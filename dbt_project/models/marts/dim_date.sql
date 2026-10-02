with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2024-01-01' as date)",
        end_date="dateadd(year, 1, current_date())"
    ) }}
)
select
    cast(date_day as date)              as date_day,
    year(date_day)                      as year,
    month(date_day)                     as month,
    dayofweekiso(date_day)              as day_of_week,
    dayname(date_day)                   as day_name,
    dayofweekiso(date_day) in (6, 7)    as is_weekend
from spine
