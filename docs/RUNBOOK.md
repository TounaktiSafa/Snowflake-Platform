# Runbook: how to run each step

All commands run from the repo root `~/snowflake-platform` in WSL unless stated. `.env` lives at the repo root:

```
SNOWFLAKE_ACCOUNT=VSKEMDN-VS76764
SNOWFLAKE_USER=SVC_PIPELINE
SNOWFLAKE_PRIVATE_KEY_FILE=/home/user/snowflake-platform/terraform/keys/svc_pipeline.p8
SNOWFLAKE_WAREHOUSE=WH_PLATFORM
HN_LOOKBACK_HOURS=24
```
Load it into your shell when a tool does not read it itself: `set -a; source .env; set +a`

---
## 0. Install
```bash
source .venv/bin/activate
pip install --upgrade pip
pip install --prefer-binary -r requirements/requirements.txt
python3 -m venv .venv-soda && .venv-soda/bin/pip install -r requirements/requirements-soda.txt
```
If pip looks frozen it is usually backtracking or building a package: re-run with `-v`. Slow network is normal on WSL; wait for it.

## 1. Connection check (must pass before anything else)
```bash
set -a; source .env; set +a
python - <<'PY'
from ingestion.hn_ingest import connect
c = connect(); print(c.cursor().execute("select current_user(), current_role(), current_warehouse()").fetchone())
PY
```
Expected: `('SVC_PIPELINE', 'LOADER', 'WH_PLATFORM')`. `JWT token is invalid` = key mismatch or WSL clock skew (see Troubleshooting).

## 2. Terraform (adds REPORTER access for the dashboard)
```bash
cd terraform
terraform fmt && terraform validate && terraform plan   # expect ~4 to add (reporter.tf)
terraform apply
```
Run it **before** the first `dbt build` so the future-grants exist when dbt creates tables.

## 3. Ingestion
```bash
python -m ingestion.setup_raw                          # creates tables/stage/file format (idempotent)
HN_LOOKBACK_HOURS=2 python -m ingestion.hn_ingest      # first small run
python -m ingestion.hn_ingest                          # second run: only new items (+ 48 h story refresh)
```
Verify in Snowflake: `SELECT COUNT(*) FROM RAW.HN.COMMENTS;` and `SELECT * FROM RAW.HN.INGESTION_STATE;`
For realistic benchmark volume, once: `HN_LOOKBACK_HOURS=72 python -m ingestion.hn_ingest` (several minutes).

## 4. Local enrichment (Cortex fallback)
```bash
python -m ingestion.score_local        # scores only comments missing from RAW.HN.COMMENT_SCORES
python -m ingestion.score_local        # second run: "nothing new to score"
```

## 5. dbt
```bash
cd dbt_project
set -a; source ../.env; set +a
dbt deps --profiles-dir .
dbt debug --profiles-dir .
dbt source freshness --profiles-dir .
dbt build --profiles-dir .                    # models + snapshot + tests
dbt build --profiles-dir . --vars '{enrichment_backend: cortex}'   # only on an account with Cortex
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .   # lineage graph -> screenshot for README
```
Dev schemas: `ANALYTICS.DEV_STAGING`, `DEV_MARTS`, `DEV_SNAPSHOTS`. Prod (`--target prod`): `STAGING`, `MARTS`, `SNAPSHOTS`.
The SCD2 snapshot only shows history after two ingestion runs saw different `points`/`num_comments` for a story: run the pipeline on two different days, then `SELECT * FROM ANALYTICS.DEV_SNAPSHOTS.SNAP_STORIES WHERE dbt_valid_to IS NOT NULL;`

## 6. Soda quality gate
```bash
set -a; source .env; set +a
.venv-soda/bin/soda test-connection -d hn_raw -c soda/configuration.yml
.venv-soda/bin/soda scan -d hn_raw -c soda/configuration.yml soda/checks/raw_checks.yml
```
Exit code 0 = pass, 1 = warn, 2 = fail. Dagster treats 2/3 as a failed blocking check.
Prove the gate works: temporarily change `row_count > 0` to `row_count > 999999999`, run the Dagster job, and watch the downstream assets stay unmaterialized.

