-- ============================================================
-- Structured "exact facts" store (DuckDB).
-- Vector search is NOT reliable for numeric / exact-term queries;
-- these tables back the calculation + lookup tools.
-- ============================================================

CREATE TABLE IF NOT EXISTS pages (
    page_id      BIGINT,
    title        TEXT,
    revision_id  BIGINT,
    namespace    INTEGER,
    document_type TEXT,
    categories   TEXT,          -- JSON array
    source       TEXT,
    source_path  TEXT,
    retrieved_at TEXT,          -- ISO-8601
    game_version TEXT,
    content_hash TEXT,
    obsolete     BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS skills (
    skill_id     TEXT,
    name         TEXT,
    level        INTEGER,
    tags         TEXT,          -- JSON array of skill tags
    required_level INTEGER,
    damage_effectiveness DOUBLE,
    mana_cost    DOUBLE,
    game_version TEXT,
    revision_id  BIGINT,
    source_path  TEXT
);

CREATE TABLE IF NOT EXISTS modifiers (
    modifier_id  TEXT,
    name         TEXT,
    domain       TEXT,          -- item class / affix domain
    stat_key     TEXT,
    minimum_value DOUBLE,
    maximum_value DOUBLE,
    conditions_json TEXT,
    game_version TEXT,
    source_path  TEXT
);

CREATE TABLE IF NOT EXISTS items (
    item_id      TEXT,
    name         TEXT,
    item_class   TEXT,
    is_unique    BOOLEAN,
    required_level INTEGER,
    required_str INTEGER,
    required_dex INTEGER,
    required_int INTEGER,
    implicits_json TEXT,
    explicits_json TEXT,
    game_version TEXT,
    source_path  TEXT
);

CREATE TABLE IF NOT EXISTS passives (
    passive_id   TEXT,
    name         TEXT,
    node_type    TEXT,          -- normal / notable / keystone / ascendancy
    stats_json   TEXT,
    game_version TEXT,
    source_path  TEXT
);

-- Handy indexes for exact-term lookups.
CREATE INDEX IF NOT EXISTS idx_skills_name    ON skills(name);
CREATE INDEX IF NOT EXISTS idx_modifiers_name ON modifiers(name);
CREATE INDEX IF NOT EXISTS idx_items_name     ON items(name);
CREATE INDEX IF NOT EXISTS idx_passives_name  ON passives(name);
