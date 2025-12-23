import re
import time
from datetime import date
from typing import List, Dict, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .base import (
    fetch_html, 
    parse_us_date_string,
    logger, 
    DATE_PATTERN
)

BASE_URL = "https://vtdigger.org"
MAX_ARTICLES = 60

def get_urls_for_date(target_date: date) -> List[str]:
    html = fetch_html(BASE_URL)
    soup = BeautifulSoup(html, "lxml")
    
    urls = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href: continue
        
        if href.startswith("/"):
            href = urljoin(BASE_URL, href)
        if not href.startswith(BASE_URL): continue

        # Regex URL check
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
        if not m: continue
        
        y, mth, d = map(int, m.groups())
        try:
            url_date = date(y, mth, d)
        except ValueError: continue
        
        if url_date != target_date: continue
        
        if href in seen: continue
        seen.add(href)
        urls.append(href)
        if len(urls) >= MAX_ARTICLES: break
    
    return urls

def scrape_article(url: str, fallback_date: date) -> Optional[Dict]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    # --- FILTER 1: Skip generic placeholder titles & Announcements ---
    clean_title = title.lower().strip()
    
    # Block specific exact titles
    if clean_title in ["vtdigger", "vtdiggers"]:
        logger.info(f"[VTDigger] Skipping placeholder title: {title}")
        return None

    # Block titles containing promotional phrases
    if "vtdigger announces" in clean_title or "giving tuesday" in clean_title:
        logger.info(f"[VTDigger] Skipping promotional/fundraising title: {title}")
        return None

    # Date Logic
    pub_date = None
    # Try URL first
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        try:
            pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: pass
    
    # Try Text Match
    if not pub_date:
        text = soup.get_text(" ", strip=True)
        match = DATE_PATTERN.search(text)
        if match:
            pub_date = parse_us_date_string(match.group(0))

    if not pub_date:
        pub_date = fallback_date

    paragraphs = []
    
    # Phrases that indicate we have hit the bottom garbage (Stop reading)
    hard_stop_phrases = [
        "have something to say? submit a commentary here",
        "vermont's newsletter",
        "request a correction",
    ]
    
    # Phrases to skip if found (Start of article headers)
    skip_exact_phrases = [
        "vtdigger",
        "news in pursuit of truth"
    ]

    first_paragraph_checked = False

    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t: continue
        
        lowered = t.lower()

        # --- FILTER 2: Commentary/Opinion & Obituary Check (First Paragraph) ---
        if not first_paragraph_checked:
            if "commentaries are opinion pieces contributed by readers and newsmakers" in lowered:
                logger.info(f"[VTDigger] Skipping Commentary/Opinion piece: {title}")
                return None
            
            # Block Obituaries starting with "Born"
            if t.startswith("Born"):
                logger.info(f"[VTDigger] Skipping Obituary: {title}")
                return None
                
            first_paragraph_checked = True

        # --- FILTER 3: Block "Young Writers Project" & "Giving Tuesday" content ---
        if "young writers project" in lowered or "giving tuesday" in lowered:
            logger.info(f"[VTDigger] Skipping blocked content type: {title}")
            return None
        
        # Check hard stops (End of article)
        if any(phrase in lowered for phrase in hard_stop_phrases):
            break

        # Skip specific branding lines (Start of article)
        if lowered in skip_exact_phrases:
            continue

        if "reader donations" in lowered: continue
        
        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs
    }

def scrape(target_date: date) -> List[Dict]:
    logger.info(f"[VTDigger] Fetching URLs for {target_date}")
    urls = get_urls_for_date(target_date)
    logger.info(f"[VTDigger] Found {len(urls)} matching URLs")

    articles = []
    total = len(urls)
    
    for i, u in enumerate(urls, start=1):
        logger.info(f"[VTDigger] Scraping {i}/{total}: {u}")
        try:
            art = scrape_article(u, fallback_date=target_date)
            if art: articles.append(art)
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"[VTDigger] Failed to scrape {u}: {e}")
            
    return articles