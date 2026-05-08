# RepLog AI — Voice/Text-to-CRM Sales Admin Agent

## 1. Project Context

This project is for the course **AI Impact on Business**.

The goal is to build a small, realistic MVP of an AI business application. The product should solve a real business problem, be technically feasible, and demonstrate responsible AI design.

The idea: **RepLog AI**, an AI sales admin agent that helps B2B sales reps turn messy post-meeting notes into structured CRM updates.

Sales reps often meet customers, discuss opportunities, objections, next steps, and deal status. After the meeting, they need to manually update a CRM such as Salesforce, HubSpot, or Dynamics. This includes writing meeting summaries, updating opportunity stages, creating follow-up tasks, and logging important customer information.

This manual CRM work is time-consuming, inconsistent, and often delayed. RepLog AI reduces this admin burden by using an LLM to extract structured information from raw meeting notes and propose CRM updates.

Important: The system should **not automatically write changes without user approval**. The AI should propose updates, show evidence and confidence, and only write to the database once the user approves.

---

## 2. Product Summary

**Product name:** RepLog AI

**One-sentence pitch:**

> RepLog AI turns messy sales meeting notes into structured CRM updates, follow-up tasks, and searchable customer memory — with human approval before anything is written.

**Target user:**

B2B sales representatives, account executives, and relationship managers who regularly meet customers and need to update CRM records afterwards.

**MVP context:**

For the MVP, we use a public fictional CRM/sales dataset, preferably the **Maven Analytics CRM Sales Opportunities** dataset, which contains B2B sales data around accounts, products, sales teams, and opportunities.

The meeting notes can be synthetic/fake, but should be realistic and aligned with the CRM data.

---

## 3. Core Business Problem

Sales reps spend too much time on post-meeting CRM administration instead of selling.

Typical current workflow:

1. Sales rep has a customer meeting.
2. Rep writes meeting notes manually.
3. Rep updates CRM fields manually.
4. Rep creates follow-up tasks manually.
5. Manager later checks CRM for pipeline visibility.

Problems:

- CRM updates are often delayed.
- Notes are inconsistent across reps.
- Important customer objections and decisions get lost.
- Follow-up tasks may be forgotten.
- Managers get poor pipeline visibility.
- CRM data quality suffers.

This MVP should demonstrate how AI can reduce manual admin work while improving CRM data quality.

---

## 4. MVP Scope

The MVP should be simple, reliable, and demoable.

The user should be able to:

1. View CRM data from a small local database.
2. Paste a raw sales meeting note into a web interface.
3. Click a button to generate a proposed CRM update.
4. See extracted structured fields.
5. See matched CRM account and opportunity.
6. See confidence/source evidence for the proposed updates.
7. Approve or reject the proposed update.
8. If approved, write the update to the local database.
9. Ask simple natural-language questions about CRM/meeting history.

---

## 5. Recommended Tech Stack

Use the simplest stack possible.

### Preferred MVP Stack

- **Frontend:** Streamlit
- **Backend:** Python
- **Database:** SQLite
- **LLM provider:** Google Gemini Flash API, Groq, OpenAI, or Anthropic
- **Validation:** Pydantic
- **Data loading:** pandas
- **SQL execution:** sqlite3 or SQLAlchemy

### Suggested Repo Structure

```text
replog-ai/
  README.md
  PROJECT_BRIEF.md
  requirements.txt
  .env.example

  app.py

  data/
    raw/
      accounts.csv
      products.csv
      sales_teams.csv
      sales_pipeline.csv
    synthetic/
      sample_meeting_notes.json

  db/
    setup_db.py
    crm.db

  src/
    config.py
    database.py
    llm.py
    schemas.py
    extraction.py
    validation.py
    actions.py
    chat.py
    utils.py

  prompts/
    extractor.md
    validator.md
    crm_chat.md
```

---

## 6. Data

### Public CRM Data

Use the Maven Analytics CRM Sales Opportunities dataset if possible.

