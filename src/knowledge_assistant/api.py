"""Authenticated edge. Every query is authorised before retrieval."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from knowledge_assistant.auth import DevTokenIssuer, Principal, verify_es256
from knowledge_assistant.config import Settings
from knowledge_assistant.eval_suite import run_eval
from knowledge_assistant.platform import AppError, CorrelationMiddleware, Metrics, RateLimiter, error_response
from knowledge_assistant.service import KnowledgeService

INDEX = Path(__file__).resolve().parent / "static" / "index.html"


class TokenIn(BaseModel):
    subject: str
    tenantId: str
    roles: list[str]
    team: str = "pilot"


class DocumentIn(BaseModel):
    title: str
    source: str
    content: str = Field(min_length=1)
    acl: list[str] = Field(min_length=1)
    mediaType: str = "text/plain"


class QueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=8000)


def create_app(settings: Settings | None = None, audit_path: Path | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.app_env == "prod" or settings.auth_mode == "oidc":
        _ = settings.resolved_api_key if settings.app_env == "prod" else None
        if not settings.oidc_public_key_pem:
            raise AppError(500, "OIDC key missing", "Production auth requires a pinned ES256 public key.", "oidc-key-missing")
    if settings.database_url:
        from knowledge_assistant.pg import migrate

        migrate(settings.database_url)
    path = audit_path or Path(settings.audit_path or ".data/audit.jsonl")
    service = KnowledgeService(settings, path)
    issuer = DevTokenIssuer(settings.dev_auth_secret)
    metrics = Metrics(settings.service_name)
    app = FastAPI(title="Enterprise Knowledge Assistant", version="0.1.0")
    app.state.service = service
    app.state.metrics = metrics
    app.state.issuer = issuer

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> Response:
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, _exc: RequestValidationError) -> Response:
        return error_response(AppError(422, "Invalid request", "The request body is invalid.", "invalid-request"))

    def principal_from(request: Request) -> Principal:
        header = request.headers.get("authorization") or ""
        if not header.lower().startswith("bearer "):
            raise AppError(401, "Unauthorised", "A bearer token is required.", "unauthorised")
        token = header.split(" ", 1)[1].strip()
        if settings.auth_mode == "oidc":
            return verify_es256(
                token,
                settings.oidc_public_key_pem,
                issuer=settings.oidc_issuer,
                audience=settings.oidc_audience,
            )
        return issuer.verify(token)

    if settings.auth_mode != "oidc":

        @app.post("/api/v1/auth/token")
        def issue(body: TokenIn) -> dict[str, str]:
            return {
                "token": issuer.issue(
                    subject=body.subject,
                    tenant_id=body.tenantId,
                    roles=body.roles,
                    team=body.team,
                )
            }

    @app.post("/api/v1/documents", status_code=201)
    def ingest(body: DocumentIn, request: Request) -> dict[str, object]:
        return service.ingest(
            principal_from(request),
            title=body.title,
            source=body.source,
            content=body.content,
            acl=body.acl,
            media_type=body.mediaType,
        )

    @app.post("/api/v1/query")
    async def query(body: QueryIn, request: Request) -> dict[str, object]:
        result = await service.query(principal_from(request), body.question)
        metrics.add_cost(result["costUsd"])
        return result

    @app.get("/api/v1/audit/verify")
    def verify_audit(request: Request) -> dict[str, bool]:
        principal_from(request)
        return {"intact": service.audit.verify()}

    @app.post("/api/v1/eval")
    async def evaluate(request: Request) -> dict[str, object]:
        principal = principal_from(request)
        if "knowledge-admin" not in principal.roles:
            raise AppError(403, "Forbidden", "Eval is limited to knowledge admins.", "forbidden")
        return await run_eval(service)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/metrics")
    def metrics_endpoint() -> Response:
        return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(INDEX)

    app.add_middleware(
        CorrelationMiddleware,
        service=settings.service_name,
        environment=settings.app_env,
        metrics=metrics,
        limiter=RateLimiter(settings.rate_limit_per_minute),
    )
    return app
