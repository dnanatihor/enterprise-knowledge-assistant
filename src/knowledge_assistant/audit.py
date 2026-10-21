"""Append-only hash-chained audit log. Records are never updated or deleted."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self.head = "GENESIS"
        if self.path.stat().st_size:
            last = self.path.read_text(encoding="utf-8").strip().splitlines()[-1]
            self.head = json.loads(last)["hash"]

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        body = dict(event)
        body["prevHash"] = self.head
        digest = hashlib.sha256(self.head.encode() + _canonical(body)).hexdigest()
        body["hash"] = digest
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(body, sort_keys=True) + "\n")
        self.head = digest
        return body

    def verify(self) -> bool:
        previous = "GENESIS"
        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        for line in lines:
            record = json.loads(line)
            stored = record["hash"]
            check = dict(record)
            check.pop("hash", None)
            if check.get("prevHash") != previous:
                return False
            digest = hashlib.sha256(previous.encode() + _canonical(check)).hexdigest()
            if digest != stored:
                return False
            previous = stored
        return True
