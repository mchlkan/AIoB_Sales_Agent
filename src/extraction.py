from __future__ import annotations

import re
from pathlib import Path

from pydantic import ValidationError

from src.config import PROMPTS_DIR, Settings, load_settings
from src.llm import LLMClient, LLMError, PROMPT_VERSIONS
from src.schemas import EvidenceItem, ExtractionProposal, FollowUpTask, ModelAttempt, ModelRun


class ExtractionAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.client = LLMClient(self.settings)

    def extract(self, note: str, crm_context: str) -> tuple[ExtractionProposal, ModelRun]:
        prompt = self._build_prompt(note, crm_context)
        try:
            proposal, response = self.client.complete_json_validated(
                prompt=prompt,
                task="extraction",
                preferred_provider="gemini",
                validator=ExtractionProposal.model_validate,
                prompt_version=PROMPT_VERSIONS["extraction"],
            )
            proposal.source = "llm"
            return proposal, ModelRun(
                task="extraction",
                provider=response.provider,
                model=response.model,
                fallback_used=response.fallback_used,
                repair_used=response.repair_used,
                prompt_version=response.prompt_version,
                latency_ms=response.latency_ms,
                attempts=response.attempts or [],
            )
        except (LLMError, ValueError, ValidationError) as exc:
            if not self.settings.demo_fallback_enabled:
                raise
            proposal = demo_fallback_extract(note)
            proposal.ambiguity_flags.append(f"Demo fallback used because LLM extraction failed: {exc}")
            return proposal, ModelRun(
                task="extraction",
                provider="demo_fallback",
                model="rule_based",
                fallback_used=True,
                prompt_version=PROMPT_VERSIONS["extraction"],
                error=str(exc),
                attempts=[
                    ModelAttempt(
                        task="extraction",
                        provider="demo_fallback",
                        model="rule_based",
                        attempt_type="demo_fallback",
                        success=True,
                        prompt_version=PROMPT_VERSIONS["extraction"],
                    )
                ],
            )

    @staticmethod
    def _build_prompt(note: str, crm_context: str) -> str:
        template_path = PROMPTS_DIR / "extractor.md"
        template = template_path.read_text(encoding="utf-8") if template_path.exists() else "{note}"
        return template.format(note=note, crm_context=crm_context)


def demo_fallback_extract(note: str) -> ExtractionProposal:
    lower = note.lower()
    account_patterns = [
        "Acme Corporation",
        "Bluth Company",
        "Bubba Gump",
        "Cheers",
        "Genco Pura Olive Oil Company",
        "Blackzim",
        "Cancity",
        "Codehow",
    ]
    product_patterns = ["GTX Plus Pro", "GTX Plus Basic", "GTX Pro", "GTXPro", "GTX Basic", "MG Advanced", "MG Special", "GTK 500"]
    agent_patterns = [
        "Zane Levy",
        "Darcel Schlecht",
        "Jonathan Berthelot",
        "Gladys Colclough",
        "Kami Bicknell",
        "Lajuana Vencill",
        "Moses Frase",
        "Boris Faz",
    ]
    account = next((name for name in account_patterns if name.lower() in lower), None)
    product_hits = [name for name in product_patterns if name.lower() in lower]
    sales_agent = next((name for name in agent_patterns if name.lower() in lower), None)
    attendees = _extract_attendees(note, account_patterns, product_patterns, agent_patterns)

    risks = []
    for keyword in ["delivery", "integration", "competitor", "budget", "security", "timeline"]:
        if keyword in lower:
            risks.append(keyword)

    buying_signals = []
    for phrase in ["approved", "move forward", "proposal", "quote", "pilot", "decision"]:
        if phrase in lower:
            buying_signals.append(phrase)

    suggested_stage = None
    if "proposal" in lower or "quote" in lower:
        suggested_stage = "Proposal"
    if "won" in lower or "signed" in lower:
        suggested_stage = "Won"
    if "lost" in lower:
        suggested_stage = "Lost"

    due_date = _extract_due_date(note)
    owner = _extract_owner(note)
    tasks = []
    if any(word in lower for word in ["follow up", "send", "schedule", "create a task", "timeline"]):
        tasks.append(
            FollowUpTask(
                description=_task_description(note),
                owner=owner,
                due_date=due_date,
                evidence=_sentence_with(note, ["send", "follow", "schedule", "timeline"]),
            )
        )

    evidence = []
    if account:
        evidence.append(EvidenceItem(field="account_name", quote=_sentence_with(note, [account]) or account))
    for product in product_hits[:2]:
        evidence.append(EvidenceItem(field="products_discussed", quote=_sentence_with(note, [product]) or product))
    if suggested_stage:
        evidence.append(EvidenceItem(field="suggested_stage", quote=_sentence_with(note, [suggested_stage, "proposal", "quote", "won", "lost"]) or suggested_stage))

    return ExtractionProposal(
        account_name=account,
        sales_agent=sales_agent,
        attendees=attendees,
        products_discussed=product_hits,
        meeting_summary=_first_sentence(note),
        customer_needs=[_sentence_with(note, ["need", "wants", "looking for", "asked"]) or "Customer needs extracted from meeting note."],
        objections_or_risks=risks,
        buying_signals=buying_signals,
        suggested_stage=suggested_stage,
        next_steps=tasks,
        confidence=0.78 if account and product_hits and sales_agent else 0.72 if account and product_hits else 0.48,
        evidence=evidence,
        ambiguity_flags=[] if account and product_hits else ["Fallback extraction could not confidently identify all CRM entities."],
        source="demo_fallback",
    )


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0][:500] if parts and parts[0] else text.strip()[:500]


def _sentence_with(text: str, needles: list[str]) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        sentence_lower = sentence.lower()
        if any(needle.lower() in sentence_lower for needle in needles):
            return sentence.strip()
    return None


def _extract_due_date(text: str) -> str | None:
    match = re.search(r"\b(by|before|on)\s+([A-Z][a-z]+day|\d{4}-\d{2}-\d{2})\b", text)
    return match.group(2) if match else None


def _extract_owner(text: str) -> str | None:
    match = re.search(r"\b(?:for|owner:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    return match.group(1) if match else None


def _task_description(text: str) -> str:
    sentence = _sentence_with(text, ["send", "follow", "schedule", "timeline"])
    return sentence or "Follow up with customer on next step from meeting."


def _extract_attendees(
    text: str, account_patterns: list[str], product_patterns: list[str], agent_patterns: list[str]
) -> list[str]:
    names = set(agent for agent in agent_patterns if agent.lower() in text.lower())
    for match in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text):
        if match in account_patterns or match in product_patterns:
            continue
        if any(word in match for word in ["GTX", "MG", "GTK", "Corporation", "Company"]):
            continue
        if match in {"Just", "Call", "Meeting", "Friday", "Monday", "Wednesday", "Proposal"}:
            continue
        names.add(match)
    return sorted(names)
