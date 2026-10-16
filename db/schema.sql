CREATE TABLE horses (
    horse_id       varchar(20)  NOT NULL,
    horse_name     varchar(100),
    sex            varchar(10),
    coat_color     varchar(20),
    birthday       varchar(20),
    trainer_name   varchar(50),
    trainer_id     varchar(20),
    owner          varchar(100),
    owner_id       varchar(20),
    breeder        varchar(100),
    birthplace     varchar(50),
    sire           varchar(100),
    dam            varchar(100),
    broodmare_sire varchar(100),
    raw_data       text,
    created_at     timestamp    NOT NULL,
    updated_at     timestamp    NOT NULL,
    PRIMARY KEY (horse_id)
);

CREATE TABLE jockeys (
    jockey_id          varchar(20) NOT NULL,
    jockey_name        varchar(50),
    affiliation        varchar(50),
    birthday           varchar(20),
    first_license_year varchar(10),
    raw_data           text,
    created_at         timestamp   NOT NULL,
    updated_at         timestamp   NOT NULL,
    PRIMARY KEY (jockey_id)
);

CREATE TABLE trainers (
    trainer_id         varchar(20) NOT NULL,
    trainer_name       varchar(50),
    affiliation        varchar(50),
    birthday           varchar(20),
    first_license_year varchar(10),
    raw_data           text,
    created_at         timestamp   NOT NULL,
    updated_at         timestamp   NOT NULL,
    PRIMARY KEY (trainer_id)
);

CREATE TABLE races (
    race_id         varchar(20)  NOT NULL,
    race_name       varchar(200),
    race_number     varchar(5),
    date            varchar(20),
    venue           varchar(50),
    course_type     varchar(20),
    distance        integer,
    direction       varchar(10),
    weather         varchar(20),
    track_condition varchar(20),
    grade           varchar(20),
    start_time      varchar(10),
    head_count      integer,
    race_condition  text,
    raw_data        text,
    created_at      timestamp    NOT NULL,
    updated_at      timestamp    NOT NULL,
    PRIMARY KEY (race_id)
);

CREATE TABLE race_results (
    race_id            varchar(20)  NOT NULL,
    horse_number       varchar(5)   NOT NULL,
    finishing_position varchar(10),
    bracket_number     varchar(5),
    horse_name         varchar(100),
    horse_id           varchar(20),
    sex_age            varchar(10),
    weight_carried     varchar(10),
    jockey_name        varchar(50),
    jockey_id          varchar(20),
    finish_time        varchar(20),
    margin             varchar(20),
    passing_order      varchar(20),
    last_3f            varchar(10),
    odds               varchar(10),
    popularity         varchar(10),
    horse_weight       integer,
    horse_weight_diff  integer,
    trainer_name       varchar(50),
    trainer_id         varchar(20),
    owner              varchar(100),
    prize_money        varchar(20),
    raw_data           text,
    created_at         timestamp    NOT NULL,
    PRIMARY KEY (race_id, horse_number)
);

CREATE INDEX race_results_horse_id_idx   ON race_results (horse_id);
CREATE INDEX race_results_jockey_id_idx  ON race_results (jockey_id);
CREATE INDEX race_results_trainer_id_idx ON race_results (trainer_id);

CREATE TABLE payoffs (
    id          serial      NOT NULL,
    race_id     varchar(20) NOT NULL,
    bet_type    varchar(20),
    combination varchar(100),
    payout      varchar(50),
    popularity  varchar(20),
    created_at  timestamp   NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX payoffs_race_id_idx ON payoffs (race_id);

CREATE TABLE pre_race_odds (
    race_id      varchar(20)  NOT NULL,
    horse_number varchar(5)   NOT NULL,
    win_odds     numeric(8,1),
    scraped_at   timestamp    NOT NULL,
    created_at   timestamp    NOT NULL,
    PRIMARY KEY (race_id, horse_number)
);

CREATE INDEX pre_race_odds_race_id_idx ON pre_race_odds (race_id);

-- オッズ API（race.netkeiba.com/api/api_get_jra_odds.html?type=all）の応答そのもの。
-- 全券種（三連単を含む）の元データとして gzip 圧縮で保存する。
-- status: API の status（result=確定, middle=発走前, yoso=予想, NG=取得不可）
CREATE TABLE odds_snapshots (
    race_id           varchar(20) NOT NULL,
    fetched_at        timestamp   NOT NULL,
    status            varchar(10) NOT NULL,
    official_datetime timestamp,
    payload           bytea       NOT NULL,
    created_at        timestamp   NOT NULL,
    PRIMARY KEY (race_id, fetched_at)
);

CREATE INDEX odds_snapshots_race_id_status_idx ON odds_snapshots (race_id, status);

-- 確定オッズ（odds_snapshots の status=result から展開）。三連単（bet_type=8）は
-- 行数が多いため展開せず、必要になったら odds_snapshots から作る。
-- bet_type: 1=単勝 2=複勝 3=枠連 4=馬連 5=ワイド 6=馬単 7=三連複
-- combination: 馬番（枠連は枠番）の0埋め2桁の連結（例: 三連複 1-3-7 → '010307'）
-- odds_max: 複勝・ワイドのオッズ上限（他の券種は NULL）
CREATE TABLE final_odds (
    race_id     varchar(20)  NOT NULL,
    bet_type    smallint     NOT NULL,
    combination varchar(12)  NOT NULL,
    odds        numeric(8,1),
    odds_max    numeric(8,1),
    popularity  integer,
    PRIMARY KEY (race_id, bet_type, combination)
);
