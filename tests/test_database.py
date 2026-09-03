from pathlib import Path
import sqlite3

from src.data.database import init_database


def test_database_initialises(tmp_path):
    db_path = tmp_path / "test_trading_agents.db"

    init_database(str(db_path))

    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    assert "predictions" in tables
    assert "agent_health" in tables
