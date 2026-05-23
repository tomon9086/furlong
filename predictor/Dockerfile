FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

# workspace の pyproject.toml とメンバーをコピー
COPY pyproject.toml .
COPY repository/ repository/
COPY predictor/ predictor/

# predictor とその依存 (repository) をインストール
RUN uv pip install --system ./repository ./predictor

CMD ["uvicorn", "predictor.api:app", "--host", "0.0.0.0", "--port", "8000"]
