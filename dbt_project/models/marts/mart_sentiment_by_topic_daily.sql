select
    f.date_day,
    e.topic,
    count(*) as comments,
    avg(e.sentiment) as avg_sentiment,
    avg(f.comment_length) as avg_comment_length
from {{ ref('fct_comments') }} as f
inner join {{ ref('comment_enrichment') }} as e on f.comment_id = e.comment_id
group by 1, 2
