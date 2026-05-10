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

Preferred free/low-cost model paths:

- Gemini Flash or Flash-Lite free tier
- Groq free tier with Qwen or Llama models
- OpenRouter free models as a fallback
- Ollama local models as a no-cloud fallback

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

## Current Status

This repository currently contains the project brief, assignment instructions, and CRM CSV files. Application scaffolding and implementation will be added in follow-up tasks.

## Local Development

The app is not scaffolded yet. Once implemented, the expected local flow will be:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

