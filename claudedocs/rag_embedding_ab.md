# RAG 임베딩 모델 A/B — MiniLM vs e5-large

검증셋(`backend/tests/eval_data.py`)으로 임베딩 모델만 바꿔 recall@5 를 측정.
라이브 데이터/설정과 무관한 임시 DB에서 동일 코퍼스(12문서)로 측정.

## 결과 (recall@5)

| 검증셋 | BM25+동의어 | MiniLM(384) 하이브리드 | e5-large(1024) 하이브리드 |
|---|---|---|---|
| 기본 (12) | 1.00 | 1.00 | 1.00 |
| 동의어 (4) | 1.00 | 1.00 | 1.00 |
| **패러프레이즈 (6, 사전 밖·어휘 비중첩)** | 0.67 | 0.83 | **1.00** |

(하이브리드 = BM25 ⊕ dense RRF. dense 단독도 동일 수치였음.)

## 해석
- 기본·동의어 셋은 어휘+동의어 레이어로 이미 1.00 → 임베딩 모델 영향 없음.
- **패러프레이즈 셋이 변별 지점**: e5-large 가 MiniLM이 놓친 케이스
  (`스마트폰 핵심 두뇌칩 평균 판매가격` → AP/ASP 문서)까지 회수해 **0.83 → 1.00**.

## 트레이드오프
| | MiniLM-L12-v2 | e5-large |
|---|---|---|
| 차원 | 384 | 1024 |
| 모델 크기 | ~0.22 GB | ~2.24 GB |
| 메모리/지연 | 낮음 | 높음 |
| 패러프레이즈 recall@5 | 0.83 | 1.00 |

## 결정
- **라이브(mi-report 프로필)는 e5-large 채택** — `profiles/mi-report/.env`:
  `MI_EMBEDDINGS=1`, `MI_EMBED_MODEL=intfloat/multilingual-e5-large`.
- 코어 기본값은 경량 MiniLM 유지(`app/embeddings.py`) — 배포 환경이 env 로 선택.
- e5 계열은 query/passage 프리픽스 필요 → `embeddings._prefixed` 가 자동 처리.

## 재현
```bash
# backend 에서, 두 모델로 검증셋 측정 (모델 첫 사용 시 다운로드)
MI_EMBEDDINGS=1 .venv/bin/python -m pytest tests/test_retrieval_eval.py -s
```

참조 설계: `~/gitspace/lsi_error_analyzer` (FastEmbed + RRF, 동일 A/B 패턴).
