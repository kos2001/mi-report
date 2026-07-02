# 성능 개선 (2026-07-02)

백엔드 전반의 지연·처리량 병목을 제거했다. 테스트 204개 통과, ruff 클린,
uvicorn 스모크(FTS 검색·gzip·RAG 실호출·병렬 리포트 생성) 검증 완료.

## 적용 내역

### 1. 병렬화 (wall-clock 단축)
- `pipeline.run_collection` — 소스별 수집을 `asyncio.gather` 로 동시 수행
  (전체 시간 = 가장 느린 소스). URL 형 소스의 다중 URL fetch 도 동시 수행.
- `hankyung.fetch_reports` — 리포트 PDF 다운로드를 동시 4개(세마포어)로,
  pypdf 텍스트 추출은 `asyncio.to_thread` 로 워커 스레드에서.
- `report.generate_report` — 다이제스트 생성 + 주제별 요약 LLM 호출을
  `asyncio.gather` 로 동시 수행(총평만 이후 순차). 스모크에서 다이제스트+주제+총평
  전체 39.9초(순차 대비 주제 수만큼 단축).
- `POST /collection/classify-untagged` — 문서별 분류 LLM 호출을 동시 5개로 병렬.

### 2. 이벤트 루프 보호 (동시 요청 처리량)
async 엔드포인트 안에서 이벤트 루프를 막던 블로킹 호출을 `asyncio.to_thread` 로 이동:
- RAG 검색(`documents_for_rag` — SQLite+파일+임베딩 질의 HTTP 호출 최대 60초),
  다이제스트/주제/경쟁사/리포트 문서 수집, 업로드 등록, 파이프라인 문서 저장.
- 수집기(confluence/sec/dart/hankyung)의 DB+파일+임베딩 쓰기도 워커 스레드로.

### 3. SQLite 접근 비용 제거
- `app/db.py` 신설 — 스레드별 커넥션 재사용(DB 경로별 캐시). 기존에는 모든 저장소
  함수가 호출마다 connect + PRAGMA(WAL 전환은 파일 I/O)를 반복했다.
  collection/assets/voc/qa_golden/schedule 다섯 모듈이 공유.
- N+1 제거 — `documents_for_digest/rag/competitor` 가 문서마다
  `read_document_text`(커넥션+쿼리)를 반복하던 것을 경로 일괄 조회
  (`_contents_for_ids`) 한 번으로.
- 임베딩 계산을 쓰기 트랜잭션 밖으로 분리(`_compute_embedding`/`_insert_embedding`) —
  병렬 수집 시 임베딩 HTTP 호출 동안 쓰기 잠금을 쥐지 않는다.
  커넥션 `timeout=10s` 로 병렬 쓰기 잠금 대기 여유 확보.

### 4. HTTP/LLM 클라이언트 재사용 (핸드셰이크 제거)
- `gateway` — agno Agent 를 설정(모델·온도·instructions·자격) 키로 캐시.
  Agent 는 db/메모리 미설정 시 무상태(agno 2.6 소스 확인)라 재사용·동시 arun 안전.
  내부 OpenAI 클라이언트 keep-alive 로 LLM 호출마다 들던 TLS 핸드셰이크 제거.
- `embeddings` — OpenRouter /embeddings 용 `httpx.Client` 싱글턴.
- `reranker` — 이벤트 루프별 `httpx.AsyncClient` 재사용.

### 5. 응답 압축
- `GZipMiddleware(minimum_size=1024)` — 문서 목록·다이제스트 등 큰 JSON 전송량 감소
  (스모크에서 `content-encoding: gzip` 확인).

## 검토했지만 적용하지 않은 것
- 프론트엔드: 각 페이지가 이미 `Promise.all` 병렬 페치를 사용하는 클라이언트 SPA
  구조(목업 데이터 위주)라 측정 가능한 병목 없음.
- 임베딩 벡터 행렬 인메모리 캐시: 코퍼스가 작아(수백 건) 질의당 로드 비용이
  임베딩 API 호출 대비 미미. 코퍼스가 커지면 재검토.
- uvicorn 다중 워커: e5-large 임베딩 모델이 워커마다 로드돼 메모리 비용이 큼.
  현재는 to_thread 오프로드로 단일 워커의 동시성이 충분.
