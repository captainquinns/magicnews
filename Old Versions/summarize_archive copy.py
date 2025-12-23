#!/usr/bin/env python3
import logging
import os
import sys
import requests # <--- Switched to robust library
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, List, Tuple

# ====== CONFIG DEFAULTS ======
DEFAULT_ARCHIVE_ROOT = Path("Stories")
ARTICLE_EXTENSIONS = {".txt"}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ====== DATA MODELS ======
@dataclass
class ArticleMetadata:
    site_id: str
    date_str: str
    article_path: str
    title: Optional[str]
    url: Optional[str]
    published_date: Optional[str]
    site_name_in_file: Optional[str]

# ====== FILE DISCOVERY ======
def discover_article_files(root: Path) -> List[Path]:
    if not root.exists():
        logging.error(f"Archive root does not exist: {root}")
        return []

    files: List[Path] = []
    for ext in ARTICLE_EXTENSIONS:
        files.extend(root.rglob(f"*{ext}"))

    return sorted([f for f in files if f.is_file() and "Rewritten" not in f.parts])

def parse_site_and_date_from_path(root: Path, file_path: Path) -> Tuple[Optional[str], Optional[str]]:
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return None, None

    parts = rel.parts
    if len(parts) < 2:
        return None, None

    try:
        _ = date.fromisoformat(parts[0])
        return parts[1], parts[0] # site, date
    except ValueError:
        pass
    return None, None

# ====== ARTICLE PARSING ======
def parse_article_file(path: Path) -> Tuple[ArticleMetadata, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logging.error(f"Failed to read {path}: {e}")
        raise

    lines = text.splitlines()
    title: Optional[str] = None
    url: Optional[str] = None
    published_date: Optional[str] = None
    site_name: Optional[str] = None
    body_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped: continue

        if title is None and not ":" in stripped:
            title = stripped
            continue

        lower = stripped.lower()
        if lower.startswith("site:"):
            site_name = stripped.split(":", 1)[-1].strip()
            continue
        if lower.startswith("published:"):
            published_date = stripped.split(":", 1)[-1].strip()
            continue
        if lower.startswith("url:"):
            url = stripped.split(":", 1)[-1].strip()
            continue

        body_lines.append(line)

    return ArticleMetadata("", "", "", title, url, published_date, site_name), "\n".join(body_lines).strip()

# ====== AI CALL (ROBUST VERSION) ======
def _call_openai(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Uses 'requests' directly to bypass Mac SSL/httpx issues.
    Also strips the API key to fix the 'newline' error.
    """
    # 1. Get and Clean the Key (The Magic Fix)
    raw_key = os.environ.get("OPENAI_API_KEY", "")
    api_key = raw_key.strip() # <--- Removes the \n that was breaking everything
    
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an experienced news editor who rewrites stories in clear, original language without copying phrasing."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1500
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30 
        )
        resp.raise_for_status() # Raise error if 4xx or 5xx
        return resp.json()['choices'][0]['message']['content'].strip()
        
    except Exception as e:
        # If it fails, log the specific error response if possible
        if 'resp' in locals():
            logging.error(f"OpenAI Error Body: {resp.text}")
        raise e

def rewrite_with_ai(article_text: str, title: Optional[str] = None) -> Tuple[str, str]:
    model_name = "gpt-4o-mini"
    prompt = f"""
You are rewriting a local news article so that it is textually distinct from the original.

Your job:
- Rewrite the article COMPLETELY in your own words.
- Do NOT copy any full sentences or distinctive phrases from the original.
- Do NOT use quotation marks at all. No direct quotes.
- Do NOT paraphrase sentences or closely mirror phrasing.
- Any speech should be converted into indirect speech.
- You MAY keep proper nouns, names, places, dates, and numbers.
- Do NOT follow the same paragraph order, story flow, or emphasis as the source.
- Shuffle the sections so the flow is unique.
- Swap the position of supporting details.
- You must NOT change names, dates, numbers, or locations. These must remain identical to the source.
- At the end of the article, include tags for SEO to use in publication (important keywords, people, places).
- Output format: Headline, blank line, body text, article tags. No extra commentary.

Original Title: {title or "N/A"}
Original Text:
\"\"\"{article_text[:12000]}\"\"\"
""".strip()

    rewritten = _call_openai(prompt=prompt, model=model_name).strip()
    
    # Post-process cleanup
    for ch in ['"', "“", "”", "‘", "’"]:
        rewritten = rewritten.replace(ch, "")

    return rewritten, model_name

# ====== OUTPUT PATH LOGIC ======
def rewritten_txt_path(article_path: Path) -> Path:
    parts = list(article_path.parts)
    if "Original" in parts:
        idx = parts.index("Original")
        parts[idx] = "Rewritten"
        return Path(*parts)
    return article_path.with_suffix(".rewritten.txt")