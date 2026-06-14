"""백엔드 전역 설정.

프로파일 루트와 활성 프로파일 위치를 결정한다.
프로파일 구조:
  - <root>/profiles/<name>/config.yaml | .env | SOUL.md
  - <root>/active_profile           (활성 프로파일 이름; 없으면 DEFAULT)
환경변수로 재정의 가능:
  - MI_BACKEND_HOME  : 프로파일 루트 (기본: backend 디렉토리)
  - MI_ACTIVE_PROFILE: 활성 프로파일 강제 지정
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/ 디렉토리 (이 파일 기준 한 단계 위)
BACKEND_HOME = Path(os.environ.get("MI_BACKEND_HOME", Path(__file__).resolve().parent.parent))

PROFILES_DIR = BACKEND_HOME / "profiles"
ACTIVE_PROFILE_FILE = BACKEND_HOME / "active_profile"

# active_profile 파일도 없고 환경변수도 없을 때의 폴백
DEFAULT_PROFILE = "mi-report"

# 데이터 수집 저장소 (SQLite + 업로드 파일)
DATA_DIR = Path(os.environ.get("MI_DATA_DIR", BACKEND_HOME / "data"))
COLLECTION_DB = DATA_DIR / "collection.db"
UPLOADS_DIR = DATA_DIR / "uploads"

# 스케줄 파이프라인이 생성한 다이제스트 산출물 저장 위치(JSON)
DIGESTS_DIR = DATA_DIR / "digests"
