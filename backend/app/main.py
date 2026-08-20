"""MI Report Agent 백엔드 — agno + OpenRouter(OpenAI 호환) LLM 으로 AI 기능을 제공.

LLM 연결 정보는 프로파일 .env(OPENROUTER_*)로 설정한다.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import agentchat, assets, auth, classify, collection, competitors, digest, gateway, mailer, oidc, pipeline, progress, qa_golden, rag, report, schedule, topics, voc
from .gateway import LLMError, get_client
from .profiles import get_active_profile_name, list_profiles, load_profile
from .schemas import (
    CompetitorAnalyzeRequest,
    DigestGenerateRequest,
    DigestSendRequest,
    FeedbackRequest,
    IngestBatch,
    IngestText,
    AgentChatRequest,
    DigestAgentCommentRequest,
    RagQueryRequest,
    RagSearchRequest,
    ReportGenerateRequest,
    ScheduleConfig,
    SourceCreate,
    SourceUpdate,
    QaGoldenCreate,
    TopicSummarizeRequest,
    UserCreate,
    UserRoleUpdate,
    VocCreate,
    VocStatusUpdate,
)


async def _run_scheduled_pipeline(sched: dict) -> None:
    """스케줄(최초 실행 또는 재시도)로 파이프라인을 한 번 돌리고 결과를 기록."""
    schedule.mark_run(datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"))
    try:
        result = await pipeline.run_pipeline(period="자동(스케줄)", limit=sched["digestLimit"])
        schedule.log_run(trigger="auto", status="success", ingested=result.get("ingested"))
    except Exception as e:
        schedule.log_run(trigger="auto", status="failure", error=str(e))  # 실행 실패가 루프를 멈추지 않게


async def _scheduler_loop():
    """MI_SCHEDULER=1 일 때만: 30초마다 스케줄을 확인해 시각이 되면(또는 재시도 조건이
    맞으면) 파이프라인을 실행한다."""
    last_run: datetime | None = None
    while True:
        try:
            now = datetime.now(timezone.utc).astimezone()
            sched = schedule.get_schedule()
            if schedule.due_now(now, sched, last_run):
                last_run = now
                await _run_scheduled_pipeline(sched)
            elif schedule.retry_due(now, sched, schedule.recent_runs(limit=20)):
                last_run = now
                await _run_scheduled_pipeline(sched)
        except Exception:
            pass
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 활성 프로파일 .env(OPENROUTER_*/MI_EMBED_*/MI_RERANK_*/CONFLUENCE_* 등)를 시작 시
    # os.environ 에 로드 → 임베딩/리랭커/LLM 이 일관된 설정을 본다(요청 시점 의존 제거).
    try:
        load_profile()
    except Exception:
        pass
    collection.init_db()
    agentchat.init_db()
    task = None
    if os.getenv("MI_SCHEDULER", "").strip().lower() in ("1", "true", "yes", "on"):
        task = asyncio.create_task(_scheduler_loop())  # 앱 내 스케줄러(옵트인)
    yield
    if task:
        task.cancel()
    await gateway.close_all()  # 영속 게이트웨이 커넥션 정리


app = FastAPI(
    title="MI Report Agent Backend",
    version="0.1.0",
    description="agno + OpenRouter(OpenAI 호환) LLM 으로 MI 자동화 기능을 제공한다.",
    lifespan=lifespan,
)

# 프론트엔드(Next.js dev: 3000/3300)에서 호출 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3300"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 문서 목록·다이제스트 등 큰 JSON 응답 압축(전송량·체감 지연 감소)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# SSO(OIDC) 로그인↔콜백 왕복 동안만 쓰는 state/nonce 저장용(authlib 요구사항).
# 앱의 실제 인증은 계속 X-User-Token 이며, 이 세션 쿠키는 로그인 절차 밖에서는
# 쓰이지 않는다. SESSION_SECRET 미설정 시 프로세스별 임시 키(재시작하면 그 사이
# 진행 중이던 로그인만 깨짐 — 앱 인증 자체엔 영향 없음).
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET") or secrets.token_hex(32))

# 읽기(GET)=viewer 이상, 쓰기(그 외 메서드)=admin 전용. users.yaml 이 비어 있으면
# (아무도 아직 만들지 않았으면) 인증이 꺼져 있다고 보고 통과시킨다 — 그래야 최초
# 관리자를 POST /auth/users 로 만들 수 있다(부트스트랩).
_AUTH_EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def _auth_gate(request: Request, call_next):
    if request.method in ("GET", "OPTIONS") or request.url.path in _AUTH_EXEMPT_PATHS:
        return await call_next(request)
    user = auth.authenticate(request.headers.get("x-user-token"))
    if user is None:
        return JSONResponse({"detail": "인증 필요 (X-User-Token 헤더)"}, status_code=401)
    if user["role"] != "admin":
        return JSONResponse({"detail": "관리자 권한이 필요합니다."}, status_code=403)
    return await call_next(request)


def _client(profile: str | None = None):
    try:
        return get_client(profile)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── 프로파일 ──────────────────────────────────────────────────────────
@app.get("/profiles")
def profiles():
    return {"active": get_active_profile_name(), "profiles": list_profiles()}


# ── 디스커버리 ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "active_profile": get_active_profile_name()}


# ── 사용자 인증/권한(admin/viewer) ─────────────────────────────────────────
@app.get("/auth/me")
def auth_me(request: Request):
    user = auth.authenticate(request.headers.get("x-user-token"))
    return {"user": user, "authEnabled": auth.enabled()}


@app.get("/auth/users")
def auth_users_list(request: Request):
    # GET 은 전역 게이트에서 viewer 도 통과하지만, 이 목록엔 다른 사람의 토큰이
    # 그대로 들어 있으므로(뷰어가 보면 그대로 관리자로 위장 가능) 여기서만 admin 강제.
    user = auth.authenticate(request.headers.get("x-user-token"))
    if user is None or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return {"users": auth.list_users()}


@app.post("/auth/users", status_code=201)
def auth_users_create(req: UserCreate):
    try:
        return auth.create_user(req.name, req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/auth/users/{name}", status_code=204)
def auth_users_delete(name: str):
    try:
        auth.delete_user(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"사용자 없음: {name}") from e


@app.patch("/auth/users/{name}/role")
def auth_users_update_role(name: str, req: UserRoleUpdate):
    """SSO 로 처음 로그인하면 항상 viewer 로 생성되므로, admin 승격은 이 경로로만 한다."""
    try:
        return auth.update_user_role(name, req.role)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"사용자 없음: {name}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── SSO(OIDC) 로그인 ───────────────────────────────────────────────────────
@app.get("/auth/oidc/status")
def auth_oidc_status():
    return {"configured": oidc.configured()}


@app.get("/auth/oidc/login")
async def auth_oidc_login(request: Request):
    if not oidc.configured():
        raise HTTPException(
            status_code=501,
            detail="OIDC 미설정 — OIDC_ISSUER/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET 환경변수가 필요합니다.",
        )
    return await oidc.login_redirect(request)


@app.get("/auth/oidc/callback")
async def auth_oidc_callback(request: Request):
    if not oidc.configured():
        raise HTTPException(status_code=501, detail="OIDC 미설정")
    try:
        claims = await oidc.handle_callback(request)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"SSO 로그인 실패: {e}") from e
    user = auth.find_or_create_oidc_user(sub=claims["sub"], name_hint=claims["name_hint"])
    return RedirectResponse(f"{oidc.frontend_return_url()}?token={user['token']}")


# ── 지식 자산 (생성물 누적) + 자기 개선 (피드백) ──────────────────────────
@app.get("/artifacts")
def artifacts_list(kind: str | None = None, ref: str | None = None, limit: int = 50):
    """누적된 생성물(다이제스트·주제·경쟁사·리포트) 이력."""
    return {"artifacts": assets.list_artifacts(kind=kind, ref=ref, limit=limit),
            "count": assets.count_artifacts()}


@app.get("/artifacts/{artifact_id}")
def artifacts_get(artifact_id: str):
    try:
        return assets.get_artifact(artifact_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"생성물 없음: {artifact_id}") from e


@app.delete("/artifacts/{artifact_id}", status_code=204)
def artifacts_delete(artifact_id: str):
    try:
        assets.delete_artifact(artifact_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"생성물 없음: {artifact_id}") from e


@app.post("/feedback", status_code=201)
def feedback_create(req: FeedbackRequest):
    """생성물에 대한 👍/👎·메모(자기 개선 신호)를 저장한다."""
    return assets.add_feedback(req.kind, req.ref, req.rating, req.note)


@app.get("/feedback/summary")
def feedback_summary():
    return assets.feedback_summary()


@app.get("/quality/summary")
def quality_summary():
    """자기개선 loop 대시보드 — 종류별 피드백·근거검증 실패 집계 + 최근 플래그된 생성물."""
    return assets.quality_summary()


# ── VOC (Voice of Customer) ───────────────────────────────────────────────
@app.get("/voc")
def voc_list(status: str | None = None, sentiment: str | None = None):
    """고객의 목소리 목록 + 상태/감정 집계."""
    return {
        "voc": voc.list_voc(status=status, sentiment=sentiment),
        "summary": voc.voc_summary(),
    }


@app.post("/voc", status_code=201)
def voc_create(req: VocCreate):
    try:
        return voc.add_voc(
            req.reporter, req.content,
            area=req.area, category=req.category,
            sentiment=req.sentiment, priority=req.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.patch("/voc/{voc_id}")
def voc_update(voc_id: str, req: VocStatusUpdate):
    try:
        return voc.update_status(voc_id, req.status)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"VOC 없음: {voc_id}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/voc/{voc_id}", status_code=204)
def voc_delete(voc_id: str):
    try:
        voc.delete_voc(voc_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"VOC 없음: {voc_id}") from e


# ── 문서 Q&A 골든 평가셋 ──────────────────────────────────────────────────
@app.get("/qa-golden")
def qa_golden_list(kind: str | None = None):
    """평가용 골든 Q&A 목록(+개수). 평가셋 자산화."""
    return {"items": qa_golden.list_qa(kind=kind), "count": qa_golden.count()}


@app.post("/qa-golden", status_code=201)
def qa_golden_create(req: QaGoldenCreate):
    try:
        return qa_golden.add_qa(
            req.question, kind=req.kind,
            expected_ids=req.expectedIds, keywords=req.keywords,
            forbidden=req.forbidden, note=req.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/qa-golden/{qa_id}", status_code=204)
def qa_golden_delete(qa_id: str):
    try:
        qa_golden.delete_qa(qa_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Q&A 없음: {qa_id}") from e


# ── 스케줄(파이프라인 cron) ───────────────────────────────────────────────
def _schedule_view(sched: dict) -> dict:
    """스케줄 + 다음 실행/crontab/설명/앱내 스케줄러 활성여부/실행 이력을 함께 반환."""
    now = datetime.now(timezone.utc).astimezone()
    runs = schedule.recent_runs(limit=10)
    last = runs[0] if runs else None
    return {
        "schedule": sched,
        "describe": schedule.describe(sched),
        "crontab": schedule.crontab_expr(sched),
        "nextRun": schedule.next_run(now, sched).strftime("%Y-%m-%d %H:%M") if sched["enabled"] else None,
        "inAppScheduler": os.getenv("MI_SCHEDULER", "").strip().lower() in ("1", "true", "yes", "on"),
        "runs": runs,
        "lastStatus": last["status"] if last else None,
        "lastError": last["error"] if last else None,
    }


@app.get("/schedule")
def schedule_get():
    return _schedule_view(schedule.get_schedule())


@app.put("/schedule")
def schedule_put(req: ScheduleConfig):
    try:
        sched = schedule.set_schedule(
            enabled=req.enabled, frequency=req.frequency, hour=req.hour,
            minute=req.minute, weekday=req.weekday, digest_limit=req.digestLimit,
            retry_enabled=req.retryEnabled, retry_minutes=req.retryMinutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _schedule_view(sched)


@app.post("/schedule/run-now")
async def schedule_run_now():
    """스케줄 설정과 무관하게 지금 즉시 파이프라인 실행(수동 트리거)."""
    sched = schedule.get_schedule()
    try:
        result = await pipeline.run_pipeline(period="수동 실행", limit=sched["digestLimit"])
    except LLMError as e:
        schedule.log_run(trigger="manual", status="failure", error=e.detail)
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        schedule.log_run(trigger="manual", status="failure", error=f"게이트웨이 연결 실패: {e}")
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    schedule.log_run(trigger="manual", status="success", ingested=result.get("ingested"))
    schedule.mark_run(datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"))
    return result


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
async def collection_collect(source_id: str):
    """수집 트리거. 소스에 URL 이 있으면 실제로 fetch→본문 추출→문서 저장하고,
    URL 이 없으면 기존 스텁(실행 기록만 갱신)으로 동작한다."""
    try:
        source = collection.get_source(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"소스 없음: {source_id}") from e

    is_api_sync = source["type"] in ("confluence", "sec", "dart", "hankyung")
    if not is_api_sync and not collection.source_urls(source):
        # URL 없는 비-API동기화 커넥터 → 기존 스텁 동작(검증 포함)
        try:
            return collection.collect_source(source_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # 실제 수집(URL 또는 confluence). 커넥터/활성 검증.
    if source["type"] not in collection.CONNECTOR_TYPES:
        raise HTTPException(status_code=400, detail="업로드 소스는 수집 트리거 대상이 아닙니다.")
    if not source["enabled"]:
        raise HTTPException(status_code=400, detail="비활성 소스는 수집할 수 없습니다.")

    async with httpx.AsyncClient() as client:
        documents, errors = await pipeline.collect_source(source, client)

    if not documents:
        collection.mark_source_status(source_id, "오류")
        detail = "; ".join(f"{e['url']}: {e['error']}" for e in errors) or "수집된 문서가 없습니다."
        raise HTTPException(status_code=502, detail=f"수집 실패 — {detail}")

    return {
        "source": collection.get_source(source_id),
        "ingested": len(documents),
        "documents": documents,
        "errors": errors,
        "stub": False,
    }


@app.post("/collection/upload", status_code=201)
async def collection_upload(file: UploadFile = File(...), topic: str | None = Form(None)):
    # 스트리밍 저장: 전체 파일을 메모리에 올리지 않고 청크 단위로 디스크에 쓴다.
    doc_id, dest, safe_name = collection.allocate_upload(file.filename or "untitled")
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):  # 1 MiB
            out.write(chunk)
    # 등록(DB+본문 색인용 파일 읽기)은 블로킹 → 워커 스레드에서 수행
    return await asyncio.to_thread(collection.register_upload, doc_id, dest, safe_name, topic)


@app.post("/collection/ingest", status_code=201)
def collection_ingest(req: IngestText):
    """COM 인제스트 워커 진입점: DRM 해제 상태로 추출된 텍스트를 문서로 등록."""
    return collection.ingest_text(
        req.title, req.text, topic=req.topic,
        original_filename=req.original_filename,
        source_name=req.source_name or collection.COM_SOURCE_NAME,
    )


@app.post("/collection/ingest/batch", status_code=201)
def collection_ingest_batch(req: IngestBatch):
    """COM 워커 배치 진입점: 여러 문서를 일괄 임베딩 + 단일 트랜잭션으로 등록.

    동일 (제목+본문) 해시가 이미 있으면 기존 문서를 deduped=true 로 돌려준다.
    """
    docs = collection.ingest_texts([d.model_dump() for d in req.documents])
    return {
        "documents": docs,
        "ingested": sum(1 for d in docs if not d.get("deduped")),
        "deduped": sum(1 for d in docs if d.get("deduped")),
    }


@app.get("/collection/documents")
def collection_documents(source: str | None = None, q: str | None = None,
                         topic: str | None = None):
    return {"documents": collection.list_documents(source_id=source, q=q, topic=topic)}


@app.get("/collection/documents/{doc_id}")
async def collection_document_detail(doc_id: str):
    """단일 수집 문서의 메타데이터 + 추출 본문(결과 열람용). 본문 없거나 비텍스트면 content=null."""
    try:
        doc = await asyncio.to_thread(collection.get_document, doc_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"문서 없음: {doc_id}") from e
    content = await asyncio.to_thread(collection.read_document_text, doc_id, max_chars=50000)
    return {"document": doc, "content": content}


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
    text = await asyncio.to_thread(collection.read_document_text, doc_id)
    if not text:
        raise HTTPException(status_code=422, detail="본문을 읽을 수 없는 문서입니다.")
    client = _client(profile)
    try:
        result = await classify.classify_document(client, doc["title"], text)
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"분류 실패: {e}") from e
    document = collection.set_topic(doc_id, result["topic"]) if result["topic"] else doc
    return {"document": document, "classification": result}


@app.post("/collection/classify-untagged")
async def collection_classify_untagged(limit: int = 20, profile: str | None = None):
    """주제 미부여 문서들을 일괄 자동 분류한다(개별 실패는 건너뜀).

    LLM 분류 호출은 문서별로 독립 → 동시 5개로 병렬 수행(전체 시간 단축).
    """
    client = _client(profile)

    def _prepare() -> list[tuple[dict, str]]:
        out: list[tuple[dict, str]] = []
        for doc_id in collection.list_untagged_ids(limit):
            text = collection.read_document_text(doc_id)
            if text:
                out.append((collection.get_document(doc_id), text))
        return out

    pending = await asyncio.to_thread(_prepare)
    sem = asyncio.Semaphore(5)

    async def _classify_one(doc: dict, text: str) -> dict | None:
        async with sem:
            try:
                result = await classify.classify_document(client, doc["title"], text)
            except (LLMError, httpx.HTTPError, ValueError):
                return None  # 개별 문서 실패는 전체를 막지 않는다
        if not result["topic"]:
            return None
        try:
            await asyncio.to_thread(collection.set_topic, doc["id"], result["topic"])
        except KeyError:
            return None  # 분류 중 문서가 삭제된 경우 — 개별 실패로 처리
        return {
            "id": doc["id"],
            "title": doc["title"],
            "topic": result["topic"],
            "category": result["category"],
        }

    results = await asyncio.gather(*(_classify_one(d, t) for d, t in pending))
    classified = [r for r in results if r]
    return {"classified": classified, "count": len(classified)}


# ── 문서 코퍼스 Q&A (RAG) ─────────────────────────────────────────────────
@app.post("/rag/query")
async def rag_query(req: RagQueryRequest):
    """수집 문서를 근거로 자연어 질문에 답한다.

    P0: 질문으로 본문 BM25 검색(최근 N건이 아니라 관련 문서). 후보를 넉넉히 뽑고
    P1: 게이트웨이로 재랭킹해 상위 N건만 답변 컨텍스트로 사용한다.
    """
    # 후보를 limit 의 2~3배로 뽑아 재랭킹 여지를 둔다(최대 24).
    # 검색(SQLite/파일/임베딩 호출)은 블로킹 → 워커 스레드에서 수행해 이벤트 루프 보호.
    candidate_k = min(max(req.limit * 3, 12), 24)
    docs = await asyncio.to_thread(
        collection.documents_for_rag, req.question, limit=candidate_k, topic=req.topic
    )
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="답변 근거로 쓸 문서가 없습니다. (문서를 업로드하거나 topic 을 조정하세요)",
        )
    client = _client(req.profile)
    try:
        ranked = await rag.rerank(client, req.question, docs, top_n=req.limit)
        return {"question": req.question, **await rag.answer_question(client, req.question, ranked)}
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"답변 생성 실패: {e}") from e


@app.post("/rag/search")
async def rag_search(req: RagSearchRequest):
    """코퍼스 검색만 수행(LLM 답변 없음) — hermes 에이전트의 근거 조회 도구.

    hybrid(BM25+임베딩) 검색 상위 문서를 본문 스니펫과 함께 반환한다.
    """
    docs = await asyncio.to_thread(
        collection.documents_for_rag, req.query,
        limit=req.limit, topic=req.topic, max_chars=req.maxChars,
    )
    return {"query": req.query, "count": len(docs), "docs": docs}


# ── hermes 에이전트 대화 (멀티턴, 멀티유저, 도구 사용) ────────────────────
def _owned_session_or_404(session_id: str, user_id: str) -> dict:
    """세션 조회 + 소유자 확인. 남의 세션은 존재를 노출하지 않고 404."""
    sess = agentchat.get_session(session_id)
    if not sess or sess["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return sess


@app.post("/agent/chat")
async def agent_chat(req: AgentChatRequest):
    """hermes 에이전트와 대화한다(세션 유지 멀티턴, 사용자별 분리).

    에이전트가 스스로 코퍼스 검색 skill·웹 검색 등 도구를 조합해 답한다.
    같은 sessionId 로 다시 호출하면 이전 대화 맥락이 이어진다. 세션은
    userId 에 귀속되며 대화는 서버에 저장돼 재개할 수 있다.
    """
    if req.sessionId:
        await asyncio.to_thread(_owned_session_or_404, req.sessionId, req.userId)
    load_profile()  # MI_LLM_* 를 프로파일 .env 에서 로드
    try:
        result = await agentchat.chat(req.message, req.sessionId, user_id=req.userId)
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    # 환각 방어: 답변 수치를 코퍼스 재검색 문서와 대조(웹 출처 수치는 미근거로 표시될 수 있음)
    result.update(await agentchat.ground_answer(req.message, result["answer"]))
    await asyncio.to_thread(
        agentchat.record_turn, req.userId, result["sessionId"], req.message, result
    )
    return result


def _sse_response(gen):
    """이벤트 dict async generator → SSE 응답(각 이벤트는 data: JSON 한 줄)."""
    import json as _json

    from fastapi.responses import StreamingResponse

    async def _stream():
        try:
            async for ev in gen:
                yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"
        except LLMError as e:
            err = {"type": "error", "status": e.status, "detail": str(e.detail)}
            yield f"data: {_json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_with_progress(work):
    """work: async def work(on_progress) -> dict (최종 결과).

    다이제스트/주제/경쟁사/리포트 생성처럼 '한 번 호출해 결과를 기다리는' 함수를,
    내부 단계별 progress 이벤트를 실시간 SSE 로 흘려보내는 스트림으로 감싼다.
    agentchat.py 의 도구 진행사항과 같은 이벤트 모양이라 프론트가 같은
    AgentProgressView 로 그린다. work 자체는 스트리밍을 모른다(on_progress 콜백만
    받는다) — 기존 비스트리밍 엔드포인트와 로직을 공유하기 위함."""
    queue: asyncio.Queue = asyncio.Queue()

    async def on_progress(ev: dict) -> None:
        await queue.put(ev)

    async def runner() -> None:
        try:
            result = await work(on_progress)
            await queue.put({"type": "done", **result})
        except HTTPException as e:
            await queue.put({"type": "error", "status": e.status_code, "detail": e.detail})
        except LLMError as e:
            await queue.put({"type": "error", "status": e.status, "detail": str(e.detail)})
        except httpx.HTTPError as e:
            await queue.put({"type": "error", "status": 502, "detail": f"게이트웨이 연결 실패: {e}"})
        except ValueError as e:
            await queue.put({"type": "error", "status": 502, "detail": str(e)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())

    async def gen():
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    break
                yield ev
        finally:
            await task

    return _sse_response(gen())


@app.post("/agent/chat/stream")
async def agent_chat_stream(req: AgentChatRequest):
    """/agent/chat 의 SSE 버전 — 도구 진행사항(progress)·답변 델타(delta)를
    실시간 중계하고, 마지막에 검증·출처를 포함한 done 이벤트를 보낸다."""
    if req.sessionId:
        await asyncio.to_thread(_owned_session_or_404, req.sessionId, req.userId)
    load_profile()
    return _sse_response(agentchat.stream_events(req.message, req.sessionId, req.userId))


@app.get("/agent/sessions")
async def agent_sessions(userId: str):
    """사용자의 에이전트 대화 세션 목록(최근순)."""
    if not agentchat.is_valid_user_id(userId):
        raise HTTPException(status_code=400, detail="userId 형식이 올바르지 않습니다.")
    return {"sessions": await asyncio.to_thread(agentchat.list_sessions, userId)}


@app.get("/agent/sessions/{session_id}")
async def agent_session_detail(session_id: str, userId: str):
    """세션 상세(메시지 전체) — 대화 재개용."""
    sess = await asyncio.to_thread(_owned_session_or_404, session_id, userId)
    messages = await asyncio.to_thread(agentchat.session_messages, session_id)
    return {
        "id": sess["id"], "title": sess["title"],
        "createdAt": sess["created_at"], "updatedAt": sess["updated_at"],
        "messages": messages,
    }


@app.delete("/agent/sessions/{session_id}", status_code=204)
async def agent_session_delete(session_id: str, userId: str):
    await asyncio.to_thread(_owned_session_or_404, session_id, userId)
    await asyncio.to_thread(agentchat.delete_session, session_id)


# ── 주간 MI 리포트 통합 생성 (AI agent 오케스트레이션) ─────────────────────
async def _generate_report_result(
    req: ReportGenerateRequest, on_progress: progress.ProgressFn | None = None,
) -> dict:
    """리포트 생성 공통 로직(문서 수집 → 생성 → 자산 저장). 엔드포인트들이 공유."""
    def _gather_docs() -> tuple[list, dict[str, list]]:
        digest_docs = collection.documents_for_digest(limit=req.digestLimit)
        topic_docs: dict[str, list] = {}
        for t in collection.list_topics()[: req.maxTopics]:
            docs = collection.documents_for_digest(limit=req.topicLimit, topic=t["topic"])
            if docs:
                topic_docs[t["topic"]] = docs
        return digest_docs, topic_docs

    # 문서 수집(SQLite+파일 다건 읽기)은 블로킹 → 워커 스레드에서 수행
    digest_docs, topic_docs = await asyncio.to_thread(_gather_docs)
    if not digest_docs and not topic_docs:
        raise HTTPException(
            status_code=422,
            detail="리포트로 만들 본문 있는 문서가 없습니다. 먼저 문서를 업로드/수집하세요.",
        )
    client = _client(req.profile)
    try:
        result = await report.generate_report(
            client,
            digest_docs=digest_docs,
            topic_docs=topic_docs,
            issue_no=req.issueNo,
            period=req.period,
            generated_at=collection.today(),
            on_progress=on_progress,
            feedback_notes={
                "report": assets.recent_negative_feedback("report"),
                "digest": assets.recent_negative_feedback("digest"),
                "topic": assets.recent_negative_feedback("topic"),
            },
        )
        assets.save_artifact_safe("report", f"제{req.issueNo}호 리포트", str(req.issueNo), result)
        return result
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"리포트 생성 실패: {e}") from e


@app.post("/report/generate")
async def report_generate(req: ReportGenerateRequest):
    """다이제스트 + 주제 요약 + 총평을 묶어 주간 리포트 초안을 생성한다."""
    return await _generate_report_result(req)


@app.post("/report/generate/stream")
async def report_generate_stream(req: ReportGenerateRequest):
    """/report/generate 의 SSE 버전 — 병렬 분석·총평·검증 단계별 진행사항을 실시간 중계."""
    return _stream_with_progress(lambda on_progress: _generate_report_result(req, on_progress))


@app.post("/report/document")
async def report_document(req: ReportGenerateRequest):
    """리포트를 생성하고 (선택) 템플릿을 적용해 Markdown 문서로 반환한다."""
    result = await _generate_report_result(req)
    markdown = report.render_report_markdown(result, template=req.template)
    return {
        "filename": f"MI리포트_제{req.issueNo}호.md",
        "markdown": markdown,
        "report": result,
    }


# ── 뉴스 다이제스트 (AI agent 생성) ───────────────────────────────────────
async def _digest_generate_result(
    req: DigestGenerateRequest, on_progress: progress.ProgressFn | None = None,
) -> dict:
    """다이제스트 생성 공통 로직. 비스트리밍/스트리밍 엔드포인트가 공유."""
    docs = await asyncio.to_thread(
        collection.documents_for_digest,
        limit=req.limit, source_id=req.source, topic=req.topic,
    )
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="본문이 있는 수집 문서가 없습니다. 먼저 문서를 업로드/수집하세요.",
        )
    client = _client(req.profile)
    try:
        result = await digest.generate_digest(
            client, docs, issue_no=req.issueNo, period=req.period, on_progress=on_progress,
            feedback_notes=assets.recent_negative_feedback("digest"),
        )
        assets.save_artifact_safe("digest", f"제{req.issueNo}호", str(req.issueNo), result)
        return result
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        # 게이트웨이가 올바른 다이제스트 JSON 을 반환하지 않은 경우
        raise HTTPException(status_code=502, detail=f"다이제스트 생성 실패: {e}") from e


@app.post("/digest/generate")
async def digest_generate(req: DigestGenerateRequest):
    """수집 문서를 게이트웨이(LLM)로 요약·평가해 다이제스트 초안을 생성한다."""
    return await _digest_generate_result(req)


@app.post("/digest/generate/stream")
async def digest_generate_stream(req: DigestGenerateRequest):
    """/digest/generate 의 SSE 버전 — 생성·근거 검증 단계별 진행사항을 실시간 중계."""
    return _stream_with_progress(lambda on_progress: _digest_generate_result(req, on_progress))


@app.post("/digest/agent-comment")
async def digest_agent_comment(req: DigestAgentCommentRequest):
    """다이제스트 초안에 hermes 에이전트 코멘트를 단다.

    에이전트가 코퍼스·웹을 검색해 초안의 타당성·놓친 리스크·수정 제안을
    코멘트로 작성한다. 답변 수치는 코퍼스 대조 검증(numbersGrounded)을 거친다.
    """
    load_profile()  # MI_LLM_* 를 프로파일 .env 에서 로드
    try:
        return await agentchat.digest_comment(
            req.issueNo, req.period, [i.model_dump() for i in req.items]
        )
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e


@app.post("/digest/agent-comment/stream")
async def digest_agent_comment_stream(req: DigestAgentCommentRequest):
    """/digest/agent-comment 의 SSE 버전 — 진행사항·델타 중계(일회성, 저장 안 함)."""
    load_profile()
    message = agentchat.digest_comment_prompt(
        req.issueNo, req.period, [i.model_dump() for i in req.items]
    )
    return _sse_response(agentchat.stream_events(message, None, None, persist=False))


@app.get("/digest/latest")
def digest_latest():
    """스케줄 파이프라인이 마지막으로 저장한 다이제스트(없으면 null)."""
    return {"digest": pipeline.load_latest_digest()}


@app.post("/digest/send")
def digest_send(req: DigestSendRequest):
    """다이제스트를 메일로 발송한다.

    SMTP 가 설정돼 있으면 실제 발송하고, 미설정/연결 불가/ dryRun 이면 발송하지 않고
    미리보기(평문)를 돌려준다. 발송 여부는 status 로 구분(예외 대신 200 + status).
    """
    load_profile()  # 활성 프로파일 .env(SMTP_*) 를 os.environ 에 보장
    digest = {"issueNo": req.issueNo, "period": req.period,
              "items": [it.model_dump() for it in req.items]}
    subject, text, html = mailer.render_digest_email(digest, subject=req.subject)
    to = req.to or mailer.default_recipients()
    cfg = mailer.smtp_config()

    if req.dryRun or cfg is None or not to:
        reason = (
            "dryRun" if req.dryRun
            else "SMTP 미설정 (SMTP_HOST/FROM)" if cfg is None
            else "수신자 미설정 (SMTP_TO 또는 to)"
        )
        return {"status": "not_sent", "reason": reason, "subject": subject,
                "to": to, "preview": text}
    try:
        mailer.send_email(cfg, subject, text, html, to)
        return {"status": "sent", "subject": subject, "to": to}
    except Exception as e:  # SMTP 연결/인증 실패 등(사내망 미연동 포함)
        return {"status": "error", "detail": str(e), "subject": subject,
                "to": to, "preview": text}


# ── 스케줄 파이프라인 (수집 → 다이제스트 생성·저장) ───────────────────────
@app.post("/pipeline/run")
async def pipeline_run(issueNo: int = 1, period: str = "자동 수집분", limit: int = 20):
    """수집 + 다이제스트 생성·저장을 한 번에 실행한다(cron/수동 트리거 공용)."""
    try:
        return await pipeline.run_pipeline(issue_no=issueNo, period=period, limit=limit)
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e


# ── 주제별 History (AI agent 생성) ────────────────────────────────────────
@app.get("/topics")
def topics_list():
    """문서에 부여된 주제 목록 + 건수."""
    return {"topics": collection.list_topics()}


async def _topics_summarize_result(
    req: TopicSummarizeRequest, on_progress: progress.ProgressFn | None = None,
) -> dict:
    """주제 요약 생성 공통 로직. 비스트리밍/스트리밍 엔드포인트가 공유."""
    docs = await asyncio.to_thread(
        collection.documents_for_digest, limit=req.limit, topic=req.topic
    )
    if not docs:
        raise HTTPException(
            status_code=422,
            detail=f"'{req.topic}' 주제에 본문이 있는 문서가 없습니다.",
        )
    client = _client(req.profile)
    try:
        result = await topics.generate_topic_summary(
            client, req.topic, docs, updated_at=collection.today(), on_progress=on_progress,
            feedback_notes=assets.recent_negative_feedback("topic"),
        )
        assets.save_artifact_safe("topic", req.topic, req.topic, result)
        return result
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"주제 요약 생성 실패: {e}") from e


@app.post("/topics/summarize")
async def topics_summarize(req: TopicSummarizeRequest):
    """한 주제의 누적 문서를 게이트웨이(LLM)로 요약·이력화한다."""
    return await _topics_summarize_result(req)


@app.post("/topics/summarize/stream")
async def topics_summarize_stream(req: TopicSummarizeRequest):
    """/topics/summarize 의 SSE 버전 — 생성·근거 검증 단계별 진행사항을 실시간 중계."""
    return _stream_with_progress(lambda on_progress: _topics_summarize_result(req, on_progress))


# ── 경쟁사 IR (AI agent 생성) ─────────────────────────────────────────────
@app.get("/competitors/candidates")
def competitors_candidates():
    """수집된 데이터(SEC/DART 소스·한경 리포트)에서 분석 가능한 경쟁사 후보 목록."""
    return {"candidates": collection.competitor_candidates()}


async def _competitors_analyze_result(
    req: CompetitorAnalyzeRequest, on_progress: progress.ProgressFn | None = None,
) -> dict:
    """경쟁사 분석 생성 공통 로직. 비스트리밍/스트리밍 엔드포인트가 공유.

    topic/q 가 없으면 회사명·티커를 하이브리드 검색해 그 기업의 한경 컨센서스·IR 문서를
    끌어온다(실데이터 근거). topic/q 지정 시 해당 스코프로 한정한다.
    """
    if req.topic or req.q:
        docs = await asyncio.to_thread(
            collection.documents_for_digest, limit=req.limit, topic=req.topic, q=req.q
        )
    else:
        docs = await asyncio.to_thread(
            collection.documents_for_competitor, req.name, req.ticker, limit=req.limit
        )
    if not docs:
        raise HTTPException(
            status_code=422,
            detail="분석할 본문 있는 문서가 없습니다. (topic/q 로 IR 문서를 지정하세요)",
        )
    client = _client(req.profile)
    try:
        result = await competitors.analyze_competitor(
            client, req.name, req.ticker, docs, on_progress=on_progress,
            feedback_notes=assets.recent_negative_feedback("competitor"),
        )
        assets.save_artifact_safe("competitor", req.name, req.ticker or req.name, result)
        return result
    except LLMError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"게이트웨이 연결 실패: {e}") from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"경쟁사 분석 생성 실패: {e}") from e


@app.post("/competitors/analyze")
async def competitors_analyze(req: CompetitorAnalyzeRequest):
    """경쟁사 IR·실적 문서를 게이트웨이(LLM)로 분기 분석화한다."""
    return await _competitors_analyze_result(req)


@app.post("/competitors/analyze/stream")
async def competitors_analyze_stream(req: CompetitorAnalyzeRequest):
    """/competitors/analyze 의 SSE 버전 — 생성·근거 검증 단계별 진행사항을 실시간 중계."""
    return _stream_with_progress(lambda on_progress: _competitors_analyze_result(req, on_progress))
