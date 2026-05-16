# Close Loop

Close Loop is a Streamlit MVP for an AI-assisted CRM admin workflow. It turns messy sales meeting notes or transcripts into structured CRM update proposals, validates them against a local SQLite CRM, asks for human approval, and only then writes approved changes to the database.

The core product idea is simple: the AI helps sales teams avoid manual CRM admin, but it does not silently mutate CRM records.

## What The App Does

Close Loop supports one clean demo flow:

```text
Paste meeting note
-> Extraction Agent creates a structured CRM proposal
-> Evidence Critic checks whether the proposal is grounded in the note
-> CRM Validation Agent checks the proposal against local CRM data
-> Human reviews, edits, approves, or rejects
-> Writeback Agent updates SQLite only after approval
-> Ask-CRM Agent answers questions over approved CRM memory
```

The user experience stays simple: paste a note, review the proposed update, approve or reject, then ask the CRM follow-up questions conversationally.

## Key Features

- Meeting-note to CRM proposal extraction
- Evidence and confidence review
- Deterministic CRM validation against local account, product, pipeline, and sales-team data
- Human-in-the-loop approval before any writeback
- Safe SQLite updates through parameterized operations
- Audit log for every approval and rejection
- Follow-up task creation from approved notes
- Optional pipeline stage updates when validation allows them
- Conversational Ask-CRM over pipeline, meetings, tasks, risks, and audit history
- Reproducible SQLite database built from immutable CSV files
- Synthetic demo notes limited to realistic meeting-note examples

## Agentic Workflow

Close Loop uses a five-agent backend workflow.

### Agent 1: Extraction Agent

The Extraction Agent receives the raw meeting note plus compact CRM context. It uses Gemini by default and returns strict structured JSON validated with Pydantic.

It extracts:

- account
- opportunity hints
- sales agent
- attendees
- products discussed
- meeting summary
- customer needs
- objections or risks
- buying signals
- suggested stage
- follow-up tasks
- confidence
- evidence snippets
- ambiguity flags

### Agent 2: Evidence Critic Agent

The Evidence Critic Agent checks whether the extracted proposal is actually supported by the original note. It uses Groq by default.

For each important field, it marks the field as:

- supported
- inferred
- missing
- contradicted

The critic does not validate against CRM tables. Its job is grounding: did the note really say this?

### Agent 3: CRM Validation Agent

The CRM Validation Agent is deterministic Python. It checks the extracted proposal against the SQLite CRM.

It validates:

- account match
- product match
- product aliases such as `GTXPro` and `GTX Pro`
- open opportunity match
- sales-agent match
- duplicate or ambiguous opportunities
- allowed stage movement
- missing mandatory fields
- confidence and critic warnings

This agent does not mutate the database.

### Human Review Layer

The human review layer is the approval gate. The user can accept, reject, or manually correct proposed fields before approval.

Nothing is written to CRM runtime tables until the user explicitly approves.

### Agent 4: Writeback Planner / Executor

The Writeback Agent converts the approved review package into a constrained writeback plan.

It can write:

- approved meeting logs
- follow-up tasks
- optional opportunity stage updates
- audit records

It uses parameterized SQLite operations. SQL is not exposed to the user.

Rejected proposals write only an audit record and do not update CRM tables.

### Agent 5: Ask-CRM Agent

The Ask-CRM Agent answers conversational questions over approved CRM memory. It retrieves relevant rows from SQLite and uses an LLM to produce grounded answers.

It can answer questions about:

- recent meetings
- attendees
- follow-up tasks
- risks and objections
- open pipeline
- approval/rejection history

It does not mutate data.

## Reliability Controls

Close Loop separates warnings from hard blockers.

Approval is blocked when:

- account is missing
- product is missing
- open opportunity is missing
- meeting summary is missing
- the evidence critic marks account, product, or summary as missing or contradicted

Low model confidence does not automatically block the whole review. Instead, it raises the review risk level and keeps the human in control.

Stage updates are safer than meeting-log writeback. If the meeting is approved but the suggested stage movement is invalid, Close Loop still writes the approved meeting log, tasks, and audit entry, but skips the pipeline stage update and records why it was skipped.

The audit trail separates:

- original model proposal
- final human-approved proposal
- validation result
- critic result
- writeback plan
- applied changes
- model run metadata

## Models And Providers

The app uses a small provider wrapper configured through `.env`.

Default model stack:

- Gemini Flash / Flash-Lite for extraction
- Groq Qwen or Llama for critique and reasoning
- Gemini for Ask-CRM answers
- Provider fallback between Gemini and Groq
- Emergency deterministic/demo fallback if API calls fail and fallback mode is enabled

