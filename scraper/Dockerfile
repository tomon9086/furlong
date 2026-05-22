FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

# workspace の pyproject.toml とメンバーをコピー
COPY pyproject.toml .
COPY repository/ repository/
COPY scraper/ scraper/

# scraper とその依存 (repository) をインストール
RUN uv pip install --system ./repository ./scraper

CMD ["python", "-m", "scraper.scheduler"]
