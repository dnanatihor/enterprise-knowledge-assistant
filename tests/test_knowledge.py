"""RBAC, audit, cache, rollout, and evaluation tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_assistant.api import create_app
from knowledge_assistant.auth import issue_es256
from knowledge_assistant.config import Settings
from knowledge_assistant.eval_suite import run_eval
from knowledge_assistant.policies import TRANSCRIPTS
from knowledge_assistant.retrieve import ACL_FILTER_SQL


SECRET = "The payroll executive bonus pool is 900000 USD."


def settings(tmp_path: Path, **overrides: object) -> Settings:
    base = dict(
        app_env="dev",
        llm_mode="scripted",
        auth_mode="dev",
        rate_limit_per_minute=500,
        audit_path=str(tmp_path / "audit.jsonl"),
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def token(client: TestClient, roles: list[str], team: str = "pilot", subject: str = "ada") -> str:
    response = client.post(
        "/api/v1/auth/token",
        json={"subject": subject, "tenantId": "corp", "roles": roles, "team": team},
    )
    assert response.status_code == 200
    return response.json()["token"]


def test_ticket_html_and_row_sources(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path), tmp_path / "sources.jsonl")) as client:
        admin = token(client, ["knowledge-admin", "knowledge-user"])
        client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {admin}"},
            json={
                "title": "ticket",
                "source": "ticket://1",
                "mediaType": "application/x-ticket",
                "content": json.dumps({"id": "T-1", "summary": "Badge recovery", "description": "Reset the lobby badge."}),
                "acl": ["knowledge-user"],
            },
        )
        client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {admin}"},
            json={
                "title": "page",
                "source": "wiki://badge",
                "mediaType": "text/html",
                "content": "<h1>Badge</h1><script>secret()</script><p>Lobby badge resets take one day.</p>",
                "acl": ["knowledge-user"],
            },
        )
        answer = client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {admin}"},
            json={"question": "How long do lobby badge resets take?"},
        ).json()
        assert "one day" in answer["answer"]
        assert "secret()" not in json.dumps(answer)


def test_acl_sql_is_in_the_query() -> None:
    assert "EXISTS" in ACL_FILTER_SQL
    assert "role_name = ANY(%(roles)s)" in ACL_FILTER_SQL
    migration = Path("src/knowledge_assistant/db/V001__chunks.sql").read_text(encoding="utf-8")
    assert "chunk_acl" in migration
    assert "USING hnsw" in migration


def test_rbac_audit_cache_and_rollout(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path), tmp_path / "audit.jsonl")) as client:
        assert client.post("/api/v1/query", json={"question": "hello"}).status_code == 401
        admin = token(client, ["knowledge-admin", "knowledge-user", "payroll-confidential"])
        employee = token(client, ["knowledge-user"], subject="bev")
        client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {admin}"},
            json={
                "title": "bonus",
                "source": "policy://payroll",
                "content": SECRET,
                "acl": ["payroll-confidential"],
            },
        )
        before = len(TRANSCRIPTS)
        hidden = client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {employee}"},
            json={"question": "What is the payroll executive bonus pool?"},
        ).json()
        assert hidden["refused"] is True
        assert "900000" not in json.dumps(hidden)
        assert all(SECRET not in item and "900000" not in item for item in TRANSCRIPTS[before:])
        visible = client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {admin}"},
            json={"question": "What is the payroll executive bonus pool?"},
        ).json()
        assert "900000" in visible["answer"]
        assert visible["citations"][0]["quote"] == SECRET
        again = client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {admin}"},
            json={"question": "What is the payroll executive bonus pool?"},
        ).json()
        assert again["cacheHit"] is True
        assert again["costUsd"] == 0
        assert client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {admin}"}).json()["intact"] is True
        audit_file = tmp_path / "audit.jsonl"
        original = audit_file.read_text(encoding="utf-8")
        audit_file.write_text(original.replace("knowledge.query", "knowledge.tamper", 1), encoding="utf-8")
        assert client.get("/api/v1/audit/verify", headers={"Authorization": f"Bearer {admin}"}).json()["intact"] is False

    with TestClient(create_app(settings(tmp_path, rollout_teams="pilot"), tmp_path / "rollout.jsonl")) as client:
        outsider = token(client, ["knowledge-user"], team="finance-east", subject="cy")
        denied = client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {outsider}"},
            json={"question": "What is the travel policy?"},
        )
        assert denied.status_code == 403


def test_production_rejects_dev_tokens_and_accepts_es256(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    application = create_app(
        settings(tmp_path, auth_mode="oidc", oidc_public_key_pem=public_pem),
        tmp_path / "prod-audit.jsonl",
    )
    claims = {
        "sub": "ada",
        "tenantId": "corp",
        "roles": ["knowledge-user"],
        "team": "pilot",
        "iss": "https://issuer.local",
        "aud": "knowledge-assistant",
        "exp": int(time.time()) + 600,
    }
    good = issue_es256(private_key, claims)
    with TestClient(application) as client:
        assert client.post("/api/v1/auth/token", json={}).status_code == 404
        dev = client.post(
            "/api/v1/query",
            headers={"Authorization": "Bearer dev.aaa.bbb"},
            json={"question": "What is the travel policy?"},
        )
        assert dev.status_code == 401
        allowed = client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {good}"},
            json={"question": "What is the CEO home address?"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["refused"] is True


def test_golden_eval(tmp_path: Path) -> None:
    service = create_app(settings(tmp_path), tmp_path / "eval.jsonl").state.service
    report = __import__("asyncio").run(run_eval(service))
    assert report["cases"] >= 100
    assert report["faithfulness"] > 0.85
    assert report["recallAt5"] >= 0.95
    assert report["refusalAccuracy"] == 1
