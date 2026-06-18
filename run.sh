#!/usr/bin/env bash
set -e

echo "========================================="
echo "  招投标智能体平台 — Bidding Agent Platform"
echo "========================================="

# Check .env exists
if [ ! -f .env ]; then
    echo "[WARN] .env not found, copying from .env.example"
    cp .env.example .env
    echo "[INFO] Please edit .env and set your DEEPSEEK_API_KEY"
fi

# Check database exists
if [ ! -f data/bid_agent.db ]; then
    echo "[INFO] Initializing database from CSV files..."
    python scripts/init_db.py
fi

# Check vector index exists
if [ ! -f data/vector_index/tfidf_matrix.npy ]; then
    echo "[INFO] Building TF-IDF vector index..."
    python scripts/build_index.py
fi

echo "[INFO] Starting services..."
echo "  Streamlit UI → http://localhost:8501"
echo "  FastAPI      → http://localhost:8000/docs"
echo ""

# Start both services
streamlit run app.py --server.port=8501 &
PID_ST=$!
uvicorn api:app --host 0.0.0.0 --port 8000 &
PID_API=$!

# Wait for any to exit
trap "kill $PID_ST $PID_API 2>/dev/null" EXIT
wait
