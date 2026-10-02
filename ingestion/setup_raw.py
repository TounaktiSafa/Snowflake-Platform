"""Create RAW.HN tables / stage / file format (idempotent). Run: python -m ingestion.setup_raw"""
from pathlib import Path

from ingestion.hn_ingest import connect

SQL = Path(__file__).parent / "sql" / "setup_raw.sql"

if __name__ == "__main__":
    conn = connect()
    cur = conn.cursor()
    for stmt in SQL.read_text().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    conn.close()
    print("RAW.HN ready")
