from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DealStage = Literal["Prospecting", "Engaging", "Proposal", "Won", "Lost"]
Decision = Literal["approved", "rejected"]
FieldSupportStatus = Literal["supported", "inferred", "missing", "contradicted"]
ModelTask = Literal["extraction", "critique", "crm_chat"]


class EvidenceItem(BaseModel):
    field: str
    quote: str


class FollowUpTask(BaseModel):
    description: str
    owner: str | None = None
    due_date: str | None = None
    evidence: str | None = None


class ModelRun(BaseModel):
    task: ModelTask
    provider: str
    model: str
    fallback_used: bool = False
    error: str | None = None


class ExtractionProposal(BaseModel):
    account_name: str | None = None
    opportunity_id: str | None = None
    sales_agent: str | None = None
    attendees: list[str] = Field(default_factory=list)
    products_discussed: list[str] = Field(default_factory=list)
    meeting_summary: str
    customer_needs: list[str] = Field(default_factory=list)
    objections_or_risks: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    suggested_stage: DealStage | None = None
    next_steps: list[FollowUpTask] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    source: Literal["llm", "demo_fallback"] = "llm"


class CriticFinding(BaseModel):
    field: str
    status: FieldSupportStatus
    confidence: float = Field(ge=0, le=1)
    evidence: str | None = None
    concern: str | None = None


class CriticReport(BaseModel):
    overall_confidence: float = Field(ge=0, le=1)
    findings: list[CriticFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    needs_human_attention: list[str] = Field(default_factory=list)
    source: Literal["llm", "deterministic_fallback"] = "llm"


class MatchResult(BaseModel):
    account_name: str | None = None
    account_confidence: float = 0
    product_names: list[str] = Field(default_factory=list)
    product_warnings: list[str] = Field(default_factory=list)
    opportunity_id: str | None = None
    opportunity_stage: str | None = None
    opportunity_warning: str | None = None
    sales_agent: str | None = None


class ValidationResult(BaseModel):
    is_approvable: bool
    warnings: list[str] = Field(default_factory=list)
    matched: MatchResult


class ReviewPackage(BaseModel):
    proposal: ExtractionProposal
    validation: ValidationResult
    source_note: str
    model_provider: str
    model_name: str
    critic: CriticReport | None = None
    model_runs: list[ModelRun] = Field(default_factory=list)


class WritebackOperation(BaseModel):
    operation: Literal["insert_meeting_log", "insert_task", "update_opportunity_stage", "insert_audit_log"]
    target: str
    summary: str


class WritebackPlan(BaseModel):
    decision: Decision
    operations: list[WritebackOperation] = Field(default_factory=list)
    requires_approval: bool = True


class CRMChatContext(BaseModel):
    source: str
    rows: list[dict[str, str | int | float | None]] = Field(default_factory=list)
