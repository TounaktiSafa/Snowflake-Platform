{{ config(materialized='incremental', unique_key='comment_id') }}
{#
  Scores ONLY new comments (incremental) -> keeps LLM credit cost proportional to new data.
  backend = cortex : in-warehouse Snowflake Cortex (needs Cortex enabled on the account)
  backend = local  : VADER + keyword topics computed by ingestion/score_local.py (works on trial/standard accounts)
  switch with:  dbt build --vars '{enrichment_backend: cortex}'
#}
{% set backend = var('enrichment_backend', 'local') %}

{% if backend == 'cortex' %}

    select
        comment_id,
        'cortex' as scored_by,
        snowflake.cortex.sentiment(comment_text) as sentiment,
        snowflake.cortex.classify_text(comment_text, ['data', 'ai', 'career', 'other']):label::string as topic,
        current_timestamp() as scored_at
    from {{ ref('stg_comments') }}
    {% if is_incremental() %}
        where comment_id not in (select comment_id from {{ this }})
    {% endif %}

{% else %}

    select
        comment_id,
        sentiment,
        topic,
        scored_by,
        scored_at
    from {{ source('hn', 'comment_scores') }}
    {% if is_incremental() %}
        where comment_id not in (select comment_id from {{ this }})
    {% endif %}
    qualify row_number() over (partition by comment_id order by scored_at desc) = 1

{% endif %}
