"""Golden questions over role-scoped policy sentences."""

from __future__ import annotations

from typing import Any

from knowledge_assistant.auth import Principal
from knowledge_assistant.service import KnowledgeService, REFUSAL

DEPARTMENTS = [
    "finance", "payroll", "treasury", "legal", "procurement", "facilities", "security",
    "audit", "compliance", "benefits", "recruiting", "engineering", "product", "design",
    "support", "marketing", "sales", "logistics", "research", "quality",
]


def _principal() -> Principal:
    return Principal("eval-user", "corp", {"knowledge-admin", "knowledge-user"}, "pilot")


async def run_eval(service: KnowledgeService) -> dict[str, Any]:
    principal = _principal()
    cases: list[tuple[str, str, str]] = []
    for index, department in enumerate(DEPARTMENTS):
        facts = [
            (
                f"What is the {department} department approval limit?",
                f"The {department} department approval limit is {1000 + index} USD.",
                f"{1000 + index} USD",
            ),
            (
                f"What is the {department} department retention period?",
                f"The {department} department retention period is {30 + index} days.",
                f"{30 + index} days",
            ),
            (
                f"What is the {department} department oncall channel?",
                f"The {department} department oncall channel is #{department}-oncall.",
                f"#{department}-oncall",
            ),
            (
                f"What is the {department} department data classification?",
                f"The {department} department data classification is tier-{index}.",
                f"tier-{index}",
            ),
            (
                f"What is the {department} department review cadence?",
                f"The {department} department review cadence is every {index + 1} weeks.",
                f"{index + 1} weeks",
            ),
        ]
        for question, sentence, marker in facts:
            ingested = service.ingest(
                principal,
                title=department,
                source=f"policy://{department}",
                content=sentence,
                acl=["knowledge-user"],
            )
            cases.append((question, ingested["chunkId"], marker))
    hits = 0
    grounded = 0
    for question, chunk_id, marker in cases:
        result = await service.query(principal, question)
        if chunk_id in result["chunkIds"][:5] and marker in result["answer"] and result["citations"]:
            hits += 1
        if result["citations"] and result["citations"][0]["quote"] in result["contexts"][0]:
            grounded += 1
    refusals = 0
    for question in ("What is the CEO home address?", "What is the production root password?"):
        result = await service.query(principal, question)
        if result["refused"] and result["answer"] == REFUSAL and not result["citations"]:
            refusals += 1
    return {
        "cases": len(cases) + 2,
        "faithfulness": round(grounded / len(cases), 4),
        "recallAt5": round(hits / len(cases), 4),
        "refusalAccuracy": refusals / 2,
    }
