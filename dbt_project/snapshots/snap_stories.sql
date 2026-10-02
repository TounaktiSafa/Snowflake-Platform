{% snapshot snap_stories %}
{{
    config(
        schema='snapshots',
        unique_key='story_id',
        strategy='check',
        check_cols=['title', 'points', 'num_comments']
    )
}}
{# SCD2: keeps the history of a story's score and comment count as ingestion re-fetches recent stories #}
select story_id, title, url, author, points, num_comments, created_at
from {{ ref('stg_stories') }}
{% endsnapshot %}
