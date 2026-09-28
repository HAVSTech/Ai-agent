from __future__ import annotations

import json
import re

import httpx

from .config import Settings
from .models import PrintIntent


PRINT_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "folder": {"type": ["string", "null"]},
        "extensions": {"type": "array", "items": {"type": "string", "enum": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".xlsm", ".csv", ".txt", ".png", ".jpg", ".jpeg"]}},
        "exclude_contains": {"type": "array", "items": {"type": "string"}},
        "recursive": {"type": "boolean"},
        "sort_order": {"type": "string", "enum": ["name", "modified", "created"]},
        "paper": {"type": "string", "enum": ["auto", "A4", "Legal"]},
        "duplex": {"type": ["boolean", "null"]},
        "edge": {"type": "string", "enum": ["auto", "long", "short"]},
        "copies": {"type": "integer", "minimum": 1, "maximum": 20},
        "clarification_needed": {"type": "boolean"},
        "clarification": {"type": ["string", "null"]},
    },
    "required": ["folder", "extensions", "exclude_contains", "recursive", "sort_order", "paper", "duplex", "edge", "copies", "clarification_needed", "clarification"],
}


SYSTEM_PROMPT = """You are the planning component of a secure local print agent.
Convert the user's natural-language print request into ONLY the supplied JSON schema.

Rules:
- You may choose files and print settings, but you may NOT execute commands, access files, upload files, delete files, or invent local filesystem contents.
- A Windows folder path may be supplied by the user. Preserve it exactly.
- If the folder is not stated, return folder=null and clarification_needed=true unless folder_hint supplies it.
- Default file selection is PDF only unless the user clearly asks for other formats or all supported files.
- "double sided", "duplex", "front and back" means duplex=true.
- "single sided" means duplex=false.
- Long-edge is normally used for portrait duplex; short-edge for landscape duplex.
- Legal paper should be selected only when explicitly requested or when the file type is Excel and the local policy says Excel uses Legal.
- Never create shell commands or executable instructions.
- If a request is ambiguous or unsafe, ask for clarification rather than guessing.
"""


class PrintPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _heuristic(self, command: str, folder_hint: str | None) -> PrintIntent:
        text = command.lower()
        folder = folder_hint
        if not folder:
            match = re.search(r'([a-z]:[\\/][^\n,;]+)', command, re.IGNORECASE)
            if match:
                folder = match.group(1).strip().strip('"')
        exts = [".pdf"]
        if "word" in text or ".docx" in text:
            exts = [".docx", ".doc"]
        elif "excel" in text or "spreadsheet" in text or ".xlsx" in text:
            exts = [".xlsx", ".xls", ".xlsm"]
        elif "all files" in text:
            exts = [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".xlsm"]
        duplex = True if any(x in text for x in ("duplex", "double sided", "front and back", "both sides")) else None
        if "single sided" in text or "one sided" in text:
            duplex = False
        paper = "Legal" if "legal" in text else "auto"
        edge = "short" if "short edge" in text else ("long" if "long edge" in text else "auto")
        copies = 1
        match = re.search(r'\b(\d+)\s+copies?\b', text)
        if match:
            copies = min(20, max(1, int(match.group(1))))
        return PrintIntent(
            folder=folder,
            extensions=exts,
            duplex=duplex,
            paper=paper,
            edge=edge,
            copies=copies,
            clarification_needed=not bool(folder),
            clarification=None if folder else "Which folder should I print from?",
        )

    def plan(self, command: str, folder_hint: str | None = None) -> PrintIntent:
        if not self.settings.ai_configured:
            return self._heuristic(command, folder_hint)

        prompt = SYSTEM_PROMPT + "\nUser command:\n" + command
        if folder_hint:
            prompt += "\nFolder hint (use this when the command does not specify another folder):\n" + folder_hint

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": PRINT_INTENT_SCHEMA,
                "temperature": 0.1,
            },
        }
        response = httpx.post(
            url,
            headers={"x-goog-api-key": self.settings.gemini_api_key},
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        return PrintIntent.model_validate(json.loads(text))
