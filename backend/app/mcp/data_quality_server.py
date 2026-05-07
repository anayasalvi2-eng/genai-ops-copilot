"""
Data Quality MCP Server — returns mock data quality metrics for enterprise pipelines.

In a production system this would connect to Great Expectations, Monte Carlo, or
a custom data observability platform via a secure internal API.
"""

from typing import Any


def get_data_quality_data() -> dict[str, Any]:
    """
    Return a mock data quality report for the current operational window.
    Fields mirror a Great Expectations / Monte Carlo-style schema.
    """
    return {
        "server": "data_quality_server",
        "timestamp": "2026-05-06T08:00:00Z",
        "datasets": [
            {
                "name": "orders_fact",
                "status": "FAILED",
                "checks": [
                    {
                        "rule": "row_count_within_range",
                        "expected": {"min": 50000, "max": 500000},
                        "actual": 1204,
                        "passed": False,
                        "severity": "critical",
                    },
                    {
                        "rule": "null_check.customer_id",
                        "null_percent": 34.2,
                        "threshold_percent": 1.0,
                        "passed": False,
                        "severity": "critical",
                    },
                    {
                        "rule": "schema_drift",
                        "added_columns": [],
                        "removed_columns": ["discount_amount"],
                        "passed": False,
                        "severity": "warning",
                    },
                ],
            },
            {
                "name": "customers_dim",
                "status": "PASSED",
                "checks": [
                    {
                        "rule": "row_count_within_range",
                        "expected": {"min": 1000, "max": 100000},
                        "actual": 42300,
                        "passed": True,
                        "severity": "info",
                    }
                ],
            },
        ],
        "summary": {
            "total_checks": 4,
            "passed": 2,
            "failed": 2,
            "critical_failures": 2,
        },
    }
