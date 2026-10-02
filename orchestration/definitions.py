"""Dagster definitions. Run from the repo root:  dagster dev -f orchestration/definitions.py

Graph:  hn ingestion (+ blocking Soda gate) -> local scoring -> dbt (staging -> marts -> snapshot -> tests)
"""
import os
import subprocess
import sys
from pathlib import Path

import requests
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetKey,
    AssetSelection,
    AssetSpec,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    Definitions,
    MaterializeResult,
    RunFailureSensorContext,
    ScheduleDefinition,
    define_asset_job,
    multi_asset,
    run_failure_sensor,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from ingestion import hn_ingest, score_local  # noqa: E402

STORIES = AssetKey(["hn", "stories"])        # same keys dbt uses for source('hn', ...)
COMMENTS = AssetKey(["hn", "comments"])
SCORES = AssetKey(["hn", "comment_scores"])


def run_soda() -> tuple[bool, str]:
    soda = os.getenv("SODA_BIN", str(ROOT / ".venv-soda" / "bin" / "soda"))
    proc = subprocess.run(
        [soda, "scan", "-d", "hn_raw", "-c", str(ROOT / "soda/configuration.yml"),
         str(ROOT / "soda/checks/raw_checks.yml")],
        capture_output=True, text=True,
    )
    ok = proc.returncode in (0, 1)   # 0 = pass, 1 = warn, 2 = fail, 3 = error
    return ok, (proc.stdout + proc.stderr)[-3000:]


@multi_asset(
    specs=[AssetSpec(STORIES), AssetSpec(COMMENTS)],
    check_specs=[AssetCheckSpec("soda_raw_checks", asset=COMMENTS, blocking=True)],
    description="Ingest new HN items to RAW, then run the Soda gate (blocks downstream on failure).",
)
def hn_raw(context):
    counts = hn_ingest.main()
    yield MaterializeResult(asset_key=STORIES, metadata={"rows_loaded": counts["stories"]})
    yield MaterializeResult(asset_key=COMMENTS, metadata={"rows_loaded": counts["comments"]})
    ok, log = run_soda()
    yield AssetCheckResult(
        check_name="soda_raw_checks", asset_key=COMMENTS, passed=ok,
        severity=AssetCheckSeverity.ERROR, metadata={"soda_output": log},
    )


@multi_asset(
    specs=[AssetSpec(SCORES, deps=[COMMENTS])],
    description="Score only NEW comments (local VADER); dbt reads RAW.HN.COMMENT_SCORES.",
)
def hn_comment_scores(context):
    n = score_local.main()
    yield MaterializeResult(asset_key=SCORES, metadata={"comments_scored": n})


dbt_project = DbtProject(project_dir=ROOT / "dbt_project", profiles_dir=ROOT / "dbt_project")
dbt_project.prepare_if_dev()


@dbt_assets(manifest=dbt_project.manifest_path)
def hn_dbt_assets(context, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


daily_job = define_asset_job("daily_pipeline", selection=AssetSelection.all())
daily_schedule = ScheduleDefinition(
    job=daily_job, cron_schedule="0 5 * * *", execution_timezone="UTC",
    default_status=DefaultScheduleStatus.RUNNING,
)


@run_failure_sensor(default_status=DefaultSensorStatus.RUNNING)
def notify_on_failure(context: RunFailureSensorContext):
    msg = f":x: Dagster run failed: job={context.dagster_run.job_name} run_id={context.dagster_run.run_id}\n{context.failure_event.message}"
    url = os.getenv("SLACK_WEBHOOK_URL")
    if url:
        requests.post(url, json={"text": msg}, timeout=10)
    context.log.error(msg)


defs = Definitions(
    assets=[hn_raw, hn_comment_scores, hn_dbt_assets],
    jobs=[daily_job],
    schedules=[daily_schedule],
    sensors=[notify_on_failure],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
