# Close Loop Data EDA

This MVP treats the provided CSVs as immutable source CRM data. The app loads them into SQLite and creates new runtime tables for approved meeting logs, tasks, and audit events.

## Source Tables

- `accounts.csv`: company/account reference data.
- `products.csv`: product catalog.
- `sales_pipeline.csv`: opportunity pipeline and deal stages.
- `sales_teams.csv`: sales agents, managers, and regions.
- `data_dictionary.csv`: field descriptions for the source data.

## Findings To Surface In The App

- `sales_pipeline.csv` has 8,800 opportunities and is the main CRM table.
- The pipeline uses four source stages: `Won`, `Lost`, `Engaging`, and `Prospecting`.
- Open opportunities are represented by `Engaging` and `Prospecting`.
- Some open opportunities have missing account names; those are useful validation examples but not ideal for the main happy-path demo.
- The product catalog contains `GTX Pro`, while the pipeline uses `GTXPro`. The validation agent should detect and explain this mismatch.
- The source data has no meeting notes, objections, buying signals, or follow-up task history.

## Synthetic Data Rationale

The only synthetic demo inputs are meeting notes/transcripts. This mirrors a real sales setting: structured CRM tables exist, while important post-meeting context often lives in messy notes, voice memos, or chat messages. The synthetic notes are tied to real accounts, real products, real agents, and real open opportunities from the provided CRM data.

