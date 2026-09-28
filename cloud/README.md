# Cloud service

FastAPI service deployed to Vercel.

## Responsibilities

- authenticate the Windows agent separately from command clients
- persist jobs in Supabase/Postgres
- parse natural-language print commands with Gemini structured output
- validate and enqueue print jobs
- expose job status
- never execute Windows commands

## Required production environment

- `AGENT_API_TOKEN`
- `COMMAND_API_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `GEMINI_API_KEY`
- optional: `GEMINI_MODEL`, `JOB_LEASE_SECONDS`, `AGENT_STALE_SECONDS`

The older `AGENT_SHARED_TOKEN` and `SUPABASE_SERVICE_ROLE_KEY` names remain accepted for migration.
