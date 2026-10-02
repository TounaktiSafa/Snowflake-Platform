{{ config(materialized='incremental', unique_key='comment_id') }}

select
    comment_id,
    story_id,
    author,
    cast(created_at as date)    as date_day,
    created_at,
    length(comment_text)        as comment_length,
    _loaded_at
from {{ ref('stg_comments') }}
{% if is_incremental() %}
where _loaded_at > (select max(_loaded_at) from {{ this }})
{% endif %}
