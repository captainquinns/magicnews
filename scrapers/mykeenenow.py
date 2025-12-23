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

BASE_URL = "https://mykeenenow.com"
NEWS_URL = f"{BASE_URL}/news/"
MAX_ARTICLES = 60

def get_urls_for_date(target_date: date) -> List[str]:
    """
    Fetch all recent URLs and check them one-by-one for the date.
    This is less efficient but necessary as the URL has no date info.
    """
    html = fetch_html(NEWS_URL)
    soup = BeautifulSoup(html, "lxml")

    candidates = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href: continue
        if href.startswith("/"):
            href = urljoin(BASE_URL, href)
        
        if not href.startswith(BASE_URL): continue
        if "/news/" not in href: continue
        
        if href in seen: continue
        seen.add(href)
        candidates.append(href)

    valid_urls = []
    total = len(candidates)
    
    for i, u in enumerate(candidates, start=1):
        if len(valid_urls) >= MAX_ARTICLES: break
        
        # Log progress because this part is slow
        logger.info(f"[MyKeeneNow] Date check {i}/{total}: {u}")
        
        try:
            art_html = fetch_html(u)
            art_soup = BeautifulSoup(art_html, "lxml")
            text = art_soup.get_text(" ", strip=True)
            
            match = DATE_PATTERN.search(text)
            if match:
                d = parse_us_date_string(match.group(0))
                if d == target_date:
                    valid_urls.append(u)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"[MyKeeneNow] Failed to check date for {u}: {e}")
            
    return valid_urls

def scrape_article(url: str, fallback_date: date) -> Optional[Dict]:
    # Note: We likely already fetched this in get_urls_for_date, 
    # but for simplicity/cleanliness we fetch again or we could cache.
    # Given the request volume, fetching again is acceptable for now.
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    text = soup.get_text(" ", strip=True)
    pub_date = None
    match = DATE_PATTERN.search(text)
    if match:
        pub_date = parse_us_date_string(match.group(0))
    
    if not pub_date:
        pub_date = fallback_date

    paragraphs = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t: continue
        if "story ©" in t.lower() and "saga communications" in t.lower(): continue
        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs
    }

def scrape(target_date: date) -> List[Dict]:
    logger.info(f"[MyKeeneNow] Fetching URLs for {target_date} (Slow Scan)")
    urls = get_urls_for_date(target_date)
    logger.info(f"[MyKeeneNow] Found {len(urls)} matching URLs")

    articles = []
    total = len(urls)
    
    for i, u in enumerate(urls, start=1):
        logger.info(f"[MyKeeneNow] Scraping {i}/{total}: {u}")
        try:
            art = scrape_article(u, fallback_date=target_date)
            if art: articles.append(art)
        except Exception as e:
            logger.error(f"[MyKeeneNow] Failed to scrape {u}: {e}")
            
    return articles