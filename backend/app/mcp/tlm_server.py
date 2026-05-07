"""
TLM MCP Server — SmartStream Transaction Lifecycle Management mock data.

Simulates unmatched trades, settlement fails, and nostro breaks that would
be surfaced by a SmartStream TLM reconciliation run.
"""

from typing import Any


def get_tlm_data() -> dict[str, Any]:
    """
    Return a mock TLM reconciliation report for the current settlement date.
    SD = 2026-05-06 (T+2 for trades booked 2026-05-04).
    """
    return {
        "server": "tlm_server",
        "source_system": "SmartStream TLM 7.4",
        "settlement_date": "2026-05-06",
        "report_generated_at": "2026-05-06T07:30:00Z",
        "breaks": [
            {
                "break_id": "TLM-BRK-20260506-0001",
                "type": "UNMATCHED_TRADE",
                "status": "OPEN",
                "severity": "HIGH",
                "trade_ref": "TRD-2026050412345",
                "asset_class": "Fixed Income",
                "instrument": "US Treasury 4.25% 2028",
                "isin": "US912810TM56",
                "counterparty": "Goldman Sachs International",
                "our_side": {
                    "quantity": 10_000_000,
                    "price": 98.75,
                    "currency": "USD",
                    "settlement_amount": 9_875_000.00,
                    "custodian": "BNY Mellon",
                },
                "counterparty_side": None,
                "age_hours": 4.5,
                "sla_breach": False,
                "sla_deadline": "2026-05-06T12:00:00Z",
                "comments": "Counterparty confirmation not received. Chaser sent at 07:15.",
            },
            {
                "break_id": "TLM-BRK-20260506-0002",
                "type": "SETTLEMENT_FAIL",
                "status": "OPEN",
                "severity": "CRITICAL",
                "trade_ref": "TRD-2026050498712",
                "asset_class": "Equity",
                "instrument": "Apple Inc",
                "isin": "US0378331005",
                "counterparty": "Morgan Stanley & Co. LLC",
                "our_side": {
                    "quantity": 50_000,
                    "price": 212.40,
                    "currency": "USD",
                    "settlement_amount": 10_620_000.00,
                    "custodian": "State Street",
                },
                "counterparty_side": {
                    "quantity": 50_000,
                    "price": 212.40,
                    "currency": "USD",
                    "settlement_amount": 10_620_000.00,
                    "custodian": "JPMorgan",
                },
                "fail_reason": "INSUFFICIENT_SECURITIES",
                "age_hours": 26.0,
                "sla_breach": True,
                "penalty_accruing": True,
                "estimated_penalty_usd": 5_310.00,
                "comments": "Client short on AAPL position. Auto-borrow failed — no available lenders.",
            },
            {
                "break_id": "TLM-BRK-20260506-0003",
                "type": "NOSTRO_BREAK",
                "status": "INVESTIGATING",
                "severity": "MEDIUM",
                "trade_ref": "TRD-2026050481234",
                "asset_class": "FX",
                "instrument": "EUR/USD",
                "counterparty": "Deutsche Bank AG",
                "our_ledger_balance_usd": 5_000_000.00,
                "custodian_statement_balance_usd": 4_750_000.00,
                "variance_usd": 250_000.00,
                "age_hours": 8.0,
                "sla_breach": False,
                "comments": "Variance of $250k identified. Possible missing FX swap leg from yesterday.",
            },
        ],
        "summary": {
            "total_breaks": 3,
            "critical": 1,
            "high": 1,
            "medium": 1,
            "total_exposure_usd": 20_745_000.00,
            "sla_breached_count": 1,
            "penalty_accruing_count": 1,
            "estimated_total_penalty_usd": 5_310.00,
        },
    }