It typically contains tables such as:

- accounts
- products
- sales teams
- sales opportunities / pipeline

The exact CSV names may differ. Adapt the loader to the downloaded files.

### Synthetic Data to Add

Create synthetic meeting notes that match accounts, products, and opportunities in the dataset.

Example synthetic meeting note:

```text
I met with Acme Corp's IT procurement team today. Sarah from procurement and James from infrastructure joined the call. They are interested in 200 units of the GTX Pro server line for their Q3 data-center refresh. Their main concern is delivery lead time and integration support. Sarah asked us to send a revised quote by Friday. Please move the opportunity from prospecting to evaluation and create a follow-up task to send pricing and implementation timeline.
```

Expected extracted output:

```json
{
  "account_name": "Acme Corp",
  "contacts": ["Sarah", "James"],
  "products_discussed": ["GTX Pro server line"],
  "quantity": 200,
  "meeting_summary": "Acme Corp is evaluating GTX Pro servers for a Q3 data-center refresh. They are interested but concerned about delivery lead time and integration support.",
  "objections": ["delivery lead time", "integration support"],
  "next_steps": [
    {
      "task": "Send revised quote",
      "owner": "sales rep",
      "due_date": "Friday"
    },
    {
      "task": "Send pricing and implementation timeline",
      "owner": "sales rep",
      "due_date": null
    }
  ],
  "suggested_opportunity_stage": "Evaluation"
}
```

---

## 7. Database Design

Use the Maven dataset as the base. Add extra tables for meeting logs and tasks.

### Minimum Tables

Use existing imported tables where available:

```sql
accounts
products
sales_teams
opportunities
```

Add these MVP tables:

