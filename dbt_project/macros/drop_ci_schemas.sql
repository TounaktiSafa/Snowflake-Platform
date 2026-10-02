{# usage: dbt run-operation drop_ci_schemas  (drops the schemas of the current DBT_SCHEMA, used by CI cleanup) #}
{% macro drop_ci_schemas() %}
  {% for suffix in ['', '_staging', '_marts', '_snapshots'] %}
    {% do run_query('drop schema if exists ' ~ target.database ~ '.' ~ target.schema ~ suffix ~ ' cascade') %}
    {{ log('dropped ' ~ target.schema ~ suffix, info=True) }}
  {% endfor %}
{% endmacro %}
