"""Incremental Hacker News ingestion: Algolia API -> NDJSON.gz -> internal stage -> RAW.HN.*

Run: python -m ingestion.hn_ingest
- comments: only items newer than the stored high-watermark
- stories : additionally re-fetches the last HN_STORY_REFRESH_HOURS so points / num_comments
            changes land in RAW and the dbt snapshot (SCD2) can record them
"""
import gzip
import json
import os
import tempfile
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

API = "https://hn.algolia.com/api/v1/search_by_date"
CAP = 1000            # Algolia returns at most 1000 hits per query
WINDOW = 3600         # seconds per query window
SOURCES = {"stories": "story", "comments": "comment"}


def _session() -> requests.Session:
    retry = Retry(total=5, connect=5, read=5, backoff_factor=2,
                  status_forcelist=(429, 500, 502, 503, 504))
    sess = requests.Session()
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess


SESSION = _session()


def connect(role: str = "LOADER"):
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        role=role,
        database="RAW",
        schema="HN",
    )


def fetch_window(tag: str, start: int, end: int) -> list[dict]:
    """Items with start < created_at_i <= end; bisects when the cap is hit."""
    r = SESSION.get(
        API,
        params={
            "tags": tag,
            "numericFilters": f"created_at_i>{start},created_at_i<={end}",
            "hitsPerPage": CAP,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data["nbHits"] > CAP and end - start > 1:
        mid = (start + end) // 2
        return fetch_window(tag, start, mid) + fetch_window(tag, mid, end)
    return data["hits"]


def get_watermark(cur, source: str, default: int) -> int:
    cur.execute("SELECT high_watermark FROM INGESTION_STATE WHERE source = %s", (source,))
    row = cur.fetchone()
    return int(row[0]) if row else default


def set_watermark(cur, source: str, value: int) -> None:
    cur.execute(
        """MERGE INTO INGESTION_STATE t
           USING (SELECT %s AS source, %s AS wm) s ON t.source = s.source
           WHEN MATCHED THEN UPDATE SET high_watermark = s.wm, updated_at = CURRENT_TIMESTAMP()
           WHEN NOT MATCHED THEN INSERT (source, high_watermark, updated_at)
             VALUES (s.source, s.wm, CURRENT_TIMESTAMP())""",
        (source, value),
    )


def ingest(source: str, tag: str, cur, upper: int, lookback_s: int) -> int:
    watermark = get_watermark(cur, source, default=upper - lookback_s)
    start = watermark
    if source == "stories":
        refresh_s = int(os.getenv("HN_STORY_REFRESH_HOURS", "48")) * 3600
        start = min(watermark, upper - refresh_s)

    items, t = [], start
    while t < upper:
        nxt = min(t + WINDOW, upper)
        items += fetch_window(tag, t, nxt)
        t = nxt
    if not items:
        print(f"[{source}] nothing new (watermark={watermark})")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{source}_{upper}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it) + "\n")
        cur.execute(f"PUT file://{path} @STG_HN/{source}/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE")

    cur.execute(
        f"""COPY INTO {source.upper()} (payload, _file)
            FROM (SELECT $1, METADATA$FILENAME FROM @STG_HN/{source}/)
            FILE_FORMAT = (FORMAT_NAME = 'FF_JSON') PURGE = TRUE"""
    )
    set_watermark(cur, source, upper)  # only after a successful COPY
    print(f"[{source}] loaded {len(items)} items, watermark -> {upper}")
    return len(items)


def main() -> dict:
    upper = int(time.time()) - 60  # small lag so late-indexed items are not missed
    lookback_s = int(os.getenv("HN_LOOKBACK_HOURS", "24")) * 3600
    conn = connect()
    counts = {}
    try:
        cur = conn.cursor()
        for source, tag in SOURCES.items():
            counts[source] = ingest(source, tag, cur, upper, lookback_s)
    finally:
        conn.close()
    return counts


if __name__ == "__main__":
    main()
