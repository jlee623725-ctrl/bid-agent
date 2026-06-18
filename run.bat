@echo off
echo =========================================
echo   招投标智能体平台 — Bidding Agent Platform
echo =========================================
echo.

REM Check .env exists
if not exist .env (
    echo [WARN] .env not found, copying from .env.example
    copy .env.example .env
    echo [INFO] Please edit .env and set your DEEPSEEK_API_KEY
)

REM Check database exists
if not exist data\bid_agent.db (
    echo [INFO] Initializing database from CSV files...
    python scripts\init_db.py
)

REM Check vector index exists
if not exist data\vector_index\tfidf_matrix.npy (
    echo [INFO] Building TF-IDF vector index...
    python scripts\build_index.py
)

echo [INFO] Starting services...
echo   Streamlit UI → http://localhost:8501
echo   FastAPI      → http://localhost:8000/docs
echo.

start "Streamlit" streamlit run app.py --server.port=8501
start "FastAPI" uvicorn api:app --host 0.0.0.0 --port 8000
