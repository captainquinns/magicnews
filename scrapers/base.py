import re
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional
from requests import RequestException

# ==========================
# Global Config
# ==========================

# Root for all scraped content
ROOT_DIR = Path("Stories")

# Common User-Agent to avoid blocking
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    )
}

# Generic Date Matcher (Month DD, YYYY)
DATE_PATTERN = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b"
)

# Logger setup
logger = logging.getLogger("Scraper")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)


# ==========================
# Helpers
# ==========================

def fetch_html(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return its HTML text with error handling."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        # Re-raise so the specific scraper decides how to handle the failure
        raise

def parse_us_date_string(date_str: str) -> Optional[date]:
    """Try to parse dates like 'Nov 29, 2025' or 'November 29, 2025'."""
    fixed = date_str.replace("Sept ", "Sep ").replace("SEPT ", "Sep ")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(fixed, fmt).date()
        except ValueError:
            continue
    return None

def title_to_filename(title: str) -> str:
    """Turn an article title into a filesystem-safe .txt filename."""
    if not title:
        return "untitled.txt"
    
    # Strip illegal characters
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    if not cleaned:
        cleaned = "untitled"
        
    # Cap length
    if len(cleaned) > 150:
        cleaned = cleaned[:150].rstrip()
        
    return f"{cleaned}.txt"

def write_text_article(article: Dict, path: Path, site_slug: str) -> None:
    """Write a single article out as a plain-text .txt file."""
    title = article.get("title") or "Untitled"
    url = article.get("url") or ""
    pub_date = article.get("date")
    paragraphs = article.get("paragraphs") or []

    lines = [
        title,
        "",
        f"Site: {site_slug.upper()}",
    ]
    if isinstance(pub_date, date):
        lines.append(f"Published: {pub_date.isoformat()}")
    
    lines.append(f"URL: {url}")
    lines.append("")

    for p in paragraphs:
        p = p.strip()
        if p:
            lines.append(p)
            lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")

def ensure_output_dir(target_date: date, site_slug: str) -> Path:
    """Ensure Stories/<YYYY-MM-DD>/<site>/Original exists."""
    out_dir = ROOT_DIR / target_date.isoformat() / site_slug / "Original"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

def save_articles(site_slug: str, target_date: date, articles: List[Dict]) -> None:
    """Standardized saving routine for all scrapers."""
    valid_articles = [a for a in articles if a]
    
    if not valid_articles:
        logger.info(f"[{site_slug}] No articles to save for {target_date}")
        return

    out_dir = ensure_output_dir(target_date, site_slug)

    # Save URL list
    urls = sorted({a.get("url") for a in valid_articles if a.get("url")})
    url_list_path = out_dir / f"{site_slug}_urls_{target_date.isoformat()}.json"
    url_list_path.write_text(json.dumps(urls, indent=2), encoding="utf-8")
    logger.info(f"[{site_slug}] Saved URL list -> {url_list_path}")

    # Save articles
    for article in valid_articles:
        title = article.get("title") or "Untitled"
        filename = title_to_filename(title)
        candidate = out_dir / filename

        # Handle duplicates
        if candidate.exists():
            base = candidate.stem
            ext = candidate.suffix
            i = 2
            while candidate.exists():
                candidate = out_dir / f"{base} ({i}){ext}"
                i += 1
        
        write_text_article(article, candidate, site_slug)
        logger.info(f"[{site_slug}] -> Saved: {candidate.name}")