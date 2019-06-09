CREATE TABLE character_money_transactions
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    char_id       INTEGER NOT NULL,
    money         INTEGER NOT NULL,
    type          TEXT,
    description   TEXT,
    created       INTEGER NOT NULL,
    deleted       INTEGER
);

CREATE TABLE character_stats
(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT    NOT NULL,
    char_id INTEGER NOT NULL,
    stat_1  INTEGER,
    stat_2  INTEGER,
    stat_3  INTEGER,
    stat_4  INTEGER,
    stat_5  INTEGER,
    stat_6  INTEGER,
    stat_7  INTEGER,
    exp     INTEGER DEFAULT 3000 NOT NULL,
    deleted INTEGER
);

CREATE TABLE character_work
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    char_id       INTEGER NOT NULL,
    job_id        INTEGER NOT NULL,
    difficulty    INTEGER NOT NULL,
    created       INTEGER NOT NULL,
    completed     INTEGER,
    deleted       INTEGER
);

CREATE TABLE jobs
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    stat_ids      TEXT NOT NULL,
    created       INTEGER NOT NULL,
    deleted       INTEGER
);

CREATE TABLE quests
(
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    caption                 TEXT NOT NULL,
    description             TEXT NOT NULL,
    repeat_hours            INTEGER,
    max_active_count        INTEGER DEFAULT 1 NOT NULL,
    max_duration            INTEGER NULL,
    min_stats               TEXT, /* json list */
    min_group_size          INTEGER DEFAULT 1 NOT NULL,
    reward_money            INTEGER NOT NULL,
    reward_exp              INTEGER NOT NULL,
    bot_command             TEXT,
    on_finish_enable_quests TEXT, /* json list */
    enabled                 INTEGER DEFAULT 1 NOT NULL
);
CREATE UNIQUE INDEX quests_caption_uindex ON quests (caption);

CREATE TABLE quest_parts
(
	  id              INTEGER PRIMARY KEY AUTOINCREMENT,
	  quest_id        INTEGER NOT NULL,
	  part_num        INTEGER NOT NULL,
	  next_part_num   INTEGER NOT NULL,
	  part_name       TEXT NOT NULL,
	  condition       TEXT,
	  text            TEXT,
	  next_step_text  TEXT
);

CREATE TABLE character_quests
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    char_id       INTEGER NOT NULL,
    quest_id      INTEGER NOT NULL,
    part_id       INTEGER NOT NULL,
    status        TEXT NOT NULL,
    started       INTEGER NOT NULL,
    changed       INTEGER NOT NULL,
    completed     INTEGER NOT NULL
);

