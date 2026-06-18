FROM python:3.11-slim

WORKDIR /app

# System dependencies for scikit-learn
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501 8000

CMD ["sh", "-c", "streamlit run app.py --server.port=8501 & uvicorn api:app --host 0.0.0.0 --port 8000"]
