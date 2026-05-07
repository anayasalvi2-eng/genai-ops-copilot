"""
Notification MCP Server — email notification dispatcher for incident resolutions.

Simulates sending resolution emails to stakeholders when PACT cases or TLM breaks
are resolved.  In production this would integrate with SendGrid, AWS SES, or the
corporate Exchange/SMTP relay via a secure internal API.

NOTE: No emails are actually sent here — all operations are mock/logged only.
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory notification log (resets on server restart — use a DB in production)
# ---------------------------------------------------------------------------
_notification_log: list[dict[str, Any]] = []


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Notification templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, str]] = {
    "tlm_break_resolved": {
        "subject": "[TLM RESOLVED] Break {break_id} — {instrument}",
        "body": (
            "Dear {recipient_name},\n\n"
            "The following TLM break has been resolved:\n\n"
            "  Break ID   : {break_id}\n"
            "  Type       : {break_type}\n"
            "  Instrument : {instrument}\n"
            "  Resolved At: {resolved_at}\n"
            "  Resolution : {resolution_summary}\n\n"
            "Financial impact cleared: USD {financial_impact}\n\n"
            "Please update PACT case {linked_pact_case} to CLOSED.\n\n"
            "Regards,\nGenAI Ops Copilot"
        ),
    },
    "pact_case_escalation": {
        "subject": "[PACT ESCALATION] Case {case_id} — SLA AT RISK",
        "body": (
            "Dear {recipient_name},\n\n"
            "PACT case {case_id} is approaching its SLA deadline and requires immediate attention.\n\n"
            "  Case Title : {case_title}\n"
            "  Priority   : {priority}\n"
            "  SLA Due    : {sla_due_at}\n"
            "  Status     : {status}\n"
            "  Next Action: {next_action}\n\n"
            "Please take action immediately to avoid SLA breach.\n\n"
            "Regards,\nGenAI Ops Copilot"
        ),
    },
    "ge_validation_failure": {
        "subject": "[DATA QUALITY ALERT] GE Suite '{suite_name}' failed — {failed_count} expectations",
        "body": (
            "Dear {recipient_name},\n\n"
            "Great Expectations checkpoint run '{checkpoint_name}' completed with failures.\n\n"
            "  Suite            : {suite_name}\n"
            "  Failed Expectations: {failed_count}\n"
            "  Critical Failures : {critical_count}\n"
            "  Run Time         : {run_time}\n\n"
            "Top failure:\n  {top_failure}\n\n"
            "Please investigate and resolve before downstream pipelines are impacted.\n\n"
            "Regards,\nGenAI Ops Copilot"
        ),
    },
    "root_cause_resolution": {
        "subject": "[RESOLUTION REPORT] {incident_title}",
        "body": (
            "Dear {recipient_name},\n\n"
            "A root cause analysis has been completed for the following incident.\n\n"
            "  Incident  : {incident_title}\n"
            "  Resolved At: {resolved_at}\n\n"
            "--- ROOT CAUSE ---\n{root_cause}\n\n"
            "--- IMPACT ---\n{impact}\n\n"
            "--- RECOMMENDED FIX ---\n{recommended_fix}\n\n"
            "--- ESTIMATED RECOVERY TIME ---\n{recovery_time}\n\n"
            "This notification was generated automatically by GenAI Ops Copilot.\n\n"
            "Regards,\nGenAI Ops Copilot"
        ),
    },
}


# ---------------------------------------------------------------------------
# Core dispatcher
# ---------------------------------------------------------------------------

def send_notification(
    template_name: str,
    recipient_email: str,
    recipient_name: str,
    **template_vars: str,
) -> dict[str, Any]:
    """
    Render a notification template and dispatch (mock) an email.

    Parameters
    ----------
    template_name   : key into _TEMPLATES
    recipient_email : destination address (validated format only)
    recipient_name  : display name in the email greeting
    **template_vars : variables injected into subject and body templates

    Returns
    -------
    A notification record dict that is appended to the in-memory log.

    Raises
    ------
    ValueError  : unknown template or invalid email format
    """
    if template_name not in _TEMPLATES:
        raise ValueError(
            f"NotificationServer: unknown template '{template_name}'. "
            f"Available: {list(_TEMPLATES.keys())}"
        )

    # Basic email format guard (not a full RFC-5322 check)
    if "@" not in recipient_email or "." not in recipient_email.split("@")[-1]:
        raise ValueError(
            f"NotificationServer: invalid recipient email '{recipient_email}'"
        )

    tmpl = _TEMPLATES[template_name]
    vars_with_recipient = {"recipient_name": recipient_name, **template_vars}

    try:
        subject = tmpl["subject"].format(**vars_with_recipient)
        body = tmpl["body"].format(**vars_with_recipient)
    except KeyError as exc:
        raise ValueError(
            f"NotificationServer: missing template variable {exc} "
            f"for template '{template_name}'"
        ) from exc

    record: dict[str, Any] = {
        "notification_id": f"NOTIF-{_utc_now().replace(':', '').replace('-', '')[:15]}-{len(_notification_log) + 1:04d}",
        "template": template_name,
        "recipient_email": recipient_email,
        "recipient_name": recipient_name,
        "subject": subject,
        "body": body,
        "sent_at": _utc_now(),
        "status": "SENT_MOCK",  # Replace with "SENT" after real SMTP integration
        "channel": "email",
    }

    _notification_log.append(record)
    logger.info(
        "NotificationServer: [MOCK] email dispatched to '%s' — subject: '%s'",
        recipient_email,
        subject,
    )
    return record


# ---------------------------------------------------------------------------
# MCP server entry point — returns current notification log and template list
# ---------------------------------------------------------------------------

def get_notification_data() -> dict[str, Any]:
    """
    Return the current notification log and available templates.
    Called by the MCPGateway during fetch_all().
    """
    return {
        "server": "notification_server",
        "available_templates": list(_TEMPLATES.keys()),
        "notification_log": list(_notification_log),
        "log_count": len(_notification_log),
        "summary": {
            "total_sent": len(_notification_log),
            "by_template": {
                tmpl: sum(1 for n in _notification_log if n["template"] == tmpl)
                for tmpl in _TEMPLATES
            },
        },
    }
