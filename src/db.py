import os
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS matches (
 match_id TEXT PRIMARY KEY, map_name TEXT, date_started TEXT, duration_ms INTEGER,
 rounds INTEGER, is_ranked INTEGER, imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS raw_matches (
 match_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, stored_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS import_status (
 match_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS teams (
 match_id TEXT, team_id TEXT, won INTEGER, rounds_won INTEGER, rounds_lost INTEGER,
 kills INTEGER, deaths INTEGER, assists INTEGER, damage INTEGER,
 PRIMARY KEY(match_id,team_id), FOREIGN KEY(match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS player_profiles (
 riot_id TEXT PRIMARY KEY, display_name TEXT, avatar_path TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS player_aliases (
 alias_riot_id TEXT PRIMARY KEY, canonical_riot_id TEXT NOT NULL,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(canonical_riot_id) REFERENCES player_profiles(riot_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_alias_canonical ON player_aliases(canonical_riot_id);

CREATE TABLE IF NOT EXISTS player_matches (
 match_id TEXT, riot_id TEXT, team_id TEXT, agent TEXT, agent_image TEXT, account_level INTEGER,
 placement INTEGER, score INTEGER, acs REAL, kills INTEGER, deaths INTEGER, assists INTEGER,
 damage INTEGER, adr REAL, damage_received INTEGER, dd_delta_round REAL,
 first_kills INTEGER, first_deaths INTEGER, esr REAL, headshots INTEGER, hs_accuracy REAL,
 survived INTEGER, traded INTEGER, kast REAL, clutches INTEGER, clutches_lost INTEGER,
 single_kills INTEGER, double_kills INTEGER, triple_kills INTEGER, quadra_kills INTEGER, penta_kills INTEGER,
 plants INTEGER, defuses INTEGER,
 attack_kills INTEGER, attack_deaths INTEGER, attack_assists INTEGER, attack_adr REAL, attack_kast REAL,
 attack_first_kills INTEGER, attack_first_deaths INTEGER,
 defense_kills INTEGER, defense_deaths INTEGER, defense_assists INTEGER, defense_adr REAL, defense_kast REAL,
 defense_first_kills INTEGER, defense_first_deaths INTEGER, tags_json TEXT,
 PRIMARY KEY(match_id,riot_id),
 FOREIGN KEY(match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
 FOREIGN KEY(riot_id) REFERENCES player_profiles(riot_id)
);
CREATE TABLE IF NOT EXISTS rounds (
 match_id TEXT, round_no INTEGER, winner TEXT, result TEXT, plant_player TEXT, plant_site TEXT,
 plant_time INTEGER, defuse_player TEXT, PRIMARY KEY(match_id,round_no)
);
CREATE TABLE IF NOT EXISTS kills (
 id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT, round_no INTEGER, killer TEXT, victim TEXT,
 weapon TEXT, weapon_category TEXT, round_time INTEGER, game_time INTEGER, assistants_json TEXT
);
CREATE TABLE IF NOT EXISTS damage_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT, round_no INTEGER, attacker TEXT, target TEXT,
 damage INTEGER, headshots INTEGER, bodyshots INTEGER, legshots INTEGER
);
CREATE TABLE IF NOT EXISTS loadout_stats (
 match_id TEXT, riot_id TEXT, loadout TEXT, rounds_played INTEGER, rounds_won INTEGER,
 kills INTEGER, deaths INTEGER, assists INTEGER, damage INTEGER, adr REAL, acs REAL, kast REAL,
 first_bloods INTEGER, first_deaths INTEGER,
 PRIMARY KEY(match_id,riot_id,loadout)
);
CREATE TABLE IF NOT EXISTS player_match_stats (
 match_id TEXT, riot_id TEXT, stat_key TEXT, numeric_value REAL, display_value TEXT,
 PRIMARY KEY(match_id,riot_id,stat_key)
);
CREATE INDEX IF NOT EXISTS ix_pms_player ON player_match_stats(riot_id);
CREATE TABLE IF NOT EXISTS player_rounds (
 match_id TEXT, round_no INTEGER, riot_id TEXT, side TEXT,
 score INTEGER, kills INTEGER, deaths INTEGER, assists INTEGER, damage INTEGER,
 loadout_value INTEGER, remaining_credits INTEGER, spent_credits INTEGER,
 PRIMARY KEY(match_id,round_no,riot_id)
);
CREATE TABLE IF NOT EXISTS ability_usage (
 match_id TEXT, riot_id TEXT, ability TEXT, casts INTEGER,
 PRIMARY KEY(match_id,riot_id,ability)
);
CREATE INDEX IF NOT EXISTS ix_pr_player ON player_rounds(riot_id);
CREATE INDEX IF NOT EXISTS ix_pr_match ON player_rounds(match_id);
CREATE INDEX IF NOT EXISTS ix_pm_player ON player_matches(riot_id);
CREATE INDEX IF NOT EXISTS ix_kills_killer ON kills(killer);
CREATE INDEX IF NOT EXISTS ix_kills_victim ON kills(victim);
"""


class CompatRow(dict):
    """sqlite3.Row-like mapping for remote Turso cursor rows."""
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class CompatCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def description(self):
        return self._cursor.description

    def _columns(self):
        return [d[0] for d in (self._cursor.description or [])]

    def _row(self, row):
        if row is None:
            return None
        if isinstance(row, sqlite3.Row):
            return row
        return CompatRow(self._columns(), row)

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self._cursor.fetchall()]

    def __iter__(self):
        columns = self._columns()
        for row in self._cursor:
            if isinstance(row, sqlite3.Row):
                yield row
            else:
                yield CompatRow(columns, row)


class RemoteConnection:
    """Small DB-API compatibility layer around turso_serverless."""
    def __init__(self, con):
        self._con = con

    def execute(self, sql, params=()):
        return CompatCursor(self._con.execute(sql, params))

    def executescript(self, script):
        # SCHEMA contains no trigger bodies, so statement splitting is sufficient here.
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self._con.execute(statement)
        return self

    def commit(self):
        return self._con.commit()

    def rollback(self):
        try:
            return self._con.rollback()
        except AttributeError:
            return None

    def close(self):
        return self._con.close()


def using_turso():
    return bool(os.getenv("TURSO_DATABASE_URL"))


def connect(path=None):
    """Connect locally with sqlite3, or remotely when TURSO_DATABASE_URL is set."""
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")
    if url:
        if not token:
            raise RuntimeError("TURSO_DATABASE_URL is set but TURSO_AUTH_TOKEN is missing.")
        try:
            import libsql
        except ImportError as exc:
            raise RuntimeError("Remote Turso mode requires the 'libsql' package.") from exc
        con = libsql.connect(database=url, auth_token=token)
        return RemoteConnection(con)

    db_path = Path(path or "inhouse.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init(path=None):
    con = connect(path)
    try:
        # Avoid replaying the full schema over the network on every Vercel cold start.
        if using_turso():
            try:
                ready = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_matches'").fetchone()
                if ready:
                    return
            except Exception:
                pass
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()
