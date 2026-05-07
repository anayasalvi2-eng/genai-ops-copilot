"""
PACT MCP Server — exception case management mock data.

PACT is an internal case management platform used by operations teams to
investigate, track, and resolve exceptions raised by TLM breaks, DQ failures,
and settlement issues.  Each case links back to a TLM break or upstream event.
"""

from typing import Any


def get_pact_data() -> dict[str, Any]:
    """
    Return mock PACT cases open as of the current operational day.
    """
    return {
        "server": "pact_server",
        "source_system": "PACT Case Management v3.1",
        "report_generated_at": "2026-05-06T08:00:00Z",
        "cases": [
            {
                "case_id": "PACT-2026-004421",
                "title": "Settlement Fail — AAPL TRD-2026050498712",
                "category": "Settlement Exception",
                "priority": "P1",
                "status": "IN_PROGRESS",
                "linked_break": "TLM-BRK-20260506-0002",
                "assigned_to": "ops-settlements-team",
                "created_at": "2026-05-06T06:00:00Z",
                "sla_due_at": "2026-05-06T14:00:00Z",
                "sla_status": "AT_RISK",
                "owner_desk": "Equity Settlement",
                "root_cause_hypothesis": "Client short position; auto-borrow exhausted.",
                "actions_taken": [
                    "Contacted stock loan desk at 06:30 — no available borrows.",
                    "Manual borrow request sent to 3 prime brokers at 07:00.",
                    "Client notified of pending fail at 07:30.",
                ],
                "next_action": "Await prime broker responses by 10:00.",
                "financial_impact_usd": 10_620_000.00,
                "penalty_risk_usd": 5_310.00,
            },
            {
                "case_id": "PACT-2026-004418",
                "title": "Unmatched Trade — UST 4.25% 2028 TRD-2026050412345",
                "category": "Matching Exception",
                "priority": "P2",
                "status": "OPEN",
                "linked_break": "TLM-BRK-20260506-0001",
                "assigned_to": "ops-fixed-income-team",
                "created_at": "2026-05-06T07:00:00Z",
                "sla_due_at": "2026-05-06T12:00:00Z",
                "sla_status": "ON_TRACK",
                "owner_desk": "Fixed Income Settlement",
                "root_cause_hypothesis": "Counterparty may have booked under different reference.",
                "actions_taken": [
                    "Chaser email sent to GS Ops at 07:15.",
                ],
                "next_action": "Escalate to GS relationship manager if no response by 09:00.",
                "financial_impact_usd": 9_875_000.00,
                "penalty_risk_usd": 0.00,
            },
            {
                "case_id": "PACT-2026-004415",
                "title": "Nostro Break — EUR/USD $250k variance vs Deutsche Bank",
                "category": "Reconciliation Break",
                "priority": "P2",
                "status": "INVESTIGATING",
                "linked_break": "TLM-BRK-20260506-0003",
                "assigned_to": "ops-fx-recon-team",
                "created_at": "2026-05-06T06:30:00Z",
                "sla_due_at": "2026-05-06T17:00:00Z",
                "sla_status": "ON_TRACK",
                "owner_desk": "FX Operations",
                "root_cause_hypothesis": "Missing swap second leg from 2026-05-05.",
                "actions_taken": [
                    "Pulled SWIFT MT202 messages — reviewing for missing entries.",
                    "Requested Deutsche Bank nostro statement reconciliation report.",
                ],
                "next_action": "Cross-reference SWIFT messages with ledger entries.",
                "financial_impact_usd": 250_000.00,
                "penalty_risk_usd": 0.00,
            },
            {
                "case_id": "PACT-2026-004390",
                "title": "Data Quality Alert — orders_fact null rate breach",
                "category": "Data Quality Exception",
                "priority": "P2",
                "status": "OPEN",
                "linked_break": None,
                "linked_ge_suite": "orders_fact_suite_v2",
                "assigned_to": "data-engineering",
                "created_at": "2026-05-06T05:00:00Z",
                "sla_due_at": "2026-05-06T13:00:00Z",
                "sla_status": "ON_TRACK",
                "owner_desk": "Data Platform",
                "root_cause_hypothesis": "ETL schema change dropped customer_id mapping.",
                "actions_taken": [
                    "Pipeline failure confirmed — extract stage timed out.",
                    "Partial load with nulls was committed before rollback logic triggered.",
                ],
                "next_action": "Rollback partial load; re-run pipeline after source DB recovery.",
                "financial_impact_usd": 0.00,
                "penalty_risk_usd": 0.00,
            },
        ],
        "summary": {
            "total_cases": 4,
            "open": 2,
            "in_progress": 1,
            "investigating": 1,
            "p1_count": 1,
            "p2_count": 3,
            "sla_at_risk": 1,
            "total_financial_exposure_usd": 20_745_000.00,
            "total_penalty_risk_usd": 5_310.00,
        },
    }
