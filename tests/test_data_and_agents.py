from __future__ import annotations

from src.actions import WritebackAgent
from src.config import Settings
from src.critic import deterministic_critique
from src.crm_chat import answer_question_with_metadata
from src.database import connect, ensure_database, run_eda, setup_database
from src.extraction import demo_fallback_extract
from src.llm import LLMClient, LLMError, LLMResponse
from src.schemas import CriticFinding, CriticReport, ExtractionProposal, ModelRun, ReviewPackage
from src.validation import ValidationAgent


def empty_settings() -> Settings:
    return Settings(
        model_provider="gemini",
        demo_fallback_enabled=True,
        gemini_api_key="",
        gemini_model="gemini-2.5-flash-lite",
        groq_api_key="",
        groq_model="qwen/qwen3-32b",
        openrouter_api_key="",
        openrouter_model="",
        ollama_base_url="",
        ollama_model="",
    )


def test_eda_detects_expected_data_shape_and_product_mismatch():
    eda = run_eda()
    assert eda["tables"]["sales_pipeline"]["rows"] == 8800
    assert eda["deal_stage_distribution"]["Won"] == 4238
    assert "GTXPro" in eda["integrity"]["pipeline_products_not_in_products"]
    assert eda["integrity"]["open_opportunities"] > 0


def test_database_setup_preserves_source_counts(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    with connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 85
        assert conn.execute("SELECT COUNT(*) FROM sales_pipeline").fetchone()[0] == 8800
        assert conn.execute("SELECT COUNT(*) FROM meeting_logs").fetchone()[0] == 0


def test_validation_handles_gtx_product_alias(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    note = (
        "Call with Acme Corporation about GTX Pro. Zane Levy should send a revised quote. "
        "Move this to Proposal because procurement asked for the quote."
    )
    proposal = demo_fallback_extract(note)
    with connect(db_path) as conn:
        validation = ValidationAgent().validate(conn, proposal)
    assert validation.matched.account_name == "Acme Corporation"
    assert "GTX Pro" in validation.matched.product_names
    assert validation.matched.opportunity_id


def test_rejection_writes_audit_only(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    proposal = demo_fallback_extract("Call with Acme Corporation about GTX Pro. Send a quote.")
    with connect(db_path) as conn:
        validation = ValidationAgent().validate(conn, proposal)
        review = ReviewPackage(
            proposal=proposal,
            validation=validation,
            source_note="Call with Acme Corporation about GTX Pro. Send a quote.",
            model_provider="demo_fallback",
            model_name="rule_based",
        )
        result = WritebackAgent().apply_decision(conn, review, "rejected")
        assert result["status"] == "rejected"
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM meeting_logs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_approval_writes_meeting_task_audit_and_stage_update(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    note = (
        "Just finished a call with Acme Corporation about the GTX Pro refresh. "
        "Zane Levy should send a revised quote by Friday. Move this to Proposal."
    )
    proposal = demo_fallback_extract(note)
    with connect(db_path) as conn:
        validation = ValidationAgent().validate(conn, proposal)
        review = ReviewPackage(
            proposal=proposal,
            validation=validation,
            source_note=note,
            model_provider="demo_fallback",
            model_name="rule_based",
        )
        result = WritebackAgent().apply_decision(conn, review, "approved")
        assert result["status"] == "approved"
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM meeting_logs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
        updated = conn.execute(
            "SELECT deal_stage FROM sales_pipeline WHERE opportunity_id = ?",
            (validation.matched.opportunity_id,),
        ).fetchone()
        assert updated["deal_stage"] == "Proposal"


def test_ensure_database_does_not_overwrite_runtime_pipeline_updates(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE sales_pipeline SET deal_stage = 'Proposal' WHERE opportunity_id = '7TI1WTV9'"
        )
        conn.commit()

    ensure_database(db_path)

    with connect(db_path) as conn:
        updated = conn.execute(
            "SELECT deal_stage FROM sales_pipeline WHERE opportunity_id = '7TI1WTV9'"
        ).fetchone()
        assert updated["deal_stage"] == "Proposal"


def test_ask_crm_answers_attendee_questions(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    note = (
        "Just finished a call with Acme Corporation about the GTX Pro refresh. "
        "Zane Levy, Sarah from procurement, and James from infrastructure joined. "
        "Send a revised quote by Friday and move this to Proposal."
    )
    proposal = demo_fallback_extract(note)
    with connect(db_path) as conn:
        validation = ValidationAgent().validate(conn, proposal)
        review = ReviewPackage(
            proposal=proposal,
            validation=validation,
            source_note=note,
            model_provider="demo_fallback",
            model_name="rule_based",
        )
        WritebackAgent().apply_decision(conn, review, "approved")
        answer, run = answer_question_with_metadata(
            conn, "Who attended the latest meeting?", settings=empty_settings()
        )
    assert "Zane Levy" in answer
    assert "Sarah" in answer
    assert run.provider == "chat_fallback"


def test_llm_router_falls_back_between_gemini_and_groq():
    class StubLLMClient(LLMClient):
        def _complete_with_provider(self, prompt, provider, task, json_mode):
            if provider == "gemini":
                raise LLMError("gemini unavailable")
            return LLMResponse(text='{"ok": true}', provider=provider, model="qwen-test", task=task)

    response = StubLLMClient(empty_settings()).complete(
        "Return JSON.", task="critique", preferred_provider="gemini"
    )
    assert response.provider == "groq"
    assert response.fallback_used is True


def test_deterministic_critic_flags_ungrounded_fields():
    note = "Call with Acme Corporation about GTX Pro. Procurement asked for a quote."
    proposal = ExtractionProposal(
        account_name="Acme Corporation",
        products_discussed=["Imaginary Product"],
        meeting_summary="Acme discussed a quote.",
        suggested_stage="Proposal",
        next_steps=[],
        confidence=0.9,
    )
    report = deterministic_critique(note, proposal)
    product_finding = next(finding for finding in report.findings if finding.field == "products_discussed")
    assert product_finding.status == "inferred"
    assert "products_discussed" in report.needs_human_attention


def test_writeback_audit_stores_critic_runs_and_plan(tmp_path):
    db_path = tmp_path / "crm.db"
    setup_database(db_path)
    note = (
        "Just finished a call with Acme Corporation about the GTX Pro refresh. "
        "Zane Levy should send a revised quote by Friday. Move this to Proposal."
    )
    proposal = demo_fallback_extract(note)
    critic = CriticReport(
        overall_confidence=0.82,
        findings=[
            CriticFinding(
                field="account_name",
                status="supported",
                confidence=0.9,
                evidence="Acme Corporation",
            )
        ],
    )
    runs = [
        ModelRun(task="extraction", provider="gemini", model="gemini-2.5-flash-lite"),
        ModelRun(task="critique", provider="groq", model="qwen/qwen3-32b"),
    ]
    with connect(db_path) as conn:
        validation = ValidationAgent().validate(conn, proposal, critic)
        review = ReviewPackage(
            proposal=proposal,
            validation=validation,
            source_note=note,
            model_provider="gemini",
            model_name="gemini-2.5-flash-lite",
            critic=critic,
            model_runs=runs,
        )
        WritebackAgent().apply_decision(conn, review, "approved")
        audit = conn.execute(
            """
            SELECT critic_json, model_runs_json, writeback_plan_json, approved_proposal_json
            FROM audit_log
            """
        ).fetchone()
    assert "account_name" in audit["critic_json"]
    assert "critique" in audit["model_runs_json"]
    assert "insert_meeting_log" in audit["writeback_plan_json"]
    assert "meeting_summary" in audit["approved_proposal_json"]
