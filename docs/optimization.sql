-- Step 10: measure before/after. Run as ACCOUNTADMIN. ACCOUNT_USAGE lags (QUERY_HISTORY ~45 min, METERING up to ~3 h).
USE ROLE ACCOUNTADMIN;

-- 1) Compare experiments (each tagged with DBT_QUERY_TAG=bench_<name>)
SELECT
    query_tag,
    COUNT(*)                                             AS queries,
    ROUND(SUM(total_elapsed_time) / 1000, 1)             AS elapsed_s,
    ROUND(SUM(execution_time) / 1000, 1)                 AS execution_s,
    ROUND(SUM(bytes_scanned) / 1e6, 1)                   AS mb_scanned,
    SUM(partitions_scanned)                              AS partitions_scanned,
    SUM(partitions_total)                                AS partitions_total,
    -- XS = 1 credit/h, S = 2, M = 4 (multiply by the size factor used in that run)
    ROUND(SUM(execution_time) / 1000 / 3600 * 1, 5)      AS est_compute_credits_xs
FROM snowflake.account_usage.query_history
WHERE warehouse_name = 'WH_PLATFORM'
  AND query_tag LIKE 'bench_%'
  AND start_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY query_tag
ORDER BY MIN(start_time);

-- 2) Slowest models in one experiment
SELECT query_tag, LEFT(query_text, 80) AS q, total_elapsed_time / 1000 AS s, bytes_scanned
FROM snowflake.account_usage.query_history
WHERE warehouse_name = 'WH_PLATFORM' AND query_tag = 'bench_baseline'
ORDER BY total_elapsed_time DESC
LIMIT 10;

-- 3) Ground truth for credits (billing includes the 60 s minimum on every resume)
SELECT DATE_TRUNC('day', start_time) AS day, SUM(credits_used_compute) AS compute_credits
FROM snowflake.account_usage.warehouse_metering_history
WHERE warehouse_name = 'WH_PLATFORM'
  AND start_time > DATEADD('day', -14, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1;

-- 4) Clustering check on the fact table (after the clustered run)
SELECT SYSTEM$CLUSTERING_INFORMATION('ANALYTICS.DEV_MARTS.FCT_COMMENTS', '(DATE_DAY)');
