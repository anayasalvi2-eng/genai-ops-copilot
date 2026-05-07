"""
Pipeline MCP Server — returns mock pipeline run status for enterprise data pipelines.

In a production system this would connect to Airflow, Prefect, Dagster, or Azure
Data Factory via their REST APIs.
"""

from typing import Any


def get_pipeline_data() -> dict[str, Any]:
    """
    Return mock pipeline execution data for the last 24 hours.
    """
    return {
        "server": "pipeline_server",
        "timestamp": "2026-05-06T08:05:00Z",
        "pipelines": [
            {
                "id": "pl-orders-ingestion-001",
                "name": "orders_ingestion_daily",
                "status": "FAILED",
                "last_run": "2026-05-06T04:00:00Z",
                "duration_seconds": 47,
                "expected_duration_seconds": 1800,
                "error": {
                    "type": "SourceConnectionTimeout",
                    "message": "Connection to source DB timed out after 30 s",
                    "task": "extract_orders_raw",
                },
                "retries": 3,
                "retry_success": False,
            },
            {
                "id": "pl-customers-sync-002",
                "name": "customers_dim_sync",
                "status": "SUCCESS",
                "last_run": "2026-05-06T03:30:00Z",
                "duration_seconds": 210,
                "expected_duration_seconds": 300,
                "error": None,
                "retries": 0,
                "retry_success": None,
            },
            {
                "id": "pl-revenue-aggregation-003",
                "name": "revenue_daily_aggregation",
                "status": "BLOCKED",
                "last_run": None,
                "duration_seconds": None,
                "expected_duration_seconds": 600,
                "error": {
                    "type": "UpstreamDependencyFailed",
                    "message": "Blocked by failed upstream: orders_ingestion_daily",
                    "task": "wait_for_orders",
                },
                "retries": 0,
                "retry_success": None,
            },
        ],
        "summary": {
            "total": 3,
            "success": 1,
            "failed": 1,
            "blocked": 1,
        },
    }
