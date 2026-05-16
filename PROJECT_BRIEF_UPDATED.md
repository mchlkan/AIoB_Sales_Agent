# Close Loop — Voice/Text-to-CRM Sales Admin Agent MVP

## 1. Executive Summary

**Close Loop** is an AI sales admin agent for B2B sales teams. It turns messy sales meeting notes or voice memo transcripts into structured CRM update proposals, follow-up tasks, and searchable customer memory.

The ideal product vision is simple: a sales rep sends a WhatsApp or Teams voice memo after a customer meeting, and the agent handles the CRM admin work. For this MVP, the workflow is implemented in a local web app: the user pastes a meeting note or uploads/uses a transcript, the LLM extracts structured CRM information, the app validates it against local CRM data, and the user approves the proposed update before anything is written to the database.

The MVP should demonstrate a real LLM-powered workflow, not a mock-only demo. It should still be robust, transparent, and safe: the AI proposes, the human approves, and every accepted or rejected action is logged.

---

## 2. Course / Assignment Context

This project is for an **AI Impact on Business** assignment. The deliverable is a realistic MVP and pitch for an AI business application. The product should show:

- a concrete business problem and user,
- a plausible AI-enabled workflow,
- why AI creates value in this workflow,
- the main risks and limitations,
- how the system mitigates those risks through design.

The important responsible-AI angle is the **illusion gap**: the system may look autonomous, but it must make clear what the AI knows, where it might be wrong, and when a human needs to review or approve its output.

---

## 3. Product Vision

### Product name

**Close Loop**

### One-sentence pitch

> Close Loop turns messy sales voice notes and meeting notes into structured CRM updates, follow-up tasks, and searchable customer memory — with confidence, evidence, and human approval before writeback.

### Target users

- B2B sales representatives
- Account executives
- Relationship managers
- Sales managers who need better pipeline visibility

### Ideal future workflow

```text
Sales rep sends WhatsApp/Teams voice memo
→ agent transcribes audio
→ LLM extracts CRM-relevant facts
→ system matches account/opportunity/product
→ agent proposes CRM updates and tasks
→ rep approves or rejects
→ approved changes are written to CRM
→ manager can ask questions over updated CRM history
```

### MVP workflow

For the MVP, do **not** depend on real WhatsApp integration. Simulate the same workflow in a local Streamlit app:

```text
Text note or audio/transcript input
→ LLM extraction
→ deterministic validation against CRM data
→ proposed CRM update screen
→ human approval/rejection
→ SQLite writeback
→ audit log
→ ask-your-CRM chat
```

This keeps the demo controllable while still showing the real product logic.

---

## 4. Business Problem

Sales reps spend too much time after customer meetings updating CRM systems manually. They need to write meeting summaries, update opportunity stages, log objections, create follow-up tasks, and keep account records current.

This creates several business problems:

- CRM updates are delayed or skipped.
- Notes are inconsistent across reps.
- Important objections, buying signals, and next steps get lost.
- Follow-up tasks are forgotten.
- Sales managers lack accurate pipeline visibility.
- CRM data quality declines over time.

Close Loop addresses this by converting unstructured meeting notes into structured CRM actions, while keeping the human in control.

---

## 5. MVP Goal

Build a small but working AI system that demonstrates the core value proposition:

> A sales rep gives the system a messy meeting note or transcript. The LLM extracts structured CRM information. The app validates and displays proposed updates with confidence and evidence. The rep approves the proposal. The database is updated and the action is logged. The updated CRM history can then be queried in natural language.

The MVP should prioritize a clean, reliable demo flow over production-grade integrations.

---

## 6. Core MVP Features

### 6.1 CRM data browser

Load the provided CSV data into a local SQLite database and allow the user to inspect key CRM tables.

Expected data files:

- `accounts.csv`
- `products.csv`
- `sales_pipeline.csv`
- `sales_teams.csv`
- `data_dictionary.csv`

The main CRM table is the sales pipeline/opportunities data. Accounts, products, and sales teams are reference data.

