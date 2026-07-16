# Notion Onboarding

This document defines how new users connect English Podcast Learning Agent to
Notion after installing the skill.

## Goal

The user should not need to understand the Notion database schema. The skill or
setup script should handle:

- Creating the required databases.
- Writing database IDs back to `.env`.
- Validating the workspace.
- Creating optional sample data.
- Giving the user the next command to run.

## Mode 1: Guided Local Setup

Use this mode when the user wants the Python project to run independently from
Codex.

Required:

- Python dependencies installed with `pip install -r requirements.txt`.
- `NOTION_TOKEN` from an internal Notion integration.
- A parent Notion page shared with that integration.

Flow:

1. User copies `.env.example` to `.env`.
2. User adds `NOTION_TOKEN`.
3. User runs:

   ```bash
   python -m src.notion.setup_workspace --parent-page-id <notion_page_url_or_id>
   ```

4. The setup script normalizes the parent page URL or ID.
5. The setup script creates:
   - `Podcast Library`
   - `Expression Database`
   - `Weekly Review`
6. The setup script writes database IDs back to `.env`.
7. User runs:

   ```bash
   python -m src.notion.check_workspace
   ```

8. User can create sample data:

   ```bash
   python -m src.notion.create_example_data
   ```

## Mode 2: Codex Assisted Setup

Use this mode when the user is working inside Codex and has connected the
Notion plugin.

Flow:

1. User connects the Notion plugin in Codex.
2. Codex creates or inspects the Notion workspace interactively.
3. Codex validates that the three databases exist with the required properties.
4. Codex returns database IDs.
5. User syncs those database IDs into `.env` for local CLI execution.
6. User runs:

   ```bash
   python -m src.notion.check_workspace
   ```

## Boundary

The Codex Notion plugin and the Python `notion-client` SDK are different
integration layers.

- The plugin lets Codex interact with Notion during assisted setup.
- The local Python project uses `NOTION_TOKEN` and database IDs from `.env`.

Installing the Notion plugin does not automatically expose a token to the local
Python process. The local CLI still needs `.env` configuration unless all
Notion actions are performed manually through Codex.

## First-Run Checklist

The setup script can print the checklist:

```bash
python -m src.notion.setup_workspace --print-onboarding
```

Expected completed state:

- `.env` contains `NOTION_TOKEN`.
- `.env` contains `NOTION_PARENT_PAGE_ID`.
- `.env` contains all three Notion database IDs.
- `python -m src.notion.check_workspace` reports:

  ```text
  ✓ Podcast Library
  ✓ Expression Database
  ✓ Weekly Review

  Missing:
  None
  ```
