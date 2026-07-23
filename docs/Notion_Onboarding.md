# Notion Onboarding

This document defines the single supported flow for connecting English Audio
Learning Agent to Notion after installing the Skill.

## Goal

The user should not need to understand the Notion database schema. The skill or
setup script should handle:

- Creating the required databases.
- Writing database IDs back to `.env`.
- Validating the workspace.
- Creating optional sample data.
- Giving the user the next command to run.

## Setup Flow

Required:

- Project dependencies installed in `.venv`.
- `NOTION_TOKEN` from an internal Notion integration.
- A parent Notion page shared with that integration.

Flow:

1. Create the project environment:

   ```bash
   python3 -m venv .venv
   ./.venv/bin/python scripts/bootstrap_environment.py
   ```

2. Create a Notion internal integration and copy its token.
3. Create a parent page, such as `English Audio Learning Agent`.
4. Share the parent page with the integration through the Notion page's
   `Share` menu.
5. Copy `.env.example` to `.env` and set `NOTION_TOKEN`.
6. Run:

   ```bash
   ./.venv/bin/python -m src.notion.setup_workspace \
     --parent-page-id "<notion-parent-page-url-or-id>"
   ```

7. The setup script normalizes the parent page URL or ID and creates:
   - `Podcast Library`
   - `Expression Database`
   - `Weekly Review` (stores the Weekly Reflection learning note)
   - `Vocabulary Database`
8. The setup script connects the required relations and writes the parent page
   ID plus all four database IDs back to `.env`.
9. Validate the workspace:

   ```bash
   ./.venv/bin/python -m src.notion.check_workspace
   ```

10. Optional: create sample data:

   ```bash
   ./.venv/bin/python -m src.notion.create_example_data
   ```

## Boundary

The local Python project publishes through the `notion-client` SDK using
`NOTION_TOKEN` and database IDs from `.env`. A Codex Notion connector, if
installed, does not expose credentials to this local process and does not
replace the setup above.

## First-Run Checklist

The setup script can print the checklist:

```bash
./.venv/bin/python -m src.notion.setup_workspace --print-onboarding
```

Expected completed state:

- `.env` contains `NOTION_TOKEN`.
- `.env` contains `NOTION_PARENT_PAGE_ID`.
- `.env` contains all four Notion database IDs.
- `./.venv/bin/python -m src.notion.check_workspace` reports:

  ```text
  ✓ Podcast Library
  ✓ Expression Database
  ✓ Weekly Review
  ✓ Vocabulary Database

  Missing:
  None
  ```