### 6.2 Meeting note / transcript input

The app should support at least text input. Optional but valuable: allow upload of an audio memo and transcribe it before extraction.

For the MVP, the key requirement is not real WhatsApp. The key requirement is to demonstrate the voice-note-to-CRM logic. A pasted transcript is acceptable; audio upload is a nice-to-have.

### 6.3 LLM extraction

Use a real LLM call to extract structured information from the meeting note/transcript.

The extraction should return structured JSON with fields such as:

- account name
- opportunity identifier or likely matched opportunity
- sales agent, if mentioned or inferable
- products discussed
- meeting summary
- customer needs
- objections or risks
- buying signals
- suggested opportunity stage update
- next steps / follow-up tasks
- due dates, if mentioned
- confidence scores
- evidence snippets from the source note
- ambiguity flags or missing information

The app should validate the LLM output with Pydantic or equivalent schema validation.

### 6.4 CRM matching and validation

After extraction, the app should deterministically check the proposal against the CRM database.

Examples:

- Does the account exist?
- Is there an open opportunity for that account?
- Is the product known?
- Is the suggested stage valid?
- Are multiple possible opportunities plausible?
- Is the output missing important information?

The validation layer should not blindly trust the LLM. It should show warnings when something is ambiguous or invalid.

### 6.5 Human approval step

The AI must not directly write CRM updates without approval.

The app should show a review screen with:

- proposed account/opportunity match,
- proposed summary,
- proposed stage change,
- proposed tasks,
- objections/risks,
- confidence,
- evidence snippets,
- validation warnings.

The user can approve or reject. Approved changes are written to SQLite. Rejected changes are logged but not applied.

### 6.6 CRM writeback

On approval, write the update into local SQLite tables. Use the existing CRM data as the base and add new MVP tables such as:

- `meeting_logs`
- `tasks`
- `audit_log`

The original CSV data should remain reproducible. It is fine to create a local `crm.db` from the CSVs.

### 6.7 Audit log

Every approve/reject decision should be logged with:

- timestamp,
- source note/transcript,
- extracted proposal,
- validation result,
- approval status,
- applied changes,
- model/provider used if available.

This is important for the responsible-AI story.

### 6.8 Ask-your-CRM chat

The app should include a simple natural-language Q&A feature over the local CRM data and meeting logs.

Example questions:

- “Which open opportunities mentioned delivery risk?”
- “What follow-up tasks are overdue?”
- “Summarize recent meetings for this account.”
- “Which deals have strong buying signals?”
- “What objections came up most often?”

Keep this simple. It does not need to be a perfect general-purpose analytics agent. It should support a few useful CRM questions for the demo.

---

## 7. AI / Model Strategy

The MVP should use a real LLM, not only deterministic mock outputs.

Recommended default model strategy:

- Use an OpenAI-compatible client abstraction.
- Make **Qwen via OpenRouter or DashScope** the preferred low-cost/free default.
- Keep the model provider configurable via environment variables.
- Optionally support Gemini or Groq as backup providers.

Example environment variables:

```env
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=qwen/qwen3.6-plus:free

# Optional alternatives
GEMINI_API_KEY=
GROQ_API_KEY=
```

The code should not be hardcoded to one provider if this can be avoided. Use one small wrapper module for model calls.

The LLM should be asked to output strict JSON. The app should parse and validate the JSON. If parsing fails, show a useful error and allow retry.

---

## 8. Recommended Tech Stack

Keep the MVP simple and transparent.

- **Frontend:** Streamlit
- **Backend:** Python
- **Database:** SQLite
- **Data handling:** pandas
- **Validation:** Pydantic
- **LLM calls:** OpenAI-compatible SDK or lightweight provider wrapper
- **Audio transcription:** optional nice-to-have

Avoid unnecessary production complexity:

- no real Salesforce/HubSpot/Dynamics integration,
- no real WhatsApp integration,
- no complex authentication,
- no cloud deployment requirement,
- no multi-agent orchestration unless it clearly improves the demo.

