"""MI Report Agent 백엔드 — Hermes Gateway 를 통해 Hermes Agent 의 전체 기능을 노출.

프로파일(연결 정보)만 갈아끼우면 어떤 OpenAI 호환 게이트웨이로도 동작한다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import classify, collection, competitors, digest, gateway, rag, topics
from .gateway import HermesGatewayError, get_client
from .profiles import get_active_profile_name, list_profiles
from .schemas import (
    ApprovalRequest,
    ChatRequest,
    CompetitorAnalyzeRequest,
    DigestGenerateRequest,
    IngestText,
    RagQueryRequest,
    RunRequest,
    SessionChatRequest,
    SourceCreate,
    SourceUpdate,
    TopicSummarizeRequest,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    collection.init_db()
    yield
    await gateway.close_all()  # 영속 게이트웨이 커넥션 정리


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


async def _guard(awaitable):
    try:
        return await awaitable
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
async def gateway_health(profile: str | None = None):
    return await _guard(_client(profile).health())


@app.get("/gateway/capabilities")
async def capabilities(profile: str | None = None):
    return await _guard(_client(profile).capabilities())


@app.get("/gateway/models")
async def models(profile: str | None = None):
    return await _guard(_client(profile).models())


@app.get("/gateway/skills")
async def skills(profile: str | None = None):
    return await _guard(_client(profile).skills())


@app.get("/gateway/toolsets")
async def toolsets(profile: str | None = None):
    return await _guard(_client(profile).toolsets())


# ── 단순 대화 ─────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest):
    client = _client(req.profile)
    messages = [m.model_dump() for m in req.messages]
    return await _guard(client.chat(
        messages, model=req.model, temperature=req.temperature,
        session_id=req.session_id, session_key=req.session_key,
    ))


# ── 에이전틱 run (전체 툴셋) ──────────────────────────────────────────
@app.post("/runs", status_code=202)
async def start_run(req: RunRequest):
    client = _client(req.profile)
    history = [m.model_dump() for m in req.conversation_history] if req.conversation_history else None
    return await _guard(client.start_run(
        req.input, instructions=req.instructions, conversation_history=history,
        session_id=req.session_id, model=req.model, session_key=req.session_key,
    ))


@app.get("/runs/{run_id}")
async def get_run(run_id: str, profile: str | None = None):
    return await _guard(_client(profile).get_run(run_id))


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
async def approve_run(run_id: str, req: ApprovalRequest, profile: str | None = None):
    return await _guard(_client(profile).approve_run(
        run_id, req.choice, resolve_all=req.resolve_all))


@app.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, profile: str | None = None):
    return await _guard(_client(profile).stop_run(run_id))


# ── 세션 ──────────────────────────────────────────────────────────────
@app.get("/sessions")
async def list_sessions(profile: str | None = None):
    return await _guard(_client(profile).list_sessions())


@app.post("/sessions", status_code=201)
async def create_session(profile: str | None = None):
    return await _guard(_client(profile).create_session())


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, profile: str | None = None):
    return await _guard(_client(profile).get_session(session_id))


@app.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, profile: str | None = None):
    return await _guard(_client(profile).session_messages(session_id))


@app.post("/sessions/{session_id}/chat")
async def session_chat(session_id: str, req: SessionChatRequest, profile: str | None = None):
    return await _guard(_client(profile).session_chat(session_id, req.message))


@app.post("/sessions/{session_id}/fork", status_code=201)
async def fork_session(session_id: str, profile: str | None = None):
    return await _guard(_client(profile).fork_session(session_id))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, profile: str | None = None):
    return await _guard(_client(profile).delete_session(session_id))


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
    # 스트리밍 저장: 전체 파일을 메모리에 올리지 않고 청크 단위로 디스크에 쓴다.
    doc_id, dest, safe_name = collection.allocate_upload(file.filename or "untitled")
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):  # 1 MiB
            out.write(chunk)
    return collection.register_upload(doc_id, dest, safe_name, topic)


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


# ── 문서 자동 분류 (AI agent) ─────────────────────────────────────────────
@app.post("/collection/documents/{doc_id}/classify")
async def collection_classify_document(doc_id: str, profile: str | None = None):
    """단일 문서를 게이트웨이(LLM)로 분류해 주제를 부여한다."""
    try:
        doc = collection.get_document(doc_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"문서 없음: {doc_id}") from e
    text = collection.read_document_text(doc_id)
    if not text:
        raise HTTPException(status_code=422, detail="본문을 읽을 수 없는 문서입니다.")
    client = _client(profile)
    try:
        result = await classify.classify_document(client, doc["title"], text)
    except HermesGatewayError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"분류 실패: {e}") from e
    document = collection.set_topic(doc_id, result["topic"]) if result["topic"] else doc
    return {"document": document, "classification": result}


@app.post("/collection/classify-untagged")
async def collection_classify_untagged(limit: int = 20, profile: str | None = None):
    """주제 미부여 문서들을 일괄 자동 분류한다(개별 실패는 건너뜀)."""
    client = _client(profile)
    classified: list[dict] = []
    for doc_id in collection.list_untagged_ids(limit):
        text = collection.read_document_text(doc_id)
        if not text:
            continue
        doc = collection.get_document(doc_id)
        try:
            result = await classify.classify_document(client, doc["title"], text)
        except (HermesGatewayError, httpx.HTTPError, ValueError):
            continue  # 개별 문서 실패는 전체를 막지 않는다
        if result["topic"]:
            collection.set_topic(doc_id, result["topic"])
            classified.append(
                {
                    "id": doc_id,
                    "title": doc["title"],
                    "topic": result["topic"],
                    "category": result["category"],
                }
            )
    return {"classified": classified, "count": len(classified)}


# ── 문서 코퍼스 Q&A (RAG) ─────────────────────────────────────────────────
@app.post("/rag/query")
async def rag_query(req: RagQueryRequest):
    """수집 문서를 근거로 자연어 질문에 답한다."""
    docs = collection.documents_for_digest(limit=req.limit, topic=req.topic, q=req.q)
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="답변 근거로 쓸 문서가 없습니다. (문서를 업로드하거나 topic/q 를 조정하세요)",
        )
    client = _client(req.profile)
    try:
        return {"question": req.question, **await rag.answer_question(client, req.question, docs)}
    except HermesGatewayError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"답변 생성 실패: {e}") from e


# ── 뉴스 다이제스트 (AI agent 생성) ───────────────────────────────────────
@app.post("/digest/generate")
async def digest_generate(req: DigestGenerateRequest):
    """수집 문서를 게이트웨이(LLM)로 요약·평가해 다이제스트 초안을 생성한다."""
    docs = collection.documents_for_digest(
        limit=req.limit, source_id=req.source, topic=req.topic
    )
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="본문이 있는 수집 문서가 없습니다. 먼저 문서를 업로드/수집하세요.",
        )
    client = _client(req.profile)
    try:
        return await digest.generate_digest(
            client, docs, issue_no=req.issueNo, period=req.period
        )
    except HermesGatewayError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        # 게이트웨이가 올바른 다이제스트 JSON 을 반환하지 않은 경우
        raise HTTPException(status_code=502, detail=f"다이제스트 생성 실패: {e}") from e


# ── 주제별 History (AI agent 생성) ────────────────────────────────────────
@app.get("/topics")
def topics_list():
    """문서에 부여된 주제 목록 + 건수."""
    return {"topics": collection.list_topics()}


@app.post("/topics/summarize")
async def topics_summarize(req: TopicSummarizeRequest):
    """한 주제의 누적 문서를 게이트웨이(LLM)로 요약·이력화한다."""
    docs = collection.documents_for_digest(limit=req.limit, topic=req.topic)
    if not docs:
        raise HTTPException(
            status_code=422,
            detail=f"'{req.topic}' 주제에 본문이 있는 문서가 없습니다.",
        )
    client = _client(req.profile)
    try:
        return await topics.generate_topic_summary(
            client, req.topic, docs, updated_at=collection.today()
        )
    except HermesGatewayError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"주제 요약 생성 실패: {e}") from e


# ── 경쟁사 IR (AI agent 생성) ─────────────────────────────────────────────
@app.post("/competitors/analyze")
async def competitors_analyze(req: CompetitorAnalyzeRequest):
    """경쟁사 IR·실적 문서를 게이트웨이(LLM)로 분기 분석화한다."""
    docs = collection.documents_for_digest(limit=req.limit, topic=req.topic, q=req.q)
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="분석할 본문 있는 문서가 없습니다. (topic/q 로 IR 문서를 지정하세요)",
        )
    client = _client(req.profile)
    try:
        return await competitors.analyze_competitor(client, req.name, req.ticker, docs)
    except HermesGatewayError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"경쟁사 분석 생성 실패: {e}") from e
