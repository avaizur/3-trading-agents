import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS agent_health (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 agent_name TEXT NOT NULL,
 status TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 opportunity_id INTEGER NOT NULL,
 agent_name TEXT NOT NULL,
 decision TEXT NOT NULL,
 confidence REAL NOT NULL,
 entry REAL,
 stop REAL,
 target REAL,
 created_at TEXT NOT NULL
);
'''

def init_database(path: str = "data/trading_agents.db") -> None:
    db = Path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
