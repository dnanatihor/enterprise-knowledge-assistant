"""Gateway, RBAC retrieval, grounded answers, escalation, and audit.

Document visibility is decided in the corpus query. The model only receives
chunks that already passed the role filter.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

import knowledge_assistant.policies  # noqa: F401
from knowledge_assistant.audit import AuditLog
from knowledge_assistant.auth import Principal
from knowledge_assistant.config import Settings
from knowledge_assistant.platform import (
    AppError,
    Tracer,
    build_chat_model,
    build_deep_agent,
    correlation_id,
    cost_usd,
    estimate_tokens,
    invoke_agent,
    message_text,
    screen_input,
    scrub_output,
)
from knowledge_assistant.retrieve import Chunk, Corpus, HashingEmbedder
from knowledge_assistant.sources import normalise

REFUSAL = "I don't know. The indexed documents do not contain enough information to answer that."


class QueryState(TypedDict, total=False):
    principal: Principal
    question: str
    rewritten: str
    found: list[tuple[Chunk, float]]
    result: dict[str, Any]


class KnowledgeService:
    def __init__(self, settings: Settings, audit_path: Path) -> None:
        self.settings = settings
        self.embedder = HashingEmbedder(settings.embedding_model_id)
        self.corpus = Corpus()
        self.audit = AuditLog(audit_path)
        self.tracer = Tracer(settings.service_name)
        self.cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
        self.spend: dict[str, float] = {}
        self._model = build_chat_model(settings, "knowledge")
        self._escalation = build_deep_agent(
            self._model,
            system_prompt="TASK: ESCALATE. Draft a handoff from the question and the confidence score. Do not invent policy text.",
            tools=[],
            name="escalation",
        )
        self._graph = self._compile()

    def _compile(self):
        graph = StateGraph(QueryState)
        graph.add_node("rewrite", self._rewrite_node)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("answer", self._answer_node)
        graph.add_node("escalate", self._escalate_node)
        graph.add_edge(START, "rewrite")
        graph.add_edge("rewrite", "retrieve")
        graph.add_conditional_edges("retrieve", self._route, {"answer": "answer", "escalate": "escalate"})
        graph.add_edge("answer", END)
        graph.add_edge("escalate", END)
        return graph.compile()

    async def _rewrite_node(self, state: QueryState) -> dict[str, Any]:
        return {"rewritten": await self._rewrite(state["question"])}

    async def _retrieve_node(self, state: QueryState) -> dict[str, Any]:
        principal = state["principal"]
        rewritten = state["rewritten"]
        return {
            "found": self.corpus.search(
                tenant_id=principal.tenant_id,
                roles=principal.roles,
                query=rewritten,
                embedding=self.embedder.embed(rewritten),
                embedding_model=self.embedder.model_id,
            )
        }

    def _route(self, state: QueryState) -> str:
        found = state.get("found") or []
        if not found or found[0][1] < self.settings.confidence_threshold:
            return "escalate"
        return "answer"

    async def _answer_node(self, state: QueryState) -> dict[str, Any]:
        return {"result": await self._answer(state["question"], state["found"])}

    async def _escalate_node(self, state: QueryState) -> dict[str, Any]:
        found = state.get("found") or []
        confidence = found[0][1] if found else 0.0
        return {"result": await self._escalate(state["principal"], state["question"], confidence)}

    def ingest(
        self,
        principal: Principal,
        *,
        title: str,
        source: str,
        content: str,
        acl: list[str],
        media_type: str = "text/plain",
    ) -> dict[str, Any]:
        self._require(principal, "knowledge-admin")
        if not acl:
            raise AppError(422, "ACL required", "Every document needs at least one role.", "acl-required")
        content = normalise(media_type, content)
        chunk = Chunk(
            chunk_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            tenant_id=principal.tenant_id,
            source=source,
            section=title,
            text=content.strip(),
            acl=set(acl),
            embedding=self.embedder.embed(content),
            embedding_model=self.embedder.model_id,
        )
        self.corpus.add([chunk])
        return {"documentId": chunk.document_id, "chunkId": chunk.chunk_id, "embeddingModel": self.embedder.model_id}

    async def query(self, principal: Principal, question: str) -> dict[str, Any]:
        self._require(principal, "knowledge-user")
        self._rollout(principal)
        screen_input(question, 4000)
        if self.spend.get(principal.subject, 0.0) >= self.settings.user_budget_usd:
            raise AppError(402, "User budget exceeded", "This user has reached the cost budget.", "user-budget")
        cache_key = (
            principal.tenant_id,
            tuple(sorted(principal.roles)),
            hashlib.sha256(question.encode()).hexdigest(),
            self.embedder.model_id,
        )
        cached = self.cache.get(cache_key)
        if cached and time.time() - cached[0] < 60:
            result = dict(cached[1])
            result["cacheHit"] = True
            result["costUsd"] = 0.0
            self._audit(principal, question, result)
            return result
        with self.tracer.span("knowledge.query", tenantId=principal.tenant_id, queryHash=cache_key[2]):
            final = await self._graph.ainvoke({"principal": principal, "question": question})
            result = final["result"]
        result["cacheHit"] = False
        result["route"] = "pinned-mini"
        result["correlationId"] = correlation_id.get()
        if result["costUsd"] > self.settings.query_budget_usd:
            raise AppError(402, "Cost ceiling exceeded", "The query exceeded its cost ceiling.", "cost-ceiling")
        self.spend[principal.subject] = round(self.spend.get(principal.subject, 0.0) + result["costUsd"], 8)
        self.cache[cache_key] = (time.time(), dict(result))
        self._audit(principal, question, result)
        return result

    async def _rewrite(self, question: str) -> str:
        response = await self._model.ainvoke(
            [
                {"role": "system", "content": "TASK: REWRITE. Return the question."},
                {"role": "user", "content": f"QUESTION: {question}"},
            ]
        )
        return message_text(response).strip() or question

    async def _answer(self, question: str, found: list[tuple[Chunk, float]]) -> dict[str, Any]:
        top, score = found[0]
        grounded = top.text.strip()
        context = "\n".join(chunk.text for chunk, _score in found)
        completion = message_text(
            await self._model.ainvoke(
                [
                    {"role": "system", "content": "Answer from the grounded sentence only."},
                    {"role": "user", "content": f"QUESTION: {question}\nGROUNDED: {grounded}\nCONTEXT:\n{context}"},
                ]
            )
        )
        answer = scrub_output(completion if grounded in completion else grounded)
        if grounded not in top.text:
            raise AppError(500, "Citation failed verification", "The quote is not in the source chunk.", "citation-mismatch")
        cost = self._price(context, answer)
        return {
            "answer": answer,
            "refused": False,
            "escalated": False,
            "confidence": score,
            "citations": [
                {
                    "documentId": top.document_id,
                    "chunkId": top.chunk_id,
                    "section": top.section,
                    "source": top.source,
                    "quote": grounded,
                }
            ],
            "contexts": [chunk.text for chunk, _score in found],
            "chunkIds": [chunk.chunk_id for chunk, _score in found],
            "costUsd": round(cost, 8),
        }

    async def _escalate(self, principal: Principal, question: str, confidence: float) -> dict[str, Any]:
        # The escalation agent is not given retrieved text. Low confidence must not
        # become a path that stuffs restricted chunks into a prompt.
        draft = await invoke_agent(
            self._escalation,
            [{"role": "user", "content": f"TASK: ESCALATE\nQUESTION: {question}\nCONFIDENCE: {confidence}"}],
            thread_id=f"esc-{uuid.uuid4().hex}",
            recursion_limit=8,
        )
        return {
            "answer": REFUSAL,
            "escalation": scrub_output(draft),
            "refused": True,
            "escalated": True,
            "confidence": confidence,
            "citations": [],
            "contexts": [],
            "chunkIds": [],
            "costUsd": round(self._price(question, draft), 8),
            "principal": principal.subject,
        }

    def _audit(self, principal: Principal, question: str, result: dict[str, Any]) -> None:
        self.audit.append(
            {
                "eventId": str(uuid.uuid4()),
                "eventType": "knowledge.query.escalated" if result.get("escalated") else "knowledge.query.completed",
                "source": self.settings.service_name,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "correlationId": correlation_id.get(),
                "schemaVersion": 1,
                "tenantId": principal.tenant_id,
                "subject": principal.subject,
                "roles": sorted(principal.roles),
                "queryHash": hashlib.sha256(question.encode()).hexdigest(),
                "chunkIds": result.get("chunkIds") or [],
                "answerHash": hashlib.sha256(result.get("answer", "").encode()).hexdigest(),
                "refused": bool(result.get("refused")),
                "cacheHit": bool(result.get("cacheHit")),
                "costUsd": result.get("costUsd", 0),
            }
        )

    def _rollout(self, principal: Principal) -> None:
        allowed = self.settings.teams
        if allowed and principal.team not in allowed:
            raise AppError(403, "Not in rollout", "This team is outside the current rollout.", "rollout")

    def _require(self, principal: Principal, role: str) -> None:
        if role not in principal.roles:
            raise AppError(403, "Forbidden", "The principal does not have the required role.", "forbidden")

    def _price(self, prompt: str, completion: str) -> float:
        return cost_usd(
            estimate_tokens(prompt),
            estimate_tokens(completion),
            self.settings.input_usd_per_token,
            self.settings.output_usd_per_token,
        )
