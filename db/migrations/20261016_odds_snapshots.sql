-- 2026-10-16: 全券種オッズの保存テーブルを追加（定義は db/schema.sql と同じ）
-- 適用: docker compose exec -T db psql -U furlong -d furlong < db/migrations/20261016_odds_snapshots.sql

CREATE TABLE IF NOT EXISTS odds_snapshots (
    race_id           varchar(20) NOT NULL,
    fetched_at        timestamp   NOT NULL,
    status            varchar(10) NOT NULL,
    official_datetime timestamp,
    payload           bytea       NOT NULL,
    created_at        timestamp   NOT NULL,
    PRIMARY KEY (race_id, fetched_at)
);

CREATE INDEX IF NOT EXISTS odds_snapshots_race_id_status_idx ON odds_snapshots (race_id, status);

CREATE TABLE IF NOT EXISTS final_odds (
    race_id     varchar(20)  NOT NULL,
    bet_type    smallint     NOT NULL,
    combination varchar(12)  NOT NULL,
    odds        numeric(8,1),
    odds_max    numeric(8,1),
    popularity  integer,
    PRIMARY KEY (race_id, bet_type, combination)
);
