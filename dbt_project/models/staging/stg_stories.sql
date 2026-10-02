with parsed as (
    select
        payload:objectID::number                        as story_id,
        payload:title::string                           as title,
        payload:url::string                             as url,
        coalesce(payload:author::string, '[deleted]')   as author,
        payload:points::number                          as points,
        payload:num_comments::number                    as num_comments,
        to_timestamp_ntz(payload:created_at_i::number)  as created_at,
        _loaded_at
    from {{ source('hn', 'stories') }}
)
select * from parsed
qualify row_number() over (partition by story_id order by _loaded_at desc) = 1
