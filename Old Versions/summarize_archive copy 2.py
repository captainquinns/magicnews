#!/usr/bin/env python3
import logging
import os
import sys
import requests
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, List, Tuple

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

@dataclass
class ArticleMetadata:
    site_id: str
    date_str: str
    article_path: str
    title: Optional[str]
    url: Optional[str]
    published_date: Optional[str]
    site_name_in_file: Optional[str]

def parse_article_file(path: Path) -> Tuple[ArticleMetadata, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logging.error(f"Failed to read {path}: {e}")
        raise

    lines = text.splitlines()
    title, url, pub_date, site_name = None, None, None, None
    body_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped: continue
        if title is None and not ":" in stripped:
            title = stripped
            continue
        lower = stripped.lower()
        if lower.startswith("site:"): site_name = stripped.split(":", 1)[-1].strip()
        elif lower.startswith("published:"): pub_date = stripped.split(":", 1)[-1].strip()
        elif lower.startswith("url:"): url = stripped.split(":", 1)[-1].strip()
        else: body_lines.append(line)

    return ArticleMetadata("", "", "", title, url, pub_date, site_name), "\n".join(body_lines).strip()

def _call_openai(prompt: str, model: str = "gpt-4o-mini") -> str:
    raw_key = os.environ.get("OPENAI_API_KEY", "")
    api_key = raw_key.strip()
    if not api_key: raise RuntimeError("OPENAI_API_KEY is missing.")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a senior news editor. You rewrite and synthesize reports into clear, factual, and textually distinct journalistic articles."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000
    }
    resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=45)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content'].strip()

def rewrite_with_ai(article_text: str, title: Optional[str] = None) -> Tuple[str, str]:
    """Standard single-article rewrite with specific distinctness requirements."""
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

Original Title: {title}
Original Text: {article_text[:10000]}
""".strip()

    rewritten = _call_openai(prompt)
    for ch in ['"', "“", "”"]: rewritten = rewritten.replace(ch, "")
    return rewritten, "gpt-4o-mini"

def merge_with_ai(articles: List[dict]) -> str:
    """Synthesizes multiple reports into one definitive, textually distinct article."""
    sources_text = ""
    for i, a in enumerate(articles, 1):
        sources_text += f"SOURCE {i} ({a['site']}):\nTitle: {a['title']}\nText: {a['text']}\n\n"

    prompt = f"""
You are an expert news editor synthesizing multiple reports regarding the SAME event/topic into ONE definitive journalistic news article.

Your job:
1. FACT-CHECK: Use details from all sources. If sources disagree on a fact (e.g. time or number of people), mention that "reports vary" or use the most common detail.
2. TEXTUAL DISTINCTNESS:
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
3. FORMAT:
- At the end of the article, include tags for SEO to use in publication (important keywords, people, places).
- Output format: Headline, blank line, body text, article tags. No extra commentary.

REPORTS TO COMBINE:
{sources_text}
""".strip()

    merged = _call_openai(prompt)
    for ch in ['"', "“", "”"]: merged = merged.replace(ch, "")
    return merged

def rewritten_txt_path(article_path: Path) -> Path:
    parts = list(article_path.parts)
    if "Original" in parts:
        idx = parts.index("Original")
        parts[idx] = "Rewritten"
        return Path(*parts)
    return article_path.with_suffix(".rewritten.txt")