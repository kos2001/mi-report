"""MI Report Agent 백엔드 — Hermes Gateway 를 통해 Hermes Agent 의 전체 기능을 노출.

프로파일(연결 정보)만 갈아끼우면 어떤 OpenAI 호환 게이트웨이로도 동작한다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import collection
from .gateway import HermesGatewayError, get_client
from .profiles import get_active_profile_name, list_profiles
from .schemas import (
    ApprovalRequest,
    ChatRequest,
    IngestText,
    RunRequest,
    SessionChatRequest,
    SourceCreate,
    SourceUpdate,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    collection.init_db()
    yield


app = FastAPI(
    title="MI Report Agent Backend",
    version="0.1.0",
    description="Hermes Gateway(OpenAI 호환)를 통해 Hermes Agent CLI 전체 기능을 사용한다.",
    lifespan=lifespan,
)

# 프론트엔드(Next.js dev: 3000/3300)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3300"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client(profile: str | None = None):
    try:
        return get_client(profile)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _guard(fn):
    try:
        return fn()
    except HermesGatewayError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e


# ── 프로파일 ──────────────────────────────────────────────────────────
@app.get("/profiles")
def profiles():
    return {"active": get_active_profile_name(), "profiles": list_profiles()}


# ── 디스커버리 ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "active_profile": get_active_profile_name()}


@app.get("/gateway/health")
def gateway_health(profile: str | None = None):
    return _guard(lambda: _client(profile).health())


@app.get("/gateway/capabilities")
def capabilities(profile: str | None = None):
    return _guard(lambda: _client(profile).capabilities())


@app.get("/gateway/models")
def models(profile: str | None = None):
    return _guard(lambda: _client(profile).models())


@app.get("/gateway/skills")
def skills(profile: str | None = None):
    return _guard(lambda: _client(profile).skills())


@app.get("/gateway/toolsets")
def toolsets(profile: str | None = None):
    return _guard(lambda: _client(profile).toolsets())


# ── 단순 대화 ─────────────────────────────────────────────────────────
@app.post("/chat")
def chat(req: ChatRequest):
    client = _client(req.profile)
    messages = [m.model_dump() for m in req.messages]
    return _guard(lambda: client.chat(
        messages, model=req.model, temperature=req.temperature,
        session_id=req.session_id, session_key=req.session_key,
    ))


# ── 에이전틱 run (전체 툴셋) ──────────────────────────────────────────
@app.post("/runs", status_code=202)
def start_run(req: RunRequest):
    client = _client(req.profile)
    history = [m.model_dump() for m in req.conversation_history] if req.conversation_history else None
    return _guard(lambda: client.start_run(
        req.input, instructions=req.instructions, conversation_history=history,
        session_id=req.session_id, model=req.model, session_key=req.session_key,
    ))


@app.get("/runs/{run_id}")
def get_run(run_id: str, profile: str | None = None):
    return _guard(lambda: _client(profile).get_run(run_id))


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str, profile: str | None = None):
    client = _client(profile)

    async def event_stream():
        try:
            async for line in client.stream_run_events(run_id):
                # SSE 프레이밍 유지: 게이트웨이가 보낸 'data: ...' 라인을 그대로 전달
                yield f"{line}\n"
        except HermesGatewayError as e:
            yield f"data: {{\"event\": \"error\", \"status\": {e.status}}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/runs/{run_id}/approval")
def approve_run(run_id: str, req: ApprovalRequest, profile: str | None = None):
    return _guard(lambda: _client(profile).approve_run(
        run_id, req.choice, resolve_all=req.resolve_all))


@app.post("/runs/{run_id}/stop")
def stop_run(run_id: str, profile: str | None = None):
    return _guard(lambda: _client(profile).stop_run(run_id))


# ── 세션 ──────────────────────────────────────────────────────────────
@app.get("/sessions")
def list_sessions(profile: str | None = None):
    return _guard(lambda: _client(profile).list_sessions())


@app.post("/sessions", status_code=201)
def create_session(profile: str | None = None):
    return _guard(lambda: _client(profile).create_session())


@app.get("/sessions/{session_id}")
def get_session(session_id: str, profile: str | None = None):
    return _guard(lambda: _client(profile).get_session(session_id))


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str, profile: str | None = None):
    return _guard(lambda: _client(profile).session_messages(session_id))


@app.post("/sessions/{session_id}/chat")
def session_chat(session_id: str, req: SessionChatRequest, profile: str | None = None):
    return _guard(lambda: _client(profile).session_chat(session_id, req.message))


@app.post("/sessions/{session_id}/fork", status_code=201)
def fork_session(session_id: str, profile: str | None = None):
    return _guard(lambda: _client(profile).fork_session(session_id))


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, profile: str | None = None):
    return _guard(lambda: _client(profile).delete_session(session_id))


# ── 데이터 수집 ────────────────────────────────────────────────────────
@app.get("/collection/sources")
def collection_sources():
    # documentCount 를 함께 반환 → 대시보드가 문서 전체 목록을 받지 않고 개수만 사용.
    return {"sources": collection.list_sources(), "documentCount": collection.count_documents()}


@app.post("/collection/sources", status_code=201)
def collection_create_source(req: SourceCreate):
    try:
        return collection.create_source(req.name, req.type, req.config, req.enabled)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.patch("/collection/sources/{source_id}")
def collection_update_source(source_id: str, req: SourceUpdate):
    try:
        return collection.update_source(
            source_id, name=req.name, config=req.config, enabled=req.enabled
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"소스 없음: {source_id}") from e


@app.delete("/collection/sources/{source_id}", status_code=204)
def collection_delete_source(source_id: str):
    try:
        collection.delete_source(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"소스 없음: {source_id}") from e


@app.post("/collection/sources/{source_id}/collect")
def collection_collect(source_id: str):
    try:
        return collection.collect_source(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"소스 없음: {source_id}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/collection/upload", status_code=201)
async def collection_upload(file: UploadFile = File(...), topic: str | None = Form(None)):
    content = await file.read()
    return collection.save_upload(file.filename or "untitled", content, topic)


@app.post("/collection/ingest", status_code=201)
def collection_ingest(req: IngestText):
    """COM 인제스트 워커 진입점: DRM 해제 상태로 추출된 텍스트를 문서로 등록."""
    return collection.ingest_text(
        req.title, req.text, topic=req.topic,
        original_filename=req.original_filename,
        source_name=req.source_name or collection.COM_SOURCE_NAME,
    )


@app.get("/collection/documents")
def collection_documents(source: str | None = None, q: str | None = None,
                         topic: str | None = None):
    return {"documents": collection.list_documents(source_id=source, q=q, topic=topic)}


@app.delete("/collection/documents/{doc_id}", status_code=204)
def collection_delete_document(doc_id: str):
    try:
        collection.delete_document(doc_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"문서 없음: {doc_id}") from e