```sql
CREATE TABLE IF NOT EXISTS meeting_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT,
    opportunity_id TEXT,
    meeting_date TEXT,
    summary TEXT,
    attendees TEXT,
    topics TEXT,
    objections TEXT,
    next_steps TEXT,
    source_note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT,
    opportunity_id TEXT,
    task_description TEXT,
    owner TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT,
    account_id TEXT,
    opportunity_id TEXT,
    proposed_change_json TEXT,
    approved INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. AI Workflow

Do not let the LLM directly execute database writes.

The LLM should produce structured JSON. The application should validate it and then use deterministic Python code to write to the database.

### Step 1: User Input

User pastes a raw meeting note into Streamlit.

### Step 2: Extraction Agent

The LLM extracts structured CRM information.

Output should follow a Pydantic schema.

### Step 3: CRM Matching / Validation

The system checks:

- Does the account exist?
- Does the opportunity exist?
- Are there multiple possible account matches?
- Are products mentioned in the CRM?
- Are required fields missing?
- Is the suggested opportunity stage valid?
- Are dates ambiguous?

If ambiguous, the UI should ask the user to confirm.

### Step 4: Proposed CRM Actions

The system creates structured proposed actions, such as:

```json
{
  "actions": [
    {
      "type": "insert_meeting_log",
      "account_id": "ACC-001",
      "opportunity_id": "OPP-003",
      "summary": "Customer is evaluating GTX Pro servers for Q3 refresh.",
      "source_evidence": "They are interested in 200 units of the GTX Pro server line for their Q3 data-center refresh."
    },
    {
      "type": "update_opportunity_stage",
      "opportunity_id": "OPP-003",
      "old_value": "Prospecting",
      "new_value": "Evaluation",
      "source_evidence": "Please move the opportunity from prospecting to evaluation."
    },
    {
      "type": "create_task",
      "account_id": "ACC-001",
      "opportunity_id": "OPP-003",
      "task_description": "Send revised quote",
      "due_date": "Friday",
      "source_evidence": "Sarah asked us to send a revised quote by Friday."
    }
  ]
}
```

### Step 5: Human Approval

The user sees the proposed updates in a review panel.

The user must click **Approve** before the database is updated.

### Step 6: Database Writeback

Only approved changes are written to SQLite.

### Step 7: Ask-your-CRM Chat

User can ask questions like:

- What were the last 3 meetings with Acme about?
- Which customers mentioned delivery lead time?
- Which tasks are overdue?
- Which opportunities moved to evaluation?
- What objections are most common?

The chat should query the database and summarize results.

---

## 9. Responsible AI Features

These features are important for the assignment and should be visible in the UI.

### Must-have

1. **Human approval before writeback**
   - AI proposes updates.
   - Human approves before database changes.

2. **Source evidence**
   - Each suggested field should show the original text evidence from the meeting note.

3. **Confidence or uncertainty**
   - Show low/medium/high confidence for extracted fields.
   - If uncertain, ask the user to confirm.

4. **Audit trail**
   - Save proposed changes and whether they were approved.

### Nice-to-have

1. Ambiguity clarification:
   - If multiple accounts match, ask the user which one is correct.

2. Manager dashboard:
   - Open follow-ups
   - Most mentioned objections
   - Recent meetings
   - Opportunities updated this week

3. ROI widget:
   - Estimate time saved per rep/week.

4. Compliance guardrail:
   - Warn if the note contains promises, discounts, legal commitments, or sensitive information.

---

## 10. UI Requirements

Use Streamlit for speed.

### Page Layout

Recommended Streamlit pages/sections:

1. **Header**
   - Product name: RepLog AI
   - Subtitle: Voice/Text-to-CRM sales admin agent

2. **CRM Context**
   - Show selected account/opportunity or allow user to search/select one.
   - Optional: show a small CRM table preview.

3. **Meeting Note Input**
   - Text area for raw meeting note.
   - Optional button to load example note.

4. **Generate CRM Update**
   - Button triggers extraction + validation.

5. **Review Panel**
   Show a table with columns:
   - Field
   - Suggested value
   - Source evidence
   - Confidence
   - Status / warning

6. **Proposed Actions**
   Show actions:
   - Insert meeting log
   - Update opportunity stage
   - Create task

7. **Approve Button**
   Writes approved actions to database.

8. **Ask Your CRM**
   Simple chat input and response.

9. **Audit Log**
   Optional display of recent approved/rejected actions.

---

## 11. LLM Prompting Guidelines

### Extraction Prompt

The extractor should return strict JSON only.

It should extract:

- account name
- contacts
- products discussed
- quantity
- meeting summary
- topics
- objections
- decisions
- next steps
- suggested opportunity stage
- confidence per field
- source evidence per field
- missing information

The prompt should explicitly say:

- Do not invent information.
- Use null if information is missing.
- Keep source evidence as exact or near-exact text from the note.
- Return valid JSON only.

### Validation Prompt

The validator receives:

- extracted JSON
- possible CRM account matches
- possible opportunities
- allowed opportunity stages
- product list

It should return:

- selected account ID or ambiguity warning
- selected opportunity ID or ambiguity warning
- validation warnings
- missing fields
- whether human clarification is needed

### CRM Chat Prompt

The chat agent should answer based only on database query results.

It should not invent CRM history.

If data is missing, it should say so.

---

## 12. Pydantic Schemas

Create schemas similar to these.

```python
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class FollowUpTask(BaseModel):
    task: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    source_evidence: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

class ExtractedMeeting(BaseModel):
    account_name: Optional[str]
    contacts: List[str] = []
    products_discussed: List[str] = []
    quantity: Optional[int] = None
    meeting_summary: str
    topics: List[str] = []
    objections: List[str] = []
    decisions: List[str] = []
    next_steps: List[FollowUpTask] = []
    suggested_opportunity_stage: Optional[str] = None
    confidence: Dict[str, float] = {}
    source_evidence: Dict[str, str] = {}
    missing_information: List[str] = []
```

```python
class CRMAction(BaseModel):
    type: str
    account_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    task_description: Optional[str] = None
    due_date: Optional[str] = None
    source_evidence: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
