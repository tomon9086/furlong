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
