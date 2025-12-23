import re
import time
from datetime import date
from typing import List, Dict, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .base import (
    fetch_html, 
    logger, 
)

BASE_URL = "https://www.wcax.com"
NEWS_URL = f"{BASE_URL}/news/"
MAX_ARTICLES = 60

# Expanded category list to prevent valid local stories from being skipped
LOCAL_CATEGORIES = [
    "vermont", "new hampshire", "local", "vt", "nh", 
    "news", "crime", "education", "health", "politics", "business"
]

EXCLUDE_TITLES = ["programming note", "this day in history", "history"]

def get_urls_for_date(target_date: date) -> List[str]:
    """Find recent URLs that match the /YYYY/MM/DD/ pattern in the link."""
    html = fetch_html(NEWS_URL)
    soup = BeautifulSoup(html, "lxml")

    urls = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href: continue
        
        if href.startswith("/"):
            href = urljoin(BASE_URL, href)
            
        if not href.startswith(BASE_URL): continue

        # Check URL structure for date
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

def extract_category(soup: BeautifulSoup) -> str:
    """Extract category metadata."""
    meta = soup.find("meta", attrs={"property": "article:section"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    
    # Fallback
    cat_link = soup.find("a", class_=re.compile("category", re.I))
    if cat_link: return cat_link.get_text(strip=True)
    
    return ""

def scrape_article(url: str, fallback_date: date) -> Optional[Dict]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    
    if any(bad in title.lower() for bad in EXCLUDE_TITLES):
        logger.info(f"[WCAX] Skipping garbage title: {title}")
        return None

    category = extract_category(soup).lower()
    
    # Debug log to help identify why things are skipped
    if category and not any(loc in category for loc in LOCAL_CATEGORIES):
        logger.info(f"[WCAX] SKIPPING URL: {url}")
        logger.info(f"[WCAX]    -> Reason: Category '{category}' is not in allow list.")
        return None

    # Parse date from URL if possible
    pub_date = fallback_date
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        try:
            pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError: pass

    paragraphs = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t: continue
        if "copyright" in t.lower() and "wcax" in t.lower(): continue
        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs
    }

def scrape(target_date: date) -> List[Dict]:
    logger.info(f"[WCAX] Fetching URLs for {target_date}")
    urls = get_urls_for_date(target_date)
    logger.info(f"[WCAX] Found {len(urls)} matching URLs")

    articles = []
    total = len(urls)
    
    for i, u in enumerate(urls, start=1):
        logger.info(f"[WCAX] Scraping {i}/{total}: {u}")
        try:
            art = scrape_article(u, fallback_date=target_date)
            if art: articles.append(art)
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"[WCAX] Failed to scrape {u}: {e}")
            
    return articles