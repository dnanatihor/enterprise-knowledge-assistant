"""Dev HMAC tokens and production ES256 verification.

Dev tokens are refused when auth_mode is oidc. The production verifier checks
issuer, audience, expiry, and an ES256 signature against a pinned public key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from knowledge_assistant.platform import AppError


@dataclass
class Principal:
    subject: str
    tenant_id: str
    roles: set[str]
    team: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


class DevTokenIssuer:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    def issue(self, *, subject: str, tenant_id: str, roles: list[str], team: str, ttl_s: int = 3600) -> str:
        payload = {
            "sub": subject,
            "tenantId": tenant_id,
            "roles": roles,
            "team": team,
            "exp": int(time.time()) + ttl_s,
            "iss": "dev",
        }
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        signature = _b64(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
        return f"dev.{body}.{signature}"

    def verify(self, token: str) -> Principal:
        try:
            prefix, body, signature = token.split(".")
            expected = _b64(hmac.new(self._secret, body.encode(), hashlib.sha256).digest())
            if prefix != "dev" or not hmac.compare_digest(signature, expected):
                raise ValueError("bad signature")
            payload = json.loads(_unb64(body))
            if int(payload["exp"]) < time.time():
                raise ValueError("expired")
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise AppError(401, "Unauthorised", "The bearer token is invalid.", "unauthorised") from exc
        return Principal(payload["sub"], payload["tenantId"], set(payload["roles"]), payload.get("team") or "")


def issue_es256(private_key: Any, claims: dict[str, Any]) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    header = _b64(json.dumps({"alg": "ES256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    der = private_key.sign(signing, ec.ECDSA(hashes.SHA256()))
    part_r, part_s = decode_dss_signature(der)
    signature = _b64(part_r.to_bytes(32, "big") + part_s.to_bytes(32, "big"))
    return f"{header}.{payload}.{signature}"


def verify_es256(token: str, public_pem: str, *, issuer: str, audience: str) -> Principal:
    if token.startswith("dev."):
        raise AppError(401, "Unauthorised", "Dev tokens are refused in production.", "unauthorised")
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        header_b, payload_b, sig_b = token.split(".")
        header = json.loads(_unb64(header_b))
        if header.get("alg") != "ES256":
            raise ValueError("alg")
        raw = _unb64(sig_b)
        if len(raw) != 64:
            raise ValueError("sig")
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        public_key = serialization.load_pem_public_key(public_pem.encode())
        public_key.verify(der, f"{header_b}.{payload_b}".encode(), ec.ECDSA(hashes.SHA256()))
        payload = json.loads(_unb64(payload_b))
        if payload.get("iss") != issuer or payload.get("aud") != audience or int(payload["exp"]) < time.time():
            raise ValueError("claims")
    except AppError:
        raise
    except Exception as exc:
        raise AppError(401, "Unauthorised", "The bearer token is invalid.", "unauthorised") from exc
    return Principal(payload["sub"], payload["tenantId"], set(payload["roles"]), payload.get("team") or "")
