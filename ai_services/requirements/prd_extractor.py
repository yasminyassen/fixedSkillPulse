import os
import json
import logging
import inspect
from pathlib import Path
import pandas as pd
import pdfplumber
from openai import AsyncOpenAI
from json_repair import repair_json

log = logging.getLogger(__name__)

def _read_pdf(file_path: Path) -> str:
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    return text

def _read_excel(file_path: Path) -> str:
    df = pd.read_excel(file_path)
    return df.to_string(index=False)

def _read_markdown(file_path: Path) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def extract_raw_text(file_path: str) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext == ".pdf":
        return _read_pdf(path)
    elif ext in [".xlsx", ".xls", ".csv"]:
        if ext == ".csv":
            return pd.read_csv(path).to_string(index=False)
        return _read_excel(path)
    elif ext in [".md", ".txt"]:
        return _read_markdown(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

def _get_llm_client():
    mode = os.getenv("AI_MODE", "openrouter")
    if mode == "openrouter":
        return (
            AsyncOpenAI(
                base_url=os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1"),
                api_key=os.getenv("OPENROUTER_API_KEY"),
            ),
            os.getenv("OPENROUTER_MODEL", "qwen/qwen3-14b"),
        )
    return (
        AsyncOpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
        ),
        os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
    )

_EXTRACTION_PROMPT = """
You are a Senior Software Architect and Agile Engineering Lead.

Your job is to convert a PRD into:
1. Well-sized user stories
2. Realistic technical tasks that managers can assign to developers

========================================================
IMPORTANT RULES
========================================================

Acceptance Criteria are NOT technical tasks.
Acceptance criteria describe:
- what the system should do

Technical tasks describe:
- what engineers must build

Do NOT rewrite acceptance criteria as tasks.

--------------------------------------------------------

Tasks must:
- represent meaningful engineering work
- be independently assignable
- usually cover MULTIPLE acceptance criteria together
========================================================
TASK TYPES : backend, frontend, qa
========================================================
USER STORY RULES
========================================================

Each story must:
- represent ONE business goal
- not be too tiny
- not combine unrelated features
Use format:
"As a <role>, I want <feature>, so that <benefit>."
========================================================
OUTPUT RULES
========================================================

Return ONLY valid JSON.
No markdown.
No explanations.

========================================================
OUTPUT FORMAT
========================================================

Each object MUST have these exact keys:

- "story_code": string — US-001, US-002, etc.
- "title": string — short headline of the user goal
- "role": string — the user persona
- "feature": string — what the user wants to do
- "benefit": string — why they want it
- "description": string — "As a <role>, I want <feature>, so that <benefit>."
- "priority": string — exactly one of:
  "critical", "high", "medium", "low"
- "estimated_days": integer
- "tags": list of strings

- "acceptance_criteria": list of objects, each with:
    - "id": integer starting from 0
    - "text": string

- "technical_tasks": list of objects, each with:
    - "description": string
    - "type": string — exactly:
      "backend", "frontend", or "qa"
    - "ac_ids": list of integers

========================================================
RAW PRD TEXT
========================================================

{raw_text}
"""
async def parse_prd_to_stories(file_path: str) -> list[dict]:
    try:
        raw_text = extract_raw_text(file_path)
    except Exception as e:
        raise

    if not raw_text.strip():
        raise ValueError("The extracted text from the file is empty.")

    client, model = _get_llm_client()
    prompt = _EXTRACTION_PROMPT.format(raw_text=raw_text)
    
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=4000,
        )
        
        raw_json_response = response.choices[0].message.content
        parsed_data = json.loads(repair_json(raw_json_response))
        
        if not isinstance(parsed_data, list):
            if "user_stories" in parsed_data:
                parsed_data = parsed_data["user_stories"]
            else:
                parsed_data = [parsed_data]
                
        return parsed_data
        
    except Exception as e:
        raise
    finally:
        close_result = client.close()
        if inspect.isawaitable(close_result):
            await close_result
