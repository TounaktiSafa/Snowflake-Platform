{# Comments can point at stories older than our ingestion window: keep a stub row so the star schema stays complete #}
with ingested as (
    select
        story_id,
        title,
        url,
        author,
        points,
        num_comments,
        created_at,
        true as is_ingested
    from {{ ref('stg_stories') }}
),

stubs as (
    select
        story_id,
        max(story_title) as title,
        null::string as url,
        null::string as author,
        null::number as points,
        null::number as num_comments,
        null::timestamp_ntz as created_at,
        false as is_ingested
    from {{ ref('stg_comments') }}
    where story_id not in (select story_id from ingested)
    group by story_id
)

select * from ingested
union all
select * from stubs
