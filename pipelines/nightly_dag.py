from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    "scribe_nightly",
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["scribe-check"],
) as dag:
    checks = BashOperator(task_id="quality_checks", bash_command="python /opt/airflow/dags/quality_checks.py")
    stats = BashOperator(task_id="grade_stats", bash_command="python /opt/airflow/dags/grade_stats.py")
    checks >> stats
