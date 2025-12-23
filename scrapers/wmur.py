import re
import time
from datetime import date
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from .base import (
    fetch_html, 
    parse_us_date_string, 
    logger, 
    DATE_PATTERN
)

# Constants specific to WMUR
BASE_URL = "https://www.wmur.com"
LOCAL_NEWS_URL = f"{BASE_URL}/local-news"
MAX_ARTICLES = 60

NON_NEWS_KEYWORDS = [
    "grow-it-green", "nh-chronicle", "forecast", "hour-by-hour",
]

def extract_title(soup: BeautifulSoup) -> str:
    """Robust title extraction for WMUR."""
    # 1. Open Graph
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    else:
        # 2. Twitter card
        tw = soup.find("meta", attrs={"name": "twitter:title"})
        if tw and tw.get("content"):
            title = tw["content"].strip()
        else:
            # 3. H1 fallback
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Untitled"

    # Remove site suffix (e.g. " - WMUR New Hampshire")
    title = re.sub(r"\s*[-|]\s*WMUR.*$", "", title, flags=re.IGNORECASE).strip()
    return title

def get_candidate_urls() -> List[str]:
    """Fetch Local News page and return article URLs."""
    html = fetch_html(LOCAL_NEWS_URL)
    soup = BeautifulSoup(html, "lxml")

    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2") and "local news" in tag.get_text(strip=True).lower()
    )

    if heading:
        anchors = heading.find_all_next("a", href=True)
    else:
        anchors = soup.find_all("a", href=True)

    urls = []
    seen = set()

    for a in anchors:
        href = a["href"]
        if not href: continue
        
        if href.startswith("/"):
            href = BASE_URL + href
            
        if not href.startswith(BASE_URL): continue
        if "/article/" not in href: continue
        
        lowered = href.lower()
        if any(bad in lowered for bad in NON_NEWS_KEYWORDS): continue
        
        if href in seen: continue
        
        seen.add(href)
        urls.append(href)
        if len(urls) >= MAX_ARTICLES: break
        
    return urls

def scrape_article(url: str, fallback_date: date) -> Optional[Dict]:
    """Fetch and parse a single WMUR article."""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title = extract_title(soup)
    
    # NEW: Filter out specific promotional/internal titles
    # This catches "Help WMUR recognize...", "Hearst Television News...", etc.
    title_lower = title.lower()
    if "wmur" in title_lower or "hearst television news" in title_lower:
        logger.info(f"[WMUR] Skipping promotional title: {title}")
        return None

    text = soup.get_text(" ", strip=True)
    
    # Date extraction
    pub_date = None
    match = DATE_PATTERN.search(text)
    if match:
        pub_date = parse_us_date_string(match.group(0))
    
    if not pub_date:
        pub_date = fallback_date

    # Body extraction
    paragraphs = []
    hard_stop_phrases = [
        "subscribe to wmur's youtube channel",
        "hearst television participates",
    ]
    skip_phrases = ["download the free wmur app", "get the wmur app", "copyright"]

    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t: continue
        lower = t.lower()

        if any(stop in lower for stop in hard_stop_phrases): break
        if any(skip in lower for skip in skip_phrases) and "wmur" in lower: continue

        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs
    }

def scrape(target_date: date) -> List[Dict]:
    """Main entry point for WMUR scraper."""
    logger.info(f"[WMUR] Fetching candidate URLs from {LOCAL_NEWS_URL}")
    candidates = get_candidate_urls()
    logger.info(f"[WMUR] Found {len(candidates)} candidates")

    valid_articles = []
    total = len(candidates)
    
    for i, url in enumerate(candidates, start=1):
        logger.info(f"[WMUR] Checking {i}/{total}: {url}")
        try:
            art = scrape_article(url, fallback_date=target_date)
            if art and art['date'] == target_date:
                valid_articles.append(art)
            time.sleep(0.3) # Be polite
        except Exception as e:
            logger.error(f"[WMUR] Failed to scrape {url}: {e}")

    return valid_articles