"""統合テスト用 pytest フィクスチャ."""

import pathlib
from collections.abc import Generator

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from repository.database import Database

_SCHEMA_PATH = pathlib.Path(__file__).parent.parent.parent / "db" / "schema.sql"

_ALL_TABLES = [
    "payoffs",
    "race_results",
    "races",
    "horses",
    "jockeys",
    "trainers",
]


@pytest.fixture(scope="session")
def pg_container() -> Generator[PostgresContainer, None, None]:
    """テストセッション中に PostgreSQL コンテナを1つ起動・停止する。"""
    with PostgresContainer("postgres:16") as container:
        yield container


@pytest.fixture(scope="session")
def db_url(pg_container: PostgresContainer) -> str:
    """スキーマを適用し、接続 URL を返す（セッション中1回のみ実行）。"""
    host = pg_container.get_container_host_ip()
    port = pg_container.get_exposed_port(5432)
    url = (
        f"postgresql://{pg_container.username}:{pg_container.password}"
        f"@{host}:{port}/{pg_container.dbname}"
    )
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
