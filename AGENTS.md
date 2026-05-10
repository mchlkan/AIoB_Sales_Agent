# AGENTS.md

## Project

Build **RepLog AI**, a Streamlit MVP for a voice/text-to-CRM sales admin agent. The app should use the provided CRM CSV files, call a real LLM, propose structured CRM updates from messy meeting notes/transcripts, and require human approval before writing changes to a local SQLite database.

## MVP Focus

Prioritize one clean demo flow:

```text
meeting note or transcript
→ LLM extracts structured CRM proposal
→ app validates against local CRM data
→ user reviews confidence/evidence/warnings
→ user approves or rejects
→ approved update is written to SQLite
→ action is logged in audit log
→ user can ask simple CRM questions
```

## Tech Direction

- Python + Streamlit
- SQLite for local CRM database
- pandas for CSV loading
- Pydantic for structured validation
- Real LLM call through a small provider wrapper
- Prefer Qwen via OpenRouter/DashScope as the default low-cost model path
- Keep provider settings in `.env` / config, not hardcoded

## Data

Use the provided files:

- `accounts.csv`
- `products.csv`
- `sales_pipeline.csv`
- `sales_teams.csv`
- `data_dictionary.csv`

Add only minimal synthetic meeting notes needed for a strong demo.

## Product Constraints

- Do not implement real WhatsApp, Salesforce, HubSpot, or Dynamics integration for the MVP.
- Do not write CRM updates without an explicit approval step.
- Do show evidence, confidence, and validation warnings where useful.
- Keep the implementation simple, readable, and demoable.

## Quality Bar

The app should run locally, have a clear README, and make the main demo flow obvious. Prefer pragmatic, reliable code over complex abstractions.
