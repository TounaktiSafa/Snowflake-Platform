with parsed as (
    select
        payload:objectID::number                        as comment_id,
        payload:story_id::number                        as story_id,
        payload:parent_id::number                       as parent_id,
        payload:story_title::string                     as story_title,
        coalesce(payload:author::string, '[deleted]')   as author,
        trim(regexp_replace(payload:comment_text::string, '<[^>]+>', ' ')) as comment_text,
        to_timestamp_ntz(payload:created_at_i::number)  as created_at,
        _loaded_at
    from {{ source('hn', 'comments') }}
)
select * from parsed
where comment_text is not null and comment_text != ''
qualify row_number() over (partition by comment_id order by _loaded_at desc) = 1
