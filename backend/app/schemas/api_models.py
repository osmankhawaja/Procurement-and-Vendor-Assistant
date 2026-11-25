"""Request and response models for the FastAPI endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.po import PurchaseOrder


class ChatRequest(BaseModel):
    """A user message and optional conversation thread identifier."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=10_000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized

    @field_validator("thread_id")
    @classmethod
    def normalize_thread_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("thread_id must not be blank")
        return normalized


class ChatResponse(BaseModel):
    """Procurement agent response and workflow status."""

    thread_id: str
    response: str | None
    status: Literal["completed", "waiting_for_approval"]
    citations: list[dict[str, Any]] = Field(default_factory=list)
    purchase_order: PurchaseOrder | None = None


class ApprovalItem(BaseModel):
    """Approval currently paused in the procurement workflow."""

    thread_id: str
    status: str = "pending"
    next: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    """A manager decision submitted for a pending purchase order."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=2000)
    approver_id: str | None = Field(default=None, max_length=128)
    approver_name: str | None = Field(default=None, max_length=200)

    @field_validator("decision", mode="before")
    @classmethod
    def normalize_decision(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("comment", "approver_id", "approver_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ApprovalDecisionResult(BaseModel):
    """Result after resuming the interrupted workflow."""

    thread_id: str
    decision: Literal["approve", "reject"]
    state: dict[str, Any]


class GraphStateResponse(BaseModel):
    """Current state snapshot for a conversation thread."""

    thread_id: str
    values: dict[str, Any]
    next: list[str] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class GraphDefinitionResponse(BaseModel):
    """Mermaid definition of the compiled procurement workflow."""

    mermaid: str