"""Local enrichment fallback (no Cortex): VADER sentiment + keyword topics.

Scores ONLY comments that are not yet in RAW.HN.COMMENT_SCORES (incremental, like the Cortex path).
Run: python -m ingestion.score_local
"""
import os
import re

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ingestion.hn_ingest import connect

TOPICS = {
    "ai": r"\b(ai|llms?|gpt|openai|anthropic|claude|gemini|chatgpt|neural|machine learning|ml|agents?|transformers?|inference|gpu|copilot|embeddings?|rag)\b",
    "data": r"\b(data|database|sql|postgres(ql)?|mysql|warehouse|pipeline|etl|elt|dataset|analytics|snowflake|spark|bigquery|duckdb|dbt|kafka|schema)\b",
    "career": r"\b(job|jobs|hiring|hired|salary|interview|career|resume|layoffs?|remote|manager|promotion|recruiter|offer|engineers?)\b",
}
TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}
TAG = re.compile(r"<[^>]+>")
BATCH = 5000

SELECT_NEW = """
SELECT payload:objectID::number AS comment_id, payload:comment_text::string AS text
FROM COMMENTS c
WHERE payload:comment_text IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM COMMENT_SCORES s WHERE s.comment_id = c.payload:objectID::number)
QUALIFY ROW_NUMBER() OVER (PARTITION BY payload:objectID::number ORDER BY _loaded_at DESC) = 1
{limit}
"""


def classify(text: str) -> str:
    hits = {k: len(rx.findall(text)) for k, rx in TOPIC_RE.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] > 0 else "other"


def main() -> int:
    limit = os.getenv("SCORE_BATCH_LIMIT")
    sql = SELECT_NEW.format(limit=f"LIMIT {int(limit)}" if limit else "")
    conn = connect()
    analyzer = SentimentIntensityAnalyzer()
    try:
        cur = conn.cursor()
        rows = cur.execute(sql).fetchall()
        if not rows:
            print("[scoring] nothing new to score")
            return 0
        out = []
        for comment_id, text in rows:
            clean = TAG.sub(" ", text or "").strip()
            if not clean:
                continue
            out.append((comment_id, analyzer.polarity_scores(clean)["compound"], classify(clean), "local_vader"))
        for i in range(0, len(out), BATCH):
            cur.executemany(
                "INSERT INTO COMMENT_SCORES (comment_id, sentiment, topic, scored_by) VALUES (%s, %s, %s, %s)",
                out[i : i + BATCH],
            )
        print(f"[scoring] scored {len(out)} new comments")
        return len(out)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
