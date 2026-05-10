# RepLog AI

RepLog AI is a Streamlit MVP for a voice/text-to-CRM sales admin agent. It turns messy sales meeting notes or transcripts into structured CRM update proposals, validates them against local CRM data, and requires human approval before writing changes to a local SQLite database.

## MVP Goal

The demo focuses on one clear workflow:

```text
meeting note or transcript
-> LLM extracts structured CRM proposal
-> app validates against local CRM data
-> user reviews confidence, evidence, and warnings
-> user approves or rejects
-> approved update is written to SQLite
-> action is logged in audit log
-> user can ask simple CRM questions
```

The product principle is simple: the AI reduces sales admin work, but it does not silently make business-critical CRM changes.

## Data

The MVP uses the CSV files in `data/` as the local CRM source:

- `accounts.csv`
- `products.csv`
- `sales_pipeline.csv`
- `sales_teams.csv`
- `data_dictionary.csv`

The CSV data should remain reproducible. Runtime database files generated from the CSVs should live locally and should not be committed.

## Planned Stack

- Python
- Streamlit
- SQLite
- pandas
- Pydantic
- Configurable LLM provider wrapper

Preferred free-tier model paths:

- Gemini Flash or Flash-Lite for extraction and Ask CRM
- Groq free tier with Qwen or Llama models for critique/reasoning and fallback

Provider settings should live in `.env`, not in source code.

## Responsible AI Design

RepLog AI should make uncertainty visible. The review screen should show:

- proposed account and opportunity match
- proposed CRM updates
- follow-up tasks
- confidence scores
- evidence snippets
- validation warnings
- approve/reject controls

Every approval or rejection should be written to an audit log.

## Architecture

The MVP is implemented as a five-step backend agent workflow:

- **Agent #1: Extraction Agent** converts a messy meeting note into structured JSON. It uses Gemini by default and can fall back through the model router.
- **Agent #2: Evidence Critic Agent** checks whether the extracted fields are supported by the source note and flags inferred, missing, or contradicted fields.
- **Agent #3: CRM Validation Agent** checks the proposal against local CRM data and prepares warnings, confidence, evidence, and matches for human review.
- **Agent #4: Writeback Planner / Executor** runs behind the scenes after approval and writes safe parameterized SQLite updates. SQL is not exposed to the user.
- **Agent #5: Ask-CRM Agent** retrieves relevant CRM records and uses the model wrapper to answer conversationally, falling back to deterministic answers when provider calls are unavailable.

The human approval gate sits between validation and writeback. Rejected proposals are audited but not applied.

## Synthetic Data Policy

The source CRM CSV files are not edited. The only synthetic demo inputs are meeting notes in `sample_notes/`, because the provided CRM data does not include unstructured meeting transcripts, objections, buying signals, or follow-up tasks. The sample notes are tied to real accounts, products, agents, and open opportunities from the provided data.

The app-generated runtime data lives in SQLite tables:

- `meeting_logs`
- `tasks`
- `audit_log`

The local database file is generated from source CSVs and is ignored by git.

## Current Status

The repository includes a runnable Streamlit MVP with:

- data loading from CSV to SQLite
- EDA/data-quality summary
- executed CRM data EDA notebook in `notebooks/replog_ai_data_eda.ipynb`
- sample synthetic meeting notes
- LLM extraction wrapper with demo fallback
- LLM evidence critic with deterministic fallback
- deterministic CRM validation and human review
- approval/rejection writeback and audit logging
- retrieval-backed Ask CRM answers over local tables

## Local Development

Create a virtual environment, install dependencies, and generate the local SQLite database:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python db/setup_db.py
streamlit run app.py
```

If `.env` has no API key, the app still runs with clearly labeled fallback components. To use the agentic model stack, set Gemini and Groq API keys in `.env`.

## Tests

Run the focused data/agent tests with:

```bash
pytest -q
```
