# REPORTER can read everything dbt creates in ANALYTICS (future schemas / tables), used by the Streamlit app.
resource "snowflake_grant_privileges_to_account_role" "reporter_future_schemas" {
  account_role_name = snowflake_account_role.reporter.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = snowflake_database.analytics.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "reporter_future_tables" {
  account_role_name = snowflake_account_role.reporter.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = snowflake_database.analytics.name
    }
  }
}

# The pipeline service user may also assume REPORTER (dashboard connects with it)
resource "snowflake_grant_account_role" "pipeline_reporter" {
  role_name = snowflake_account_role.reporter.name
  user_name = snowflake_service_user.pipeline.name
}
