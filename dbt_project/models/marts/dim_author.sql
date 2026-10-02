with authors as (
    select author, created_at from {{ ref('stg_comments') }}
    union all
    select author, created_at from {{ ref('stg_stories') }}
)
select
    author,
    min(created_at) as first_seen_at,
    max(created_at) as last_seen_at,
    count(*)        as items_seen
from authors
group by author
