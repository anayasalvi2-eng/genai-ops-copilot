"""
Incident MCP Server — returns mock active incidents from the enterprise ITSM platform.

In a production system this would connect to PagerDuty, ServiceNow, or OpsGenie.
"""

from typing import Any


def get_incident_data() -> dict[str, Any]:
    """
    Return a mock list of active incidents correlated with data pipeline operations.
    """
    return {
        "server": "incident_server",
        "timestamp": "2026-05-06T08:10:00Z",
        "incidents": [
            {
                "id": "INC-20260506-0042",
                "title": "Data pipeline failure — orders_ingestion_daily",
                "severity": "P1",
                "status": "OPEN",
                "created_at": "2026-05-06T04:15:00Z",
                "affected_services": ["orders-service", "revenue-reporting", "BI-dashboard"],
                "assigned_team": "data-platform-oncall",
                "description": (
                    "The orders ingestion pipeline failed at the extract stage due to a "
                    "source DB connection timeout. Downstream revenue aggregation is blocked. "
                    "Revenue dashboard shows stale data from yesterday."
                ),
                "timeline": [
                    {"time": "2026-05-06T04:00:00Z", "event": "Pipeline run started"},
                    {"time": "2026-05-06T04:00:47Z", "event": "SourceConnectionTimeout raised"},
                    {"time": "2026-05-06T04:01:00Z", "event": "3 automatic retries exhausted"},
                    {"time": "2026-05-06T04:15:00Z", "event": "PagerDuty alert triggered"},
                ],
            },
            {
                "id": "INC-20260506-0038",
                "title": "Data quality check failed — orders_fact high null rate",
                "severity": "P2",
                "status": "INVESTIGATING",
                "created_at": "2026-05-06T05:00:00Z",
                "affected_services": ["data-quality-platform", "analytics"],
                "assigned_team": "data-engineering",
                "description": (
                    "Null rate on customer_id column in orders_fact spiked to 34.2 %, "
                    "well above the 1 % SLA threshold. Schema drift detected — "
                    "column discount_amount is missing from the latest load."
                ),
                "timeline": [
                    {"time": "2026-05-06T05:00:00Z", "event": "DQ check failure detected"},
                    {"time": "2026-05-06T05:10:00Z", "event": "Alert sent to #data-incidents Slack channel"},
                    {"time": "2026-05-06T05:45:00Z", "event": "Engineer began investigation"},
                ],
            },
        ],
        "summary": {
            "total_open": 2,
            "p1_count": 1,
            "p2_count": 1,
        },
    }
