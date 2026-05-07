"""
Great Expectations MCP Server — data validation suite results mock data.

Returns results as produced by a Great Expectations checkpoint run against
financial data pipelines.  Mirrors the GE CheckpointResult / ValidationResult
schema so agents can interpret results directly.
"""

from typing import Any


def get_great_expectations_data() -> dict[str, Any]:
    """
    Return mock Great Expectations checkpoint results for the daily run.
    """
    return {
        "server": "great_expectations_server",
        "source_system": "Great Expectations 0.18.x",
        "checkpoint_name": "daily_financial_data_checkpoint",
        "run_id": "GE-RUN-20260506-0400",
        "run_time": "2026-05-06T04:30:00Z",
        "overall_success": False,
        "validation_results": [
            {
                "suite_name": "orders_fact_suite_v2",
                "datasource": "orders_postgres_prod",
                "batch_id": "BATCH-20260506-001",
                "success": False,
                "statistics": {
                    "evaluated_expectations": 12,
                    "successful_expectations": 8,
                    "unsuccessful_expectations": 4,
                    "success_percent": 66.7,
                },
                "failed_expectations": [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "column": "customer_id",
                        "kwargs": {"mostly": 0.99},
                        "result": {
                            "element_count": 1204,
                            "unexpected_count": 412,
                            "unexpected_percent": 34.22,
                        },
                        "severity": "CRITICAL",
                        "message": "34.22% of customer_id values are null — exceeds 1% threshold.",
                    },
                    {
                        "expectation_type": "expect_table_row_count_to_be_between",
                        "kwargs": {"min_value": 50000, "max_value": 500000},
                        "result": {"observed_value": 1204},
                        "severity": "CRITICAL",
                        "message": "Row count 1,204 is far below expected minimum of 50,000.",
                    },
                    {
                        "expectation_type": "expect_column_to_exist",
                        "column": "discount_amount",
                        "result": {"observed_value": False},
                        "severity": "WARNING",
                        "message": "Column 'discount_amount' missing — schema drift detected.",
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_of_type",
                        "column": "order_amount",
                        "kwargs": {"type_": "NUMERIC"},
                        "result": {"observed_value": "VARCHAR"},
                        "severity": "HIGH",
                        "message": "Column 'order_amount' has type VARCHAR instead of NUMERIC.",
                    },
                ],
                "passed_expectations": [
                    "expect_column_values_to_not_be_null :: order_id",
                    "expect_column_values_to_not_be_null :: order_date",
                    "expect_column_values_to_be_in_set :: status",
                    "expect_column_values_to_be_between :: order_amount (where not null)",
                    "expect_column_pair_values_to_be_equal :: order_id, source_order_id",
                    "expect_compound_columns_to_be_unique :: [order_id, order_date]",
                    "expect_column_values_to_match_regex :: order_id",
                    "expect_table_columns_to_match_ordered_list (partial)",
                ],
            },
            {
                "suite_name": "transactions_tlm_suite_v1",
                "datasource": "tlm_reporting_db",
                "batch_id": "BATCH-20260506-002",
                "success": False,
                "statistics": {
                    "evaluated_expectations": 8,
                    "successful_expectations": 5,
                    "unsuccessful_expectations": 3,
                    "success_percent": 62.5,
                },
                "failed_expectations": [
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "column": "settlement_amount",
                        "kwargs": {"mostly": 1.0},
                        "result": {
                            "element_count": 3,
                            "unexpected_count": 1,
                            "unexpected_percent": 33.3,
                        },
                        "severity": "HIGH",
                        "message": "1 of 3 TLM breaks is missing settlement_amount.",
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_in_set",
                        "column": "break_type",
                        "kwargs": {
                            "value_set": [
                                "UNMATCHED_TRADE",
                                "SETTLEMENT_FAIL",
                                "NOSTRO_BREAK",
                                "CORPORATE_ACTION_BREAK",
                            ]
                        },
                        "result": {
                            "unexpected_list": ["PARTIAL_FILL_DISCREPANCY"],
                            "unexpected_count": 1,
                        },
                        "severity": "WARNING",
                        "message": "Unknown break type 'PARTIAL_FILL_DISCREPANCY' found — possible new event type.",
                    },
                    {
                        "expectation_type": "expect_column_values_to_be_between",
                        "column": "age_hours",
                        "kwargs": {"max_value": 24},
                        "result": {
                            "unexpected_list": [26.0],
                            "unexpected_count": 1,
                        },
                        "severity": "HIGH",
                        "message": "1 break (TLM-BRK-20260506-0002) has aged 26 hours — exceeds 24h SLA.",
                    },
                ],
                "passed_expectations": [
                    "expect_column_values_to_not_be_null :: break_id",
                    "expect_column_values_to_not_be_null :: trade_ref",
                    "expect_column_values_to_not_be_null :: counterparty",
                    "expect_column_values_to_be_in_set :: severity",
                    "expect_table_row_count_to_be_between (1-1000)",
                ],
            },
            {
                "suite_name": "customers_dim_suite_v1",
                "datasource": "customers_postgres_prod",
                "batch_id": "BATCH-20260506-003",
                "success": True,
                "statistics": {
                    "evaluated_expectations": 6,
                    "successful_expectations": 6,
                    "unsuccessful_expectations": 0,
                    "success_percent": 100.0,
                },
                "failed_expectations": [],
                "passed_expectations": [
                    "expect_table_row_count_to_be_between",
                    "expect_column_values_to_not_be_null :: customer_id",
                    "expect_column_values_to_be_unique :: customer_id",
                    "expect_column_values_to_not_be_null :: email",
                    "expect_column_values_to_match_regex :: email",
                    "expect_column_values_to_not_be_null :: account_status",
                ],
            },
        ],
        "summary": {
            "total_suites": 3,
            "passed_suites": 1,
            "failed_suites": 2,
            "total_expectations_evaluated": 26,
            "total_passed": 19,
            "total_failed": 7,
            "critical_failures": 2,
            "high_failures": 3,
            "warning_failures": 2,
            "overall_success_rate_percent": 73.1,
        },
    }