---

## 9. Suggested Repository Structure

```text
close-loop/
  README.md
  PROJECT_BRIEF.md
  AGENTS.md
  requirements.txt
  .env.example
  app.py

  data/
    accounts.csv
    products.csv
    sales_pipeline.csv
    sales_teams.csv
    data_dictionary.csv

  sample_notes/
    note_01_delivery_risk.txt
    note_02_budget_approved.txt
    note_03_competitor_objection.txt

  db/
    setup_db.py
    crm.db

  src/
    config.py
    database.py
    llm.py
    schemas.py
    extraction.py
    matching.py
    validation.py
    actions.py
    audit.py
    crm_chat.py
    utils.py

  prompts/
    extractor.md
    crm_chat.md
```

The structure can be simplified if needed, but the separation between LLM extraction, deterministic validation, approval/writeback, and audit logging should remain clear.

---

## 10. Suggested Database Additions

Use the CSV data as the base CRM. Add tables like the following.

### `meeting_logs`

Stores approved meeting summaries and extracted meeting information.

Suggested fields:

- `id`
- `created_at`
- `account_id` or `account_name`
- `opportunity_id`
- `sales_agent`
- `summary`
- `products_discussed`
- `objections`
- `buying_signals`
- `next_steps`
- `source_note`
- `model_provider`
- `model_name`

### `tasks`

Stores follow-up tasks proposed by the agent and approved by the user.

Suggested fields:

- `id`
- `created_at`
- `account_name`
- `opportunity_id`
- `task_description`
- `owner`
- `due_date`
- `status`
- `source_meeting_log_id`

### `audit_log`

Stores every approval/rejection decision.

Suggested fields:

- `id`
- `created_at`
- `source_note`
- `proposal_json`
- `validation_json`
- `decision` (`approved` / `rejected`)
- `applied_changes_json`
- `model_provider`
- `model_name`

---

## 11. Example Meeting Note

```text
Just finished a call with Acme Corp. Sarah from procurement and James from infrastructure joined. They are still interested in GTX Pro for their Q3 refresh, but they are worried about delivery timing and whether our team can support integration. Sarah asked me to send a revised quote and implementation timeline by Friday. I think the opportunity should move from Engaging to Proposal if we can confirm delivery dates. Please create a follow-up task for me to send the revised quote.
```

Expected behavior:

- Match account: `Acme Corp` if present in the CRM data, otherwise show a warning.
- Match product: `GTX Pro` or closest valid product name.
- Extract objections: delivery timing, integration support.
- Extract task: send revised quote and implementation timeline by Friday.
- Suggest stage update: from Engaging to Proposal, with a confidence score and evidence.
- Ask for human approval before writing.

---

## 12. Demo Script

A strong demo should follow one simple path:

1. Open the Streamlit app.
2. Show that CRM data has been loaded from the CSV files.
3. Paste or upload a sales meeting note/transcript.
4. Click “Analyze meeting”.
5. Show the LLM-generated structured proposal.
6. Show account/opportunity/product matching and validation warnings.
7. Approve the update.
8. Show the new meeting log, task, and audit log entry.
9. Ask a CRM question such as: “Which open opportunities mentioned delivery risk?”
10. Explain that the production interface could be WhatsApp/Teams voice notes, while the MVP demonstrates the same backend workflow locally.

---

## 13. Success Criteria

The MVP is successful if it can demonstrate:

- real LLM extraction from messy sales notes,
- structured CRM update proposals,
- deterministic validation against CRM data,
- confidence/evidence display,
- human approval before database writeback,
- audit logging,
- basic natural-language CRM querying,
- a credible path from local MVP to WhatsApp/Teams/CRM integration.

It does not need to be production-ready. It does need to be clear, reliable, and easy to explain.

---

## 14. Design Principle

The core design principle is:

> The AI should reduce admin work, but it should not silently make business-critical CRM changes. It should propose, explain, and ask for approval.

This is the key responsible-AI message of the project.