For JSON tasks, the model wrapper tries one repair pass before moving to provider fallback or deterministic/demo fallback.

The `.env` file is local only and should never be committed.

Example configuration:

```bash
MODEL_PROVIDER=gemini
DEMO_FALLBACK_ENABLED=true

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash-lite

GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3-32b
```

## Data

The source CRM data lives in `data/`:

- `accounts.csv`
- `products.csv`
- `sales_pipeline.csv`
- `sales_teams.csv`
- `data_dictionary.csv`

These CSV files are treated as immutable source data.

The local SQLite database is generated from the CSVs. Runtime app records are stored in:

- `meeting_logs`
- `tasks`
- `audit_log`

The local database file is ignored by git.

## Synthetic Data Policy

The provided CRM data contains accounts, products, sales teams, and pipeline records, but it does not contain unstructured meeting notes or transcripts.

For demo purposes, the repository includes synthetic meeting notes in `sample_notes/`.

These notes are intentionally limited to realistic sales-rep inputs and are tied to real CRM entities where possible. They simulate the kind of unstructured information the agent is designed to process:

- delivery risk
- competitor objection
- budget approval
- buying signal
- stakeholder attendance
- follow-up tasks
- ambiguity or missing information

The repository also includes a small labeled reliability fixture in `evals/meeting_notes/` for regression testing and future model evaluation.

## EDA

The data exploration is documented in:

```text
notebooks/close_loop_data_eda.ipynb
docs/DATA_EDA.md
```

The EDA covers:

- table sizes
- columns
- missing values
- unique counts
- deal-stage distribution
- open opportunities
- referential integrity
- product naming quirks
- rationale for synthetic meeting notes

Known data quirk:

```text
sales_pipeline uses GTXPro
products uses GTX Pro
```

The app handles this alias during validation.

## Local Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` file:

```bash
cp .env.example .env
```

Add Gemini and Groq API keys to `.env` if available.

Generate the SQLite database:

```bash
python db/setup_db.py
```

Run the app:

```bash
streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

## Running Without API Keys

The app can run without API keys if demo fallback is enabled:

```bash
DEMO_FALLBACK_ENABLED=true
```

In this mode, deterministic fallback logic keeps the demo usable, but the main intended workflow uses Gemini and Groq through the provider wrapper.

## Tests

Run the test suite:

```bash
pytest -q
```

The tests cover:

- CSV loading into SQLite
- source row-count preservation
- product alias handling
- validation behavior
- explicit approval blockers
- invalid stage-update skipping
- human-corrected writeback values
- approval and rejection writeback
- audit logging
- critic fallback behavior
- Ask-CRM fallback behavior
- unsupported CRM questions
- JSON repair metadata
- no writeback before approval

## Project Structure

```text
app.py                  Streamlit application
src/config.py           Environment and path configuration
src/database.py         SQLite setup, source loading, EDA helpers
src/llm.py              Gemini/Groq provider wrapper
src/extraction.py       Extraction Agent
src/critic.py           Evidence Critic Agent
src/validation.py       CRM Validation Agent
src/actions.py          Writeback Planner / Executor
src/crm_chat.py         Ask-CRM Agent
src/schemas.py          Pydantic schemas
src/matching.py         CRM matching and stage helpers
db/setup_db.py          Database creation script
data/                   Immutable CRM CSVs
sample_notes/           Synthetic demo meeting notes
evals/                  Labeled reliability fixtures
notebooks/              Executed EDA notebook
docs/                   EDA summary docs
tests/                  Data and agent tests
```

## Current Limitations

Close Loop is an MVP. It does not include:

- Salesforce, HubSpot, or Dynamics integration
- WhatsApp or voice ingestion
- production authentication
- multi-user permissions
- hosted database
- background jobs
- long-term vector memory
- production monitoring

The current goal is a reliable local demo of the agentic CRM workflow.

## Recommended Next Improvements

The highest-value next steps are:

1. Polish the frontend so the agentic workflow feels like a CRM assistant, not a developer demo.
2. Expand the labeled evaluation set and score live model outputs against it.
3. Add semantic retrieval over approved meeting logs and tasks.
4. Add prompt-versioned eval reports for Gemini and Groq model changes.
5. Add production-style observability if the app moves beyond a local MVP.

## Design Principle

Close Loop is not an autonomous CRM mutation bot. It is an AI-assisted CRM admin system with human approval, evidence, validation, and auditability built into the workflow.
