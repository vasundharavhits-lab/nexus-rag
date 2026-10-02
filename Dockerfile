FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV HF_HOME=/models/huggingface
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN grep -v -E "^(ipykernel|matplotlib)" requirements.txt > req-docker.txt
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r req-docker.txt
COPY app ./app
COPY scripts ./scripts
COPY eval ./eval
COPY data/raw ./data/raw
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]