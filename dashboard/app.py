"""Streamlit dashboard: sentiment by topic over time. Run: streamlit run dashboard/app.py"""
import os

import pandas as pd
import snowflake.connector
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
SCHEMA = os.getenv("DASHBOARD_SCHEMA", "DEV_MARTS")   # use MARTS once deployed to prod

st.set_page_config(page_title="HN sentiment by topic", layout="wide")
st.title("Hacker News: comment sentiment by topic")


@st.cache_resource
def conn():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key_file=os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        role="REPORTER",
        database="ANALYTICS",
        schema=SCHEMA,
    )


@st.cache_data(ttl=900)  # 15 min cache keeps warehouse wake-ups (credits) low
def load() -> pd.DataFrame:
    cur = conn().cursor()
    cur.execute(
        "SELECT date_day, topic, comments, avg_sentiment FROM mart_sentiment_by_topic_daily ORDER BY date_day"
    )
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    df["date_day"] = pd.to_datetime(df["date_day"])
    return df


df = load()
if df.empty:
    st.warning("No data yet: run the pipeline first.")
    st.stop()

topics = st.multiselect("Topics", sorted(df.topic.unique()), default=sorted(df.topic.unique()))
d = df[df.topic.isin(topics)]

c1, c2, c3 = st.columns(3)
c1.metric("Comments scored", f"{int(d.comments.sum()):,}")
c2.metric("Avg sentiment", f"{(d.avg_sentiment * d.comments).sum() / max(d.comments.sum(), 1):+.3f}")
c3.metric("Days covered", d.date_day.nunique())

st.subheader("Average sentiment per day")
st.line_chart(d.pivot(index="date_day", columns="topic", values="avg_sentiment"))
st.subheader("Comment volume per day")
st.bar_chart(d.pivot(index="date_day", columns="topic", values="comments"))
st.caption("Sentiment ranges from -1 (negative) to +1 (positive).")