## 7. Dagster
```bash
set -a; source .env; set +a
export DAGSTER_HOME=$PWD/dagster_home && mkdir -p $DAGSTER_HOME
dagster dev -f orchestration/definitions.py          # UI on http://localhost:3000
```
In the UI: Assets -> select all -> Materialize. Order: `hn_raw` (+ Soda check) -> `hn_comment_scores` -> dbt assets.
Schedule `daily_pipeline` runs at 05:00 UTC (turn it on under Automation; the daemon runs inside `dagster dev`).
Failure alert: set `SLACK_WEBHOOK_URL` in `.env` for Slack, otherwise it logs to the run.
If `dagster dev` complains about the dbt manifest, run `cd dbt_project && dbt parse --profiles-dir .` once.

## 8. Streamlit dashboard
```bash
set -a; source .env; set +a
streamlit run dashboard/app.py          # http://localhost:8501
```
Uses role `REPORTER`. Dev data lives in `DEV_MARTS`; after a prod deploy: `DASHBOARD_SCHEMA=MARTS streamlit run dashboard/app.py`.

## 9. CI/CD (GitHub Actions)
1. Create the GitHub repo and push:
   ```bash
   git remote add origin git@github.com:TounaktiSafa/snowflake-platform.git
   git add -A && git commit -m "feat: dbt, enrichment, dagster, soda, ci" && git push -u origin main
   ```
2. Repo -> Settings -> Secrets and variables -> Actions: add `SNOWFLAKE_ACCOUNT` (`VSKEMDN-VS76764`), `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY` (full contents of the `.p8` file).
   Better practice: create a dedicated CI service user with its own key and only the `TRANSFORMER` role.
3. Work on a branch, open a PR: `lint` and `dbt-ci` run. Merge to `main`: `Deploy` builds prod and caches the manifest, which later PRs use for `state:modified+`.
4. Settings -> Branches: require the CI checks before merging.
Remote state (to automate `terraform apply` later): move state to a remote backend (GCS bucket or Terraform Cloud) before adding an apply job.

## 10. Optimize and measure
```bash
cd dbt_project; set -a; source ../.env; set +a
DBT_QUERY_TAG=bench_baseline        dbt build --profiles-dir . --full-refresh
# experiment A: clustering -> add cluster_by=['date_day'] to fct_comments config
DBT_QUERY_TAG=bench_clustered       dbt build --profiles-dir . --full-refresh
# experiment B: materialization -> set stg_comments to +materialized: table in dbt_project.yml
DBT_QUERY_TAG=bench_stg_table       dbt build --profiles-dir . --full-refresh
# experiment C: warehouse size -> as ACCOUNTADMIN: ALTER WAREHOUSE WH_PLATFORM SET WAREHOUSE_SIZE = SMALL;
DBT_QUERY_TAG=bench_small_wh        dbt build --profiles-dir . --full-refresh
# then restore XS (Terraform owns the size): ALTER WAREHOUSE WH_PLATFORM SET WAREHOUSE_SIZE = XSMALL;
```
Wait ~1 h, then run `docs/optimization.sql` and paste the numbers in the README cost table. With small data, clustering gains are small: report that honestly, with the partitions-scanned numbers.

## 11. Publish checklist
Architecture diagram (README mermaid renders on GitHub), dbt lineage screenshot, dashboard screenshot, filled cost table, `terraform destroy` + `docs/teardown.sql`.

---
## Troubleshooting
- **`JWT token is invalid`**: compare fingerprints.
  Local: `openssl rsa -in terraform/keys/svc_pipeline.p8 -pubout -outform DER | openssl dgst -sha256 -binary | openssl enc -base64`
  Snowflake: `DESC USER SVC_PIPELINE;` -> `RSA_PUBLIC_KEY_FP` (`SHA256:...`). They must match.
  If not: put the right public key into `terraform.tfvars` (`service_user_public_key`) and `terraform apply`.
  If they match, check the WSL clock: `date -u` vs real UTC; fix with `sudo hwclock -s` (or restart WSL: `wsl --shutdown` from PowerShell).
- **`insufficient privileges ... SELECT`** on a RAW table created before the grants: as ACCOUNTADMIN `GRANT SELECT ON ALL TABLES IN SCHEMA RAW.HN TO ROLE TRANSFORMER;`
- **Soda cannot read the key**: your Soda version may not support `private_key_path`; use `private_key: ${SNOWFLAKE_PRIVATE_KEY}` with the key text in an env var instead.
- **Warehouse never suspends**: `SHOW WAREHOUSES;` and check `auto_suspend = 60` and `state`.
