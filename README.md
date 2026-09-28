# AI Print Agent

Cloud AI + secure Windows local agent for natural-language printing.

## What it does

A user can send a command such as:

> Print all PDFs in H:\PRINT FILE, double sided, and use the file name order.

The cloud AI converts that request into a strict print plan. The Windows agent validates the folder against its local allow-list, analyzes each document, applies the local print policy, and sends each file to the installed printer sequentially.

The cloud never receives arbitrary Windows shell access and never reads the user's local files.

## Architecture

~~~text
User / API client
       |
       | authenticated natural-language command
       v
Vercel + FastAPI
       |
       +--> Gemini structured-output planner
       |
       +--> Supabase/Postgres durable job queue
                         |
                         | HTTPS polling
                         v
                 Windows Local Agent
                         |
              +----------+----------+
              |                     |
       File validation          Document analysis
              |                     |
              +----------+----------+
                         |
                  Sequential queue
                         |
                         v
                Windows printer DC
                         |
                         v
                 Brother HL-L2400D
~~~

## Repository

~~~text
Ai-agent/
├── cloud/
│   ├── app/
│   │   ├── ai.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── security.py
│   │   └── store.py
│   ├── schema.sql
│   ├── requirements.txt
│   ├── README.md
│   └── vercel.json
├── local_agent/
│   ├── agent.py
│   ├── config.example.json
│   ├── print_rules.json
│   ├── requirements.txt
│   └── services/
│       ├── document_analyzer.py
│       ├── file_manager.py
│       ├── office_converter.py
│       ├── print_engine.py
│       ├── printer.py
│       └── queue_manager.py
└── tests/
    └── test_local_agent.py
~~~

## Cloud API

### Health

GET /api/health

Returns database and AI readiness. A production deployment is considered ready only when both are configured and the database responds.

### Agent heartbeat

POST /api/agents/heartbeat

Authenticated with AGENT_API_TOKEN.

### Natural-language command

POST /api/commands

Authenticated with COMMAND_API_TOKEN.

Example body:

~~~json
{
  "agent_id": "hari-ai",
  "command": "Print all PDFs in H:\\PRINT FILE, double sided, in file name order.",
  "idempotency_key": "print-2026-09-28-001"
}
~~~

### Job status

GET /api/jobs/{job_id}

Authenticated with COMMAND_API_TOKEN.

## Production setup

### 1. Supabase

Run cloud/schema.sql once in the Supabase SQL editor.

The database tables have RLS enabled and public roles are revoked. The Vercel backend uses a server-side Supabase secret key. Supabase recommends secret keys for backend-only access and says they must never be exposed to browsers or shipped clients.

### 2. Vercel

Set these environment variables:

- ENVIRONMENT=production
- AGENT_API_TOKEN
- COMMAND_API_TOKEN
- SUPABASE_URL
- SUPABASE_SECRET_KEY
- GEMINI_API_KEY
- GEMINI_MODEL=gemini-2.5-flash-lite

Then redeploy.

### 3. Windows agent

Copy:

~~~text
local_agent/config.example.json
~~~

to:

~~~text
local_agent/config.json
~~~

Use forward slashes in Windows JSON paths or escape every backslash.

Install:

~~~cmd
cd H:\Projects\Ai-agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r local_agent\requirements.txt
~~~

Start:

~~~cmd
cd local_agent
..\.venv\Scripts\python.exe agent.py
~~~

The agent only makes outbound HTTPS requests to Vercel. No inbound port is required.

## Printing model

The Windows agent:

1. validates the requested folder against configured allowed roots
2. discovers files recursively only when requested
3. sorts deterministically
4. analyzes PDFs with PyMuPDF
5. converts Word/Excel files to temporary PDFs through Microsoft Office
6. creates a per-job Windows printer DEVMODE
7. applies A4/Legal, orientation, simplex/duplex, and long/short-edge settings
8. renders PDF pages through the printer device context
9. waits for the Windows spooler job before moving to the next file
10. reports every file result to the cloud

Default policy:

| File | Paper | Duplex | Edge |
|---|---|---|---|
| PDF | A4 | Yes | Portrait = long, landscape = short |
| Excel | Legal | Yes | Short |
| Word | A4 | No | — |

Explicit command settings can override these defaults where the printer driver supports them.

### Important local requirements

- Windows 10/11
- Python 3.12
- pywin32
- PyMuPDF
- Pillow
- Microsoft Word/Excel for Office files
- a Windows-installed printer driver with duplex support for duplex printing

The printer driver remains authoritative. The agent requests the DEVMODE settings; unsupported driver options may be rejected by Windows.

## Security boundaries

- The cloud AI produces structured data only.
- The local agent does not execute AI-generated shell commands.
- Local paths are accepted only if they are inside configured allowed_roots.
- Agent and command API tokens are separate.
- Supabase secret keys stay only in Vercel.
- Job creation supports idempotency keys.
- Processing jobs have leases and can be requeued after an agent crash.
- The local queue stops on the first failed print so later files are not sent with uncertain printer state.

## Development

Run local tests:

~~~cmd
.\.venv\Scripts\python.exe -m pytest -q
~~~

The cloud service can be run locally with Uvicorn after installing cloud/requirements.txt and setting the environment variables.

## Production boundary

The repository now contains the production architecture and code path. Before calling a deployment production-live, the Supabase schema must be applied, Vercel environment variables must be configured, the printer driver must be tested with the target Brother HL-L2400D, and a real end-to-end print test must be completed.
