# ---------- Cost safety ----------
resource "snowflake_warehouse" "platform" {
  name                = "WH_PLATFORM"
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = "true"
  initially_suspended = true

  lifecycle {
    ignore_changes = [resource_monitor]
  }
}

# ---------- Databases & schemas ----------
resource "snowflake_database" "raw" {
  name = "RAW"
}

resource "snowflake_schema" "hn" {
  database = snowflake_database.raw.name
  name     = "HN"
}

resource "snowflake_database" "analytics" {
  name = "ANALYTICS"
}

# ---------- Roles ----------
resource "snowflake_account_role" "loader" {
  name = "LOADER"
}

resource "snowflake_account_role" "transformer" {
  name = "TRANSFORMER"
}

resource "snowflake_account_role" "reporter" {
  name = "REPORTER"
}

# ---------- Service user ----------
resource "snowflake_service_user" "pipeline" {
  name              = "SVC_PIPELINE"
  default_role      = snowflake_account_role.transformer.name
  default_warehouse = snowflake_warehouse.platform.name
  rsa_public_key    = var.service_user_public_key
}

resource "snowflake_grant_account_role" "pipeline_loader" {
  role_name = snowflake_account_role.loader.name
  user_name = snowflake_service_user.pipeline.name
}

resource "snowflake_grant_account_role" "pipeline_transformer" {
  role_name = snowflake_account_role.transformer.name
  user_name = snowflake_service_user.pipeline.name
}

# Let SYSADMIN see everything these roles own
resource "snowflake_grant_account_role" "loader_to_sysadmin" {
  role_name        = snowflake_account_role.loader.name
  parent_role_name = "SYSADMIN"
}
resource "snowflake_grant_account_role" "transformer_to_sysadmin" {
  role_name        = snowflake_account_role.transformer.name
  parent_role_name = "SYSADMIN"
}
resource "snowflake_grant_account_role" "reporter_to_sysadmin" {
  role_name        = snowflake_account_role.reporter.name
  parent_role_name = "SYSADMIN"
}
