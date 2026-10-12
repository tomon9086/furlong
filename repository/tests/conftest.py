"""統合テスト用 pytest フィクスチャ."""

import pathlib

import psycopg
import pytest
from pytest_docker.plugin import Services

from repository.database import Database

_TESTS_DIR = pathlib.Path(__file__).parent
_SCHEMA_PATH = _TESTS_DIR.parent.parent / "db" / "schema.sql"

_ALL_TABLES = [
    "payoffs",
    "race_results",
    "races",
    "horses",
    "jockeys",
    "trainers",
]


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    """pytest-docker が起動する compose ファイル（tests/docker-compose.yml）。"""
    return str(_TESTS_DIR / "docker-compose.yml")


@pytest.fixture(scope="session")
def db_url(docker_ip: str, docker_services: Services) -> str:
    """テスト用 PostgreSQL にスキーマを適用し、接続 URL を返す（セッション中1回のみ）。

    コンテナは docker compose 経由で起動するため、docker コマンドが使える環境
    （アクティブな docker context）であれば追加の設定なしで動く。
    """
    port = docker_services.port_for("db", 5432)
    url = f"postgresql://test:test@{docker_ip}:{port}/test"
    schema_sql = _SCHEMA_PATH.read_text()
    with psycopg.connect(url) as conn:
        conn.execute(schema_sql)
    return url


@pytest.fixture
def db(db_url: str) -> Database:
    """各テスト前に全テーブルを truncate し、Database インスタンスを返す。"""
    tables = ", ".join(_ALL_TABLES)
    with psycopg.connect(db_url) as conn:
        conn.execute(f"TRUNCATE {tables} RESTART IDENTITY")
    return Database(db_url)
