from __future__ import annotations

import json

from pydantic import ValidationError

from src.config import Settings, load_settings
from src.llm import LLMClient, LLMError, extract_json_object
from src.schemas import CriticFinding, CriticReport, ExtractionProposal, ModelRun


IMPORTANT_FIELDS = [
    "account_name",
    "opportunity_id",
    "sales_agent",
    "attendees",
    "products_discussed",
    "meeting_summary",
    "objections_or_risks",
    "buying_signals",
    "suggested_stage",
    "next_steps",
]


class EvidenceCriticAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.client = LLMClient(self.settings)

    def critique(self, note: str, proposal: ExtractionProposal) -> tuple[CriticReport, ModelRun]:
        prompt = self._build_prompt(note, proposal)
        try:
            response = self.client.complete(prompt, task="critique", preferred_provider="groq", json_mode=True)
            report = CriticReport.model_validate(extract_json_object(response.text))
            report.source = "llm"
            return report, ModelRun(
                task="critique",
                provider=response.provider,
                model=response.model,
                fallback_used=response.fallback_used,
            )
        except (LLMError, ValueError, ValidationError) as exc:
            report = deterministic_critique(note, proposal)
            return report, ModelRun(
                task="critique",
                provider="critic_fallback",
                model="rule_based",
                fallback_used=True,
                error=str(exc),
            )

    @staticmethod
    def _build_prompt(note: str, proposal: ExtractionProposal) -> str:
        return f"""
You are Agent #2, the RepLog AI evidence critic.

Check whether the extracted CRM proposal is grounded in the original meeting note.
Do not validate against CRM tables. Only judge support from the note itself.

Return only valid JSON with this exact shape:
{{
  "overall_confidence": 0.0,
  "findings": [
    {{
      "field": "string",
      "status": "supported, inferred, missing, or contradicted",
      "confidence": 0.0,
      "evidence": "short quote or null",
      "concern": "string or null"
    }}
  ],
  "warnings": ["string"],
  "needs_human_attention": ["field name"],
  "source": "llm"
}}

Use these rules:
- supported: explicit text in the note supports the field.
- inferred: plausible from the note, but not explicitly stated.
- missing: important field is blank or absent.
- contradicted: proposal conflicts with the note.
- Flag account_name, products_discussed, meeting_summary, suggested_stage, and next_steps if they are inferred, missing, or contradicted.

Original meeting note:
{note}

Extracted proposal JSON:
{proposal.model_dump_json()}
""".strip()


def deterministic_critique(note: str, proposal: ExtractionProposal) -> CriticReport:
    note_lower = note.lower()
    findings: list[CriticFinding] = []

    values = {
        "account_name": proposal.account_name,
        "opportunity_id": proposal.opportunity_id,
        "sales_agent": proposal.sales_agent,
        "attendees": proposal.attendees,
        "products_discussed": proposal.products_discussed,
        "meeting_summary": proposal.meeting_summary,
        "objections_or_risks": proposal.objections_or_risks,
        "buying_signals": proposal.buying_signals,
        "suggested_stage": proposal.suggested_stage,
        "next_steps": [task.description for task in proposal.next_steps],
    }

    for field in IMPORTANT_FIELDS:
        value = values[field]
        finding = _support_for_field(field, value, note, note_lower)
        findings.append(finding)

    warnings = [
        f"{finding.field} is {finding.status}: {finding.concern}"
        for finding in findings
        if finding.status in {"inferred", "missing", "contradicted"} and finding.concern
    ]
    needs_attention = [
        finding.field
        for finding in findings
        if finding.field in {"account_name", "products_discussed", "meeting_summary", "suggested_stage", "next_steps"}
        and finding.status in {"inferred", "missing", "contradicted"}
    ]
    overall = sum(finding.confidence for finding in findings) / max(len(findings), 1)
    return CriticReport(
        overall_confidence=round(overall, 2),
        findings=findings,
        warnings=warnings,
        needs_human_attention=needs_attention,
        source="deterministic_fallback",
    )


def _support_for_field(field: str, value: object, note: str, note_lower: str) -> CriticFinding:
    if value is None or value == "" or value == []:
        return CriticFinding(
            field=field,
            status="missing",
            confidence=0.0,
            concern="No value was extracted for this field.",
        )

    if isinstance(value, list):
        supported_items = [str(item) for item in value if str(item).lower() in note_lower]
        if supported_items and len(supported_items) == len(value):
            return CriticFinding(field=field, status="supported", confidence=0.88, evidence=supported_items[0])
        if supported_items:
            return CriticFinding(
                field=field,
                status="inferred",
                confidence=0.62,
                evidence=supported_items[0],
                concern="Some extracted values appear in the note, but not all were explicitly grounded.",
            )
        return CriticFinding(
            field=field,
            status="inferred",
            confidence=0.45,
            concern="The extracted list was not explicitly found in the note.",
        )

    text_value = str(value)
    if text_value.lower() in note_lower:
        return CriticFinding(field=field, status="supported", confidence=0.9, evidence=text_value)

    if field == "meeting_summary":
        overlap = _token_overlap(text_value, note)
        return CriticFinding(
            field=field,
            status="supported" if overlap >= 0.35 else "inferred",
            confidence=0.78 if overlap >= 0.35 else 0.55,
            concern=None if overlap >= 0.35 else "The summary is plausible but not directly quoted.",
        )

    if field == "suggested_stage" and _stage_is_supported(text_value, note_lower):
        return CriticFinding(field=field, status="supported", confidence=0.82, evidence=text_value)

    return CriticFinding(
        field=field,
        status="inferred",
        confidence=0.5,
        concern="The value was not explicitly found in the note.",
    )


def _token_overlap(value: str, note: str) -> float:
    value_tokens = {token.strip(".,:;!?").lower() for token in value.split() if len(token) > 3}
    note_tokens = {token.strip(".,:;!?").lower() for token in note.split() if len(token) > 3}
    if not value_tokens:
        return 0.0
    return len(value_tokens & note_tokens) / len(value_tokens)


def _stage_is_supported(stage: str, note_lower: str) -> bool:
    stage_terms = {
        "Prospecting": ["prospecting", "initial outreach"],
        "Engaging": ["engaging", "discovery", "pilot", "technical review"],
        "Proposal": ["proposal", "quote", "commercials"],
        "Won": ["won", "signed", "approved", "move forward"],
        "Lost": ["lost", "not moving forward", "competitor"],
    }
    return any(term in note_lower for term in stage_terms.get(stage, []))
