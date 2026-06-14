# MI Report 백엔드 (FastAPI + agno/OpenRouter + fastembed)
# 빌드 컨텍스트: ./backend
FROM python:3.11-slim

WORKDIR /app

# 소스 + 프로파일(설정). .env 는 .dockerignore 로 제외(런타임 주입).
COPY pyproject.toml ./
COPY app ./app
COPY profiles ./profiles
COPY active_profile ./active_profile

# 임베딩 하이브리드 포함 설치(-e 로 두어 config.BACKEND_HOME 경로 해석이 /app 기준 유지).
RUN pip install --no-cache-dir -e '.[embeddings]'

# 의미 임베딩 기본 활성(모델/키는 런타임 환경변수로).
ENV MI_EMBEDDINGS=1
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
