# AI Print Agent

A cloud-assisted AI print assistant with a secure Windows local agent.

## Architecture

- **Web/API (Vercel-ready):** receives natural-language print requests and converts them into validated print jobs.
- **Local Windows Agent:** runs on the user's PC, reads permitted local files, analyzes documents, queues print jobs, and controls the Windows printer.
- **Printer:** any Windows-installed printer; designed to work with the Brother HL-L2400D.
- **Repository:** GitHub stores the source code.

## Repository layout

```
Ai-agent/
├── cloud/
│   ├── app/
│   │   └── main.py
│   ├── requirements.txt
│   └── vercel.json
├── local_agent/
│   ├── agent.py
│   ├── config.example.json
│   ├── requirements.txt
│   ├── print_rules.json
│   └── services/
│       ├── file_manager.py
│       ├── document_analyzer.py
│       ├── printer.py
│       ├── queue_manager.py
│       └── transport.py
├── tests/
│   └── test_local_agent.py
└── .gitignore
```

## Current MVP

The first implementation intentionally keeps the local agent deterministic:

1. Discover files in an allowed folder.
2. Filter files by extension and exclusion patterns.
3. Inspect PDF metadata where available.
4. Build a sequential print queue.
5. Print one file at a time through Windows.
6. Report status back through the transport abstraction.

The cloud side exposes a small job API. The transport is deliberately abstract so we can start with a local/mock flow and later connect it to a deployed Vercel service using authenticated polling or realtime messaging.

## Safety model

The cloud side never gets arbitrary shell access to Windows. The local agent only accepts structured operations such as file discovery, print-job creation, status checks, pause, resume, and cancel.

## Important

Do not put printer credentials, API keys, Windows credentials, or personal folder paths into Git. Copy `config.example.json` to a local config file and keep the local config out of source control.