```

---

## 13. Implementation Plan for Coding Agent

Build incrementally.

### Phase 1 — Data and Database

- Create `requirements.txt`.
- Create `db/setup_db.py`.
- Load CSV files from `data/raw/`.
- Create SQLite database at `db/crm.db`.
- Add `meeting_logs`, `tasks`, and `audit_log` tables.
- Add a few synthetic meeting notes in `data/synthetic/sample_meeting_notes.json`.

### Phase 2 — Basic Streamlit App

- Create `app.py`.
- Show CRM data preview.
- Add meeting note text area.
- Add button: "Generate CRM Update".
- Add example note loader.

### Phase 3 — LLM Extraction

- Create `src/llm.py`.
- Support environment variable for API key.
- Use Gemini Flash by default if possible.
- Add fallback/mock mode if no API key exists.
- Create `src/extraction.py`.
- Return structured JSON matching Pydantic schema.

### Phase 4 — Validation

- Create `src/validation.py`.
- Match extracted account name against accounts table.
- Match products against products table.
- Match opportunity if possible.
- Flag ambiguity.
- Show validation warnings in UI.

### Phase 5 — Actions and Approval

- Create `src/actions.py`.
- Convert validated extraction into proposed CRM actions.
- Show actions in Streamlit.
- Add "Approve Update" button.
- On approval:
  - Insert meeting log.
  - Insert tasks.
  - Update opportunity stage if supported by schema.
  - Insert audit log.

### Phase 6 — Ask-your-CRM Chat

- Create `src/chat.py`.
- Implement simple database-backed question answering.
- For MVP, support common question types:
  - last meetings for account
  - open tasks
  - objections mentioned
  - recent opportunity updates
- Use LLM to summarize query results if API key exists.
- Otherwise return raw query results.

### Phase 7 — Polish

- Add confidence/source evidence review table.
- Add warnings for low-confidence fields.
- Add audit log preview.
- Add README with setup instructions.

---

## 14. Important Engineering Constraints

- Keep it simple.
- Do not build authentication.
- Do not integrate real Salesforce.
- Do not train a model.
- Do not let the LLM directly execute arbitrary SQL.
- Use synthetic meeting notes.
- Use local SQLite.
- Prioritize demo reliability over complexity.
- Include mock mode so the app works even without an API key.

---

## 15. Environment Variables

Create `.env.example`:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
DATABASE_PATH=db/crm.db
```

The app should not crash if no API key is available. It should use mock extraction for demo purposes.

---

## 16. Example Demo Flow

1. Open Streamlit app.
2. Show public CRM dataset loaded.
3. Paste example meeting note.
4. Click "Generate CRM Update".
5. Show extracted structured fields.
6. Show account/opportunity match.
7. Show confidence and source evidence.
8. Show proposed CRM actions.
9. Click "Approve Update".
10. Show success message.
11. Ask: "What were the last meetings with Acme about?"
12. App answers based on stored meeting logs.

---

## 17. Success Criteria

The MVP is successful if it can demonstrate:

- A realistic business problem.
- AI extraction from messy meeting notes.
- Structured CRM update proposal.
- Human approval before database writeback.
- Source evidence and confidence/uncertainty.
- A small searchable CRM memory.

The app does not need to be production-ready. It needs to be a clear, credible prototype for a 2-minute pitch and a small YC-style deck.

---

## 18. Suggested Pitch Framing

Use this framing in the README/deck:

> B2B sales reps spend too much time after meetings updating CRM records. RepLog AI turns a quick meeting recap into structured CRM updates, follow-up tasks, and searchable customer memory. Unlike a black-box automation tool, it shows confidence and source evidence for every proposed update and requires human approval before writing to the CRM.

---

## 19. Do Not Overbuild

Avoid:

- Complex multi-agent frameworks
- Full Salesforce API integration
- User login
- Production deployment complexity
- Real customer data
- Training/fine-tuning
- Large dashboard systems

Focus on:

- Clean demo
- Reliable extraction
- Human approval
- Auditability
- Business relevance
