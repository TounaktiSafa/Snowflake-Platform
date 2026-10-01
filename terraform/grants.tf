locals {
  roles = {
    loader      = snowflake_account_role.loader.name
    transformer = snowflake_account_role.transformer.name
    reporter    = snowflake_account_role.reporter.name
  }
}

# ---- Warehouse usage for all three roles ----
resource "snowflake_grant_privileges_to_account_role" "wh_usage" {
  for_each          = local.roles
  account_role_name = each.value
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.platform.name
  }
}

# ---- LOADER: write into RAW.HN ----
resource "snowflake_grant_privileges_to_account_role" "loader_db" {
  account_role_name = local.roles.loader
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "loader_schema" {
  account_role_name = local.roles.loader
  privileges        = ["USAGE", "CREATE TABLE", "CREATE STAGE", "CREATE FILE FORMAT"]
  on_schema {
    schema_name = snowflake_schema.hn.fully_qualified_name
  }
}

# ---- TRANSFORMER: read RAW, own ANALYTICS ----
resource "snowflake_grant_privileges_to_account_role" "transformer_raw_db" {
  account_role_name = local.roles.transformer
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.raw.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_raw_schema" {
  account_role_name = local.roles.transformer
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.hn.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_raw_tables" {
  account_role_name = local.roles.transformer
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.hn.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_raw_future_tables" {
  account_role_name = local.roles.transformer
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.hn.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "transformer_analytics" {
  account_role_name = local.roles.transformer
  privileges        = ["USAGE", "CREATE SCHEMA"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.analytics.name
  }
}

# ---- REPORTER: read ANALYTICS (schemas created by dbt get future grants later) ----
resource "snowflake_grant_privileges_to_account_role" "reporter_analytics" {
  account_role_name = local.roles.reporter
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.analytics.name
  }
}
