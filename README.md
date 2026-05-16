# Close Loop

**Close Loop** is a Streamlit MVP for an AI-assisted CRM admin workflow. It turns messy sales meeting notes into structured CRM update proposals, validates them against a local SQLite CRM, asks for human approval, and only then writes approved changes to the database.

The core product idea is simple: the AI helps sales teams avoid manual CRM admin, but it never silently mutates CRM records.

> The AI drafts. The human commits.

---

## Table of Contents

1. [Reproduce the Demo](#1-reproduce-the-demo)
2. [Problem and Solution](#2-problem-and-solution)
3. [Agentic Workflow](#3-agentic-workflow)
4. [Models and Providers](#4-models-and-providers)
5. [Dataset Overview](#5-dataset-overview)
6. [Reliability and Risk Mitigation](#6-reliability-and-risk-mitigation)
7. [Project Structure](#7-project-structure)
8. [Tests](#8-tests)
9. [Limitations and Next Steps](#9-limitations-and-next-steps)
10. [Design Principle](#10-design-principle)

---

## 1. Reproduce the Demo

This is the fastest path from a fresh clone to a working demo in the browser.

### 1.1 Prerequisites

- Python 3.10+
- A terminal
- Optional: a Gemini API key and a Groq API key (both have free tiers). The app also runs without keys in deterministic demo-fallback mode.

### 1.2 Clone and install

```bash
git clone https://github.com/mchlkan/AIoB_Sales_Agent.git
cd AIoB_Sales_Agent

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 1.3 Configure environment

```bash
cp .env.example .env
```

Open `.env` and add your keys (optional). The default configuration uses Gemini for extraction/chat and Groq for critique:

```bash
MODEL_PROVIDER=gemini
DEMO_FALLBACK_ENABLED=true

GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite

GROQ_API_KEY=your_key_here
GROQ_MODEL=qwen/qwen3-32b
```

If you skip the keys, set `DEMO_FALLBACK_ENABLED=true` and the app will use deterministic rule-based fallbacks for all LLM calls. The workflow stays end-to-end functional.

### 1.4 Build the local CRM database

```bash
python db/setup_db.py
```

This loads the five source CSV files in `data/` into a local SQLite database at `db/crm.db` and creates the runtime tables (`meeting_logs`, `tasks`, `audit_log`). The CSVs are treated as immutable source data; the database is reproducible at any time and is gitignored.

### 1.5 Run the app

```bash
streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

### 1.6 Demo walkthrough

1. Go to the **Workspace** tab.
2. Pick one of the nine synthetic notes in the sidebar dropdown (or paste your own) — e.g. `note_01_delivery_risk.txt`.
3. Click **Analyze meeting**. The Extraction Agent, Evidence Critic, and CRM Validation Agent run in sequence.
4. Review the structured proposal: account match, opportunity, products, summary, suggested stage, follow-up tasks, evidence quotes, and validation warnings.
5. Optionally correct any fields the critic flagged.
6. Click **Approve** to write the meeting log, tasks, and (if allowed) the stage update. Click **Reject** to only record the decision in the audit log.
7. Switch to **Ask CRM** and try questions like _"Which open opportunities mentioned delivery risk?"_ or _"What follow-up tasks did I just approve?"_
8. Switch to **Activity** to see the full audit trail.

---

## 2. Problem and Solution

### Problem

Sales reps spend significant time after meetings updating CRM records — writing summaries, updating opportunity stages, logging objections, creating follow-up tasks. The result:

- CRM updates are delayed or skipped
- Notes are inconsistent across reps
- Objections, buying signals, and next steps get lost
- Follow-ups are forgotten
- Managers lack pipeline visibility
- CRM data quality decays

### Solution

Close Loop converts unstructured meeting notes into structured, validated CRM update proposals, with confidence and evidence shown to the rep, and writes nothing until the rep approves.

### Target users

- B2B sales representatives
- Account executives
- Relationship managers
- Sales managers who need better pipeline visibility

---

## 3. Agentic Workflow

Close Loop is built around a five-agent backend pipeline with a mandatory human review gate.

```text
CRM Data + Meeting Note
  -> [Agent 1] Extraction Agent
  -> [Agent 2] Evidence Critic
  -> [Agent 3] CRM Validation Agent
  -> Human Review (approve / reject)
  -> [Agent 4] Writeback Agent  (only on approve)
  -> Updated CRM
  -> [Agent 5] Ask-CRM Agent
```

### Agent 1: Extraction Agent

- **Input:** raw meeting note + compact CRM context (known accounts, products, agents).
- **Model:** Gemini 2.5 Flash Lite.
- **Output:** strict structured JSON validated with Pydantic — account, opportunity hint, sales agent, attendees, products, summary, customer needs, objections/risks, buying signals, suggested stage, follow-up tasks with due dates, confidence score, evidence quotes, ambiguity flags.
- **Prompt** (from `prompts/extractor.md`):

```text
You are Agent #1, the Close Loop extraction agent.

Extract CRM-relevant facts from the meeting note. Use the CRM context only
to improve entity names; do not invent facts.

Return only valid JSON with this exact shape:

{
  "account_name": "string or null",
  "opportunity_id": "string or null",
  "sales_agent": "string or null",
  "attendees": ["person name"],
  "products_discussed": ["string"],
  "meeting_summary": "string",
  "customer_needs": ["string"],
  "objections_or_risks": ["string"],
  "buying_signals": ["string"],
  "suggested_stage": "Prospecting, Engaging, Proposal, Won, Lost, or null",
  "next_steps": [
    {"description": "string", "owner": "string or null",
     "due_date": "string or null", "evidence": "string or null"}
  ],
  "confidence": 0.0,
  "evidence": [
    {"field": "string", "quote": "short exact quote from the note"}
  ],
  "ambiguity_flags": ["string"],
  "source": "llm"
}

CRM context:
{crm_context}

Meeting note:
{note}
```

### Agent 2: Evidence Critic

- **Input:** original note + Agent 1's extracted proposal.
- **Model:** Groq Qwen3-32B.
- **Output:** per-field grounding verdict — `supported` / `inferred` / `missing` / `contradicted` — with evidence quotes, an overall confidence score, warnings, and a list of fields needing human attention.
- **Purpose:** does NOT validate against CRM tables. Only checks whether claims are grounded in the source note.
- **Prompt** (from `src/critic.py`):

```text
You are Agent #2, the Close Loop evidence critic.

Check whether the extracted CRM proposal is grounded in the original meeting note.
Do not validate against CRM tables. Only judge support from the note itself.

Return only valid JSON with this exact shape:
{
  "overall_confidence": 0.0,
  "findings": [
    {
      "field": "string",
      "status": "supported, inferred, missing, or contradicted",
      "confidence": 0.0,
      "evidence": "short quote or null",
      "concern": "string or null"
    }
  ],
  "warnings": ["string"],
  "needs_human_attention": ["field name"],
  "source": "llm"
}

Use these rules:
- supported: explicit text in the note supports the field.
- inferred: plausible from the note, but not explicitly stated.
- missing: important field is blank or absent.
- contradicted: proposal conflicts with the note.
- Flag account_name, products_discussed, meeting_summary, suggested_stage,
  and next_steps if they are inferred, missing, or contradicted.

Original meeting note:
{note}

Extracted proposal JSON:
{proposal_json}
```

### Agent 3: CRM Validation Agent

- **Input:** extraction proposal + critic report + live SQLite CRM tables.
- **Model:** none — fully deterministic Python.
- **Output:** `is_approvable` flag, warnings, blocking reasons, fields needing correction, risk level (low / medium / high), best-match account / product / opportunity / sales agent.
- **Checks:** fuzzy account and product matches, product aliases (e.g. `GTXPro` vs `GTX Pro`), open opportunity lookup, sales-agent match, duplicate/ambiguous opportunities, valid stage progression, missing mandatory fields, propagated critic warnings.

### Human Review Layer

The approval gate. The user can:

- accept the proposal
- reject it
- manually correct any field before approval

Nothing is written to runtime CRM tables until the user explicitly approves.

### Agent 4: Writeback Agent

- **Input:** the approved review package and the human decision.
- **Model:** none — deterministic Python with parameterized SQL.
- **Output on approve:** new rows in `meeting_logs`, `tasks`, an optional stage update in `sales_pipeline`, and a full `audit_log` entry.
- **Output on reject:** an `audit_log` entry only, with no other mutations.
- **Safety:** if validation does not allow a stage update, the meeting log and tasks are still written, but the pipeline stage update is skipped and the skip reason is recorded.

### Agent 5: Ask-CRM Agent

- **Input:** the user's natural language question + rows retrieved from SQLite via intent routing (attendees, tasks, risks, pipeline, audit, recent meetings).
- **Model:** Gemini 2.5 Flash Lite.
- **Output:** one concise grounded paragraph (or bullets when listing items), based strictly on retrieved CRM context. Cannot mutate data.
- **Prompt** (from `src/crm_chat.py`):

```text
You are Agent #5, the Close Loop Ask-CRM agent.

Answer the user's CRM question in a natural, conversational style.
Use only the retrieved CRM context below. Do not invent people, accounts,
tasks, opportunities, or dates. If the context is insufficient, say what
is missing and suggest the closest CRM question you can answer from the
available records.

Prefer one concise paragraph. Use bullets only when the user asks for a
list or when there are many concrete items.

Question:
{question}

Retrieved CRM context:
{context_json}
```

---

## 4. Models and Providers

| Agent | Provider | Model | Fallback |
|---|---|---|---|
| 1. Extraction | Gemini | `gemini-2.5-flash-lite` | Rule-based Python |
| 2. Evidence Critic | Groq | `qwen/qwen3-32b` | Deterministic Python |
| 3. CRM Validation | — | Deterministic Python | n/a |
| 4. Writeback | — | Deterministic Python + parameterized SQL | n/a |
| 5. Ask-CRM | Gemini | `gemini-2.5-flash-lite` | Rule-based keyword responses |

### Why these providers

- Both Gemini and Groq offer free-tier access — no cost for the prototype.
- Gemini for extraction and chat: strong structured JSON output, good entity recognition.
- Groq for critique: very fast inference, well-suited for grounding/reasoning checks.

### LLM client wrapper

`src/llm.py` is a small provider wrapper that handles:

- provider selection from `.env`
- JSON-mode prompting
- one JSON repair pass on parse failures
- provider fallback between Gemini and Groq
- emergency deterministic fallback if all LLM paths fail and `DEMO_FALLBACK_ENABLED=true`
- prompt versioning and per-attempt telemetry recorded in the audit log

### Configuration

All settings live in `.env`. The `.env` file is local-only and is gitignored.

```bash
MODEL_PROVIDER=gemini            # default provider for extraction and chat
DEMO_FALLBACK_ENABLED=true       # turn deterministic fallback on/off

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-lite

GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3-32b
```

---

## 5. Dataset Overview

### Source CRM data

The provided CSV files in `data/` are treated as immutable source data.

| File | Rows | Description |
|---|---|---|
| `accounts.csv` | 85 | Company/account reference data |
| `products.csv` | 7 | Product catalog |
| `sales_pipeline.csv` | 8,800 | Opportunity pipeline and deal stages — the main CRM table |
| `sales_teams.csv` | 35 | Sales agents, managers, and regions |
| `data_dictionary.csv` | 21 | Field descriptions for the source data |

### Deal stages

The pipeline uses four source stages:

- `Won`
- `Lost`
- `Engaging`
- `Prospecting`

Open opportunities are `Engaging` and `Prospecting`. The Extraction Agent can additionally suggest a `Proposal` stage transition based on the meeting note.

### Known data quirks

- The pipeline uses the product code `GTXPro`, while the catalog uses `GTX Pro`. The Validation Agent normalizes this alias automatically.
- Some open opportunities in the pipeline have a missing account name. These are useful as validation examples (the app surfaces a warning) but are not used for the happy-path demo.
- The source data has no meeting notes, no objections, no buying signals, and no follow-up task history — exactly the gap Close Loop fills.

### Runtime tables

The local SQLite database adds three runtime tables that store approved app state:

- `meeting_logs` — approved meeting summaries and extracted context
- `tasks` — approved follow-up tasks
- `audit_log` — every approve/reject decision with the full original proposal, validation result, critic result, writeback plan, applied changes, and model run metadata

The local `db/crm.db` file is gitignored. It is regenerated from the CSVs on demand.

### Synthetic data: meeting notes

Because the source data has no unstructured meeting notes, the repo includes nine synthetic notes in `sample_notes/`:

- `note_01_delivery_risk.txt`
- `note_02_budget_approved.txt`
- `note_03_competitor_objection.txt`
- `note_04_pilot_next_step.txt`
- `note_05_multi_stakeholder_security.txt`
- `note_06_price_pushback.txt`
- `note_07_missing_product_ambiguity.txt`
- `note_08_close_won_signal.txt`
- `note_09_unknown_account_warning.txt`

Each note is tied to a real account, real product, and real open opportunity from the CRM data. They simulate realistic sales-rep inputs covering delivery risk, competitor objections, budget approvals, buying signals, stakeholder attendance, follow-up tasks, and ambiguity / missing information.

A small labeled reliability fixture lives in `evals/meeting_notes/reliability_cases.json` for regression testing.

### Exploratory data analysis

The full EDA is in:

- `notebooks/close_loop_data_eda.ipynb` — executed notebook
- `docs/DATA_EDA.md` — written summary

The EDA covers table sizes, columns, missing values, unique counts, deal-stage distribution, open opportunities, referential integrity, product naming quirks, and the rationale for synthetic meeting notes.

---

## 6. Reliability and Risk Mitigation

### Core risk: hallucination

The AI could confidently extract the wrong account, the wrong deal stage, or invent a commitment that was never made. Close Loop mitigates this with **mandatory human-in-the-loop** approval: no CRM field is written until the rep reviews a confidence-scored summary and clicks approve.

The mitigation is layered:

- **Evidence Critic** labels every field as `supported` / `inferred` / `missing` / `contradicted` before the rep sees it.
- **CRM Validation** blocks approval entirely if account, product, opportunity, or summary cannot be matched in the live CRM.
- **Deterministic stage rules** block invalid stage transitions (you cannot jump from `Prospecting` to `Won`).
- **Full audit trail** records every approve and reject with the model metadata attached.

### Other risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM API outage or rate limit | Every LLM agent has a deterministic Python fallback that activates automatically. The app remains fully usable offline if `DEMO_FALLBACK_ENABLED=true`. |
| Multiple open opportunities match a single account | The Validation Agent surfaces a warning (`"N open opportunities match; using most recent as default"`) so the rep can correct it before approval. |
| Fuzzy matching picks the wrong account | All match results are surfaced with the rep's original phrase vs the matched name, so wrong matches are visible at review time. |
| Wrong stage advancement | Deterministic stage-flow rules in `src/matching.py`. Invalid transitions are skipped and the skip reason is recorded in the audit log. |
| Data quality drift | Source CSVs are immutable. The runtime database is reproducible. The audit log captures the full proposal, validation, and critic state of every decision. |

### Blockers vs warnings

Approval is **hard-blocked** when:

- account is missing
- product is missing
- open opportunity is missing
- meeting summary is missing
- the evidence critic marks account, product, or summary as `missing` or `contradicted`

Low model confidence does NOT auto-block the review. Instead, it raises the review risk level (low / medium / high) and keeps the rep in control.

### Audit trail content

Each audit log row stores:

- original model proposal
- final human-approved proposal (or null if rejected)
- validation result
- critic result
- writeback plan
- applied changes
- per-agent model run metadata (provider, model, latency, prompt version, attempts, fallback usage)

---

## 7. Project Structure

```text
AIoB_Sales_Agent/
  app.py                              Streamlit application
  README.md                           This file
  requirements.txt                    Python dependencies
  .env.example                        Environment template
  pyproject.toml                      Project metadata

  src/
    config.py                         Environment and path configuration
    database.py                       SQLite setup, source loading, EDA helpers
    llm.py                            Gemini / Groq provider wrapper
    extraction.py                     Agent 1: Extraction Agent
    critic.py                         Agent 2: Evidence Critic
    validation.py                     Agent 3: CRM Validation Agent
    actions.py                        Agent 4: Writeback Agent
    crm_chat.py                       Agent 5: Ask-CRM Agent
    schemas.py                        Pydantic schemas
    matching.py                       CRM matching and stage helpers

  db/
    setup_db.py                       Database creation script

  data/
    accounts.csv                      Source CRM data (immutable)
    products.csv
    sales_pipeline.csv
    sales_teams.csv
    data_dictionary.csv

  sample_notes/                       Nine synthetic demo meeting notes
  prompts/                            LLM prompt templates
  notebooks/                          Executed EDA notebook
  docs/                               EDA summary docs
  evals/                              Labeled reliability fixtures
  tests/                              Data and agent tests
```

---

## 8. Tests

Run the test suite:

```bash
pytest -q
```

The tests cover:

- CSV loading into SQLite
- source row-count preservation
- product alias handling (`GTXPro` vs `GTX Pro`)
- validation behavior and blocking reasons
- human-corrected field writeback
- approval and rejection writeback paths
- audit logging
- critic fallback behavior
- Ask-CRM fallback behavior
- unsupported CRM question handling
- JSON repair metadata
- no writeback before approval (safety invariant)

---

## 9. Limitations and Next Steps

### Current limitations

Close Loop is an MVP. It does **not** include:

- Salesforce, HubSpot, or Dynamics integration
- WhatsApp or voice ingestion (text only for now)
- production authentication
- multi-user permissions
- hosted database
- background jobs or queues
- long-term vector / semantic memory
- production monitoring or observability

The current goal is a reliable, end-to-end local demo of the agentic CRM workflow.

### Recommended next improvements

1. Polish the Streamlit frontend so the workflow feels like a CRM assistant, not a developer demo.
2. Expand the labeled evaluation set in `evals/` and score live model outputs against it on every prompt or model change.
3. Add semantic retrieval over approved meeting logs and tasks for the Ask-CRM agent.
4. Add prompt-versioned eval reports for Gemini and Groq model changes.
5. Add production-grade observability if the app moves beyond a local MVP.
6. Add a real audio-to-text ingestion path (WhatsApp / Teams voice memo).

---

## 10. Design Principle

> Close Loop is not an autonomous CRM mutation bot. It is an AI-assisted CRM admin system with evidence, validation, human approval, and auditability built into the workflow.

The AI proposes. The human approves. Every decision is logged.

*AI disclosure: Claude Code (Opus 4.7) was used as a coding assistant for the repository setup, the agentic workflow implementation, and the test suite. All conceptual work, problem definition, agentic design, and feature scoping, was done by the team.* 
