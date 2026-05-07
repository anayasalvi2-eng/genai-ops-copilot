"""
Pydantic schemas shared across the application.
"""

from pydantic import BaseModel, Field, EmailStr


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User query")


class AskResponse(BaseModel):
    response: str = Field(..., description="AI-generated root-cause analysis")
    latency_ms: float = Field(..., description="End-to-end latency in milliseconds")


class NotifyRequest(BaseModel):
    template: str = Field(
        ...,
        description=(
            "Notification template name. One of: tlm_break_resolved, "
            "pact_case_escalation, ge_validation_failure, root_cause_resolution"
        ),
    )
    recipient_email: EmailStr = Field(..., description="Destination email address")
    recipient_name: str = Field(..., min_length=1, max_length=100, description="Recipient display name")
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Template variables to inject into the email subject and body",
    )


class NotifyResponse(BaseModel):
    notification_id: str
    recipient_email: str
    subject: str
    status: str
    sent_at: str
