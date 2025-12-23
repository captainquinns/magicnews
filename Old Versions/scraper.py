import argparse
import json
import re
import time
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Callable
from urllib.parse import urljoin

import requests
from requests import RequestException
from bs4 import BeautifulSoup

# ==========================
# Global config
# ==========================

# Root for all scraped content:
# Stories/<YYYY-MM-DD>/<site>/Original
ROOT_DIR = Path("Stories")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    )
}

# Hard cap on how many articles we’ll process per site per run
MAX_ARTICLES_PER_SITE = 60  # bump to 25 if you really want more

# Generic "Month DD, YYYY" pattern with short or long month names
DATE_PATTERN = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b"
)

# WMUR
WMUR_BASE = "https://www.wmur.com"
WMUR_LOCAL_NEWS_URL = f"{WMUR_BASE}/local-news"
WMUR_NON_NEWS_KEYWORDS = [
    "grow-it-green",
    "nh-chronicle",
    "forecast",
    "hour-by-hour",
]

# VTDigger
VTDIGGER_BASE = "https://vtdigger.org"

# WCAX
WCAX_BASE = "https://www.wcax.com"
WCAX_NEWS_URL = f"{WCAX_BASE}/news/"

WCAX_LOCAL_CATEGORIES = [
    "vermont",
    "new hampshire",
    "local",
    "vt",
    "nh",
]

WCAX_EXCLUDE_TITLES = [
    "programming note",
    "this day in history",
    "history",
]

# My Keene Now
MYK_BASE = "https://mykeenenow.com"
MYK_NEWS_URL = f"{MYK_BASE}/news/"


# ==========================
# Common helpers
# ==========================

def fetch(url: str) -> str:
    """Fetch a URL and return its HTML text, with sane timeout/error handling."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.text
    except RequestException as e:
        raise RuntimeError(f"Request failed for {url}: {e}")


def parse_us_date_string(date_str: str) -> Optional[date]:
    """Try to parse dates like 'Nov 29, 2025' or 'November 29, 2025'."""
    fixed = date_str.replace("Sept ", "Sep ")
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(fixed, fmt).date()
        except ValueError:
            continue
    return None


def title_to_filename(title: str) -> str:
    """
    Turn an article title into a filesystem-safe .txt filename,
    staying as human-readable as possible.
    """
    if not title:
        return "untitled.txt"

    # Strip illegal path characters
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        cleaned = "untitled"

    # Cap length to avoid filesystem issues
    if len(cleaned) > 150:
        cleaned = cleaned[:150].rstrip()

    return f"{cleaned}.txt"


def write_text_article(article: Dict, path: Path, site_slug: str) -> None:
    """Write a single article out as a plain-text .txt file."""
    title = article.get("title") or "Untitled"
    url = article.get("url") or ""
    pub_date = article.get("date")
    paragraphs = article.get("paragraphs") or []

    lines: List[str] = []
    lines.append(title)
    lines.append("")
    lines.append(f"Site: {site_slug.upper()}")
    if isinstance(pub_date, date):
        lines.append(f"Published: {pub_date.isoformat()}")
    lines.append(f"URL: {url}")
    lines.append("")

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        lines.append(p)
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


def ensure_output_dir(target_date: date, site_slug: str) -> Path:
    """
    Ensure Stories/<YYYY-MM-DD>/<site>/Original exists and return it.
    """
    out_dir = ROOT_DIR / target_date.isoformat() / site_slug / "Original"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def save_articles_for_site(
    site_slug: str,
    target_date: date,
    articles: List[Dict],
) -> None:
    """
    Save a JSON list of URLs and one .txt file per article
    into Stories/<date>/<site>/Original
    """
    # Filter out any None placeholders just in case
    articles = [a for a in articles if a]

    if not articles:
        print(f"[{site_slug}] No articles to save for {target_date.isoformat()}")
        return

    out_dir = ensure_output_dir(target_date, site_slug)

    urls = sorted({a.get("url") for a in articles if a.get("url")})
    url_list_path = out_dir / f"{site_slug}_urls_{target_date.isoformat()}.json"
    url_list_path.write_text(json.dumps(urls, indent=2), encoding="utf-8")
    print(f"[{site_slug}] Saved URL list -> {url_list_path}")

    for article in articles:
        title = article.get("title") or "Untitled"
        filename = title_to_filename(title)
        candidate = out_dir / filename

        # Avoid collisions when titles repeat
        if candidate.exists():
            base = candidate.stem
            ext = candidate.suffix
            i = 2
            while candidate.exists():
                candidate = out_dir / f"{base} ({i}){ext}"
                i += 1

        write_text_article(article, candidate, site_slug)
        print(f"[{site_slug}] -> Saved article: {candidate}")


# ==========================
# WMUR
# ==========================

def wmur_extract_title(soup: BeautifulSoup) -> str:
    """Robustly extract WMUR article title (avoid junk like 'Search location by ZIP code')."""
    # 1) Open Graph
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    else:
        # 2) Twitter card
        tw = soup.find("meta", attrs={"name": "twitter:title"})
        if tw and tw.get("content"):
            title = tw["content"].strip()
        else:
            # 3) <title> tag
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                title = title_tag.string.strip()
            else:
                # 4) Fallback: first h1
                h1 = soup.find("h1")
                title = h1.get_text(strip=True) if h1 else ""

    if title:
        title = re.sub(r"\s*[-|]\s*WMUR.*$", "", title, flags=re.IGNORECASE).strip()

    return title or "Untitled"


def wmur_get_recent_article_urls(max_articles: int = MAX_ARTICLES_PER_SITE) -> List[str]:
    """
    Fetch WMUR Local News page and extract up to `max_articles` candidate article URLs.
    """
    html = fetch(WMUR_LOCAL_NEWS_URL)
    soup = BeautifulSoup(html, "lxml")

    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2") and "local news" in tag.get_text(strip=True).lower()
    )

    if heading:
        anchors = heading.find_all_next("a", href=True)
    else:
        print("[wmur] WARNING: 'Local News' heading not found, scanning whole page.")
        anchors = soup.find_all("a", href=True)

    urls: List[str] = []
    seen = set()

    for a in anchors:
        href = a["href"]
        if not href:
            continue

        # Normalize relative URLs
        if href.startswith("/"):
            href = WMUR_BASE + href

        if not href.startswith(WMUR_BASE):
            continue
        if "/article/" not in href:
            continue

        lowered = href.lower()
        if any(bad in lowered for bad in WMUR_NON_NEWS_KEYWORDS):
            continue

        if href in seen:
            continue

        seen.add(href)
        urls.append(href)

        if len(urls) >= max_articles:
            break

    return urls


def wmur_get_article_date(url: str) -> Optional[date]:
    """
    Fetch a WMUR article and try to extract its date as a `datetime.date`.
    Returns None if it can't find/parse a date or fetch fails.
    """
    try:
        html = fetch(url)
    except RuntimeError as e:
        print(f"[wmur]   [WARN] Date fetch failed for {url}: {e}")
        return None

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    match = DATE_PATTERN.search(text)
    if not match:
        print(f"[wmur]   [WARN] No date found in article: {url}")
        return None

    d = parse_us_date_string(match.group(0))
    if not d:
        print(f"[wmur]   [WARN] Failed to parse date string '{match.group(0)}' in {url}")
    return d


def wmur_scrape_article(url: str, fallback_date: Optional[date]) -> Optional[Dict]:
    """
    Fetch a WMUR article and return structured data:
    {url, title, date, paragraphs, images}
    """
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    title = wmur_extract_title(soup)

    text = soup.get_text(" ", strip=True)
    pub_date: Optional[date] = None
    match = DATE_PATTERN.search(text)
    if match:
        pub_date = parse_us_date_string(match.group(0))
    if not pub_date:
        pub_date = fallback_date

    paragraphs: List[str] = []
    hard_stop_phrases = [
        "subscribe to wmur's youtube channel",
        "hearst television participates in various affiliate marketing programs",
    ]
    skip_phrases = [
        "download the free wmur app",
        "get the wmur app",
        "copyright",
    ]

    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t:
            continue
        lower = t.lower()

        if any(phrase in lower for phrase in hard_stop_phrases):
            break

        if any(phrase in lower for phrase in skip_phrases) and "wmur" in lower:
            continue

        paragraphs.append(t)

    images: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = WMUR_BASE + src
        if src not in images:
            images.append(src)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs,
        "images": images,
    }


def scrape_wmur_for_date(target_date: date) -> List[Dict]:
    print(f"[wmur] Fetching candidate URLs from {WMUR_LOCAL_NEWS_URL}")
    urls = wmur_get_recent_article_urls()
    print(f"[wmur] Found {len(urls)} candidate URLs (capped at {MAX_ARTICLES_PER_SITE})")

    todays_urls: List[str] = []

    for idx, u in enumerate(urls, start=1):
        print(f"[wmur] Date check {idx}/{len(urls)}: {u}")
        art_date = wmur_get_article_date(u)
        if art_date is None:
            continue
        if art_date == target_date:
            todays_urls.append(u)

    print(f"[wmur] URLs matching {target_date.isoformat()}: {len(todays_urls)}")
    for u in todays_urls:
        print(f"[wmur]   {u}")

    articles: List[Dict] = []
    for u in todays_urls[:MAX_ARTICLES_PER_SITE]:
        try:
            art = wmur_scrape_article(u, fallback_date=target_date)
            if art:
                articles.append(art)
        except Exception as e:
            print(f"[wmur]   [ERROR] Failed to scrape article {u}: {e}")
            continue
        time.sleep(0.5)

    return articles


# ==========================
# VTDigger
# ==========================

def vtdigger_get_urls_for_date(target_date: date) -> List[str]:
    """
    Grab article URLs from the VTDigger front page whose URL path
    contains /YYYY/MM/DD/ that matches the target date.
    """
    urls: List[str] = []
    seen = set()

    html = fetch(VTDIGGER_BASE)
    soup = BeautifulSoup(html, "lxml")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(VTDIGGER_BASE, href)

        if not href.startswith(VTDIGGER_BASE):
            continue

        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
        if not m:
            continue
        y, mth, d = map(int, m.groups())
        try:
            url_date = date(y, mth, d)
        except ValueError:
            continue
        if url_date != target_date:
            continue

        if href in seen:
            continue
        seen.add(href)
        urls.append(href)

    return urls[:MAX_ARTICLES_PER_SITE]


def vtdigger_scrape_article(url: str, fallback_date: Optional[date]) -> Optional[Dict]:
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    pub_date: Optional[date] = None
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        try:
            pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pub_date = None

    if not pub_date:
        text = soup.get_text(" ", strip=True)
        match = DATE_PATTERN.search(text)
        if match:
            pub_date = parse_us_date_string(match.group(0))
    if not pub_date:
        pub_date = fallback_date

    paragraphs: List[str] = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t:
            continue
        lowered = t.lower()
        if "vtdigger exists because of reader donations" in lowered:
            continue
        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs,
        "images": [],
    }


def scrape_vtdigger_for_date(target_date: date) -> List[Dict]:
    print(f"[vtdigger] Fetching URLs for {target_date.isoformat()}")
    urls = vtdigger_get_urls_for_date(target_date)
    print(f"[vtdigger] Found {len(urls)} URLs (capped at {MAX_ARTICLES_PER_SITE})")

    articles: List[Dict] = []
    for u in urls:
        try:
            art = vtdigger_scrape_article(u, fallback_date=target_date)
            if art:
                articles.append(art)
        except Exception as e:
            print(f"[vtdigger]   [ERROR] Failed to scrape {u}: {e}")
            continue
        time.sleep(0.5)

    return articles


# ==========================
# WCAX
# ==========================

def wcax_get_urls_for_date(target_date: date) -> List[str]:
    """
    Scrape WCAX News page and collect article links whose URL contains
    /YYYY/MM/DD/ for the given date.
    """
    html = fetch(WCAX_NEWS_URL)
    soup = BeautifulSoup(html, "lxml")

    urls: List[str] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(WCAX_BASE, href)

        if not href.startswith(WCAX_BASE):
            continue

        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
        if not m:
            continue

        y, mth, d = map(int, m.groups())
        try:
            url_date = date(y, mth, d)
        except ValueError:
            continue
        if url_date != target_date:
            continue

        if href in seen:
            continue
        seen.add(href)
        urls.append(href)

    return urls[:MAX_ARTICLES_PER_SITE]


def wcax_extract_category(soup: BeautifulSoup) -> str:
    """
    Try to extract a category/section label for WCAX articles.
    If none found, return empty string (we won't filter on empty).
    """
    # Common pattern: meta property="article:section"
    meta = soup.find("meta", attrs={"property": "article:section"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    # Fallbacks: look for obvious category tags
    cat_link = soup.find("a", class_=re.compile("category", re.I))
    if cat_link and cat_link.get_text(strip=True):
        return cat_link.get_text(strip=True)

    breadcrumb = soup.find("li", class_=re.compile("breadcrumb", re.I))
    if breadcrumb and breadcrumb.get_text(strip=True):
        return breadcrumb.get_text(strip=True)

    return ""


def wcax_scrape_article(url: str, fallback_date: Optional[date]) -> Optional[Dict]:
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    title_lower = title.lower()

    # Skip obvious garbage by title
    if any(bad in title_lower for bad in WCAX_EXCLUDE_TITLES):
        print(f"[wcax] Skipping garbage content by title: {title}")
        return None

    # Category-based filtering when we *can* detect a category
    category = wcax_extract_category(soup).lower()
    if category:
        if not any(loc in category for loc in WCAX_LOCAL_CATEGORIES):
            print(f"[wcax] Skipping non-local category '{category}' for: {title}")
            return None

    pub_date: Optional[date] = None
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        try:
            pub_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pub_date = None
    if not pub_date:
        pub_date = fallback_date

    paragraphs: List[str] = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t:
            continue
        lowered = t.lower()
        if "copyright" in lowered and "wcax" in lowered:
            continue
        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs,
        "images": [],
    }


def scrape_wcax_for_date(target_date: date) -> List[Dict]:
    print(f"[wcax] Fetching URLs for {target_date.isoformat()}")
    urls = wcax_get_urls_for_date(target_date)
    print(f"[wcax] Found {len(urls)} URLs (capped at {MAX_ARTICLES_PER_SITE})")

    articles: List[Dict] = []
    for u in urls:
        try:
            art = wcax_scrape_article(u, fallback_date=target_date)
            if art:
                articles.append(art)
        except Exception as e:
            print(f"[wcax]   [ERROR] Failed to scrape {u}: {e}")
            continue
        time.sleep(0.5)

    return articles


# ==========================
# My Keene Now
# ==========================

def myk_get_urls_for_date(target_date: date) -> List[str]:
    """
    Scrape MyKeeneNow /news/ listing and gather article URLs for the given date.
    URL itself doesn't contain the date, so we fetch each candidate and inspect
    its text. We stop once we've collected MAX_ARTICLES_PER_SITE.
    """
    html = fetch(MYK_NEWS_URL)
    soup = BeautifulSoup(html, "lxml")

    candidate_urls: List[str] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(MYK_BASE, href)

        if not href.startswith(MYK_BASE):
            continue
        if "/news/" not in href:
            continue
        if href in seen:
            continue

        seen.add(href)
        candidate_urls.append(href)

    urls_for_day: List[str] = []

    for u in candidate_urls:
        if len(urls_for_day) >= MAX_ARTICLES_PER_SITE:
            break

        try:
            html = fetch(u)
        except RuntimeError as e:
            print(f"[mykeenenow]   [WARN] Failed to fetch {u}: {e}")
            continue

        s = BeautifulSoup(html, "lxml")
        text = s.get_text(" ", strip=True)
        match = DATE_PATTERN.search(text)
        if not match:
            continue
        d = parse_us_date_string(match.group(0))
        if d == target_date:
            urls_for_day.append(u)

        time.sleep(0.3)

    return urls_for_day


def myk_scrape_article(url: str, fallback_date: Optional[date]) -> Optional[Dict]:
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    text = soup.get_text(" ", strip=True)
    pub_date: Optional[date] = None
    match = DATE_PATTERN.search(text)
    if match:
        pub_date = parse_us_date_string(match.group(0))
    if not pub_date:
        pub_date = fallback_date

    paragraphs: List[str] = []
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t:
            continue
        lowered = t.lower()
        if "story ©" in lowered and "saga communications" in lowered:
            continue
        paragraphs.append(t)

    return {
        "url": url,
        "title": title,
        "date": pub_date,
        "paragraphs": paragraphs,
        "images": [],
    }


def scrape_myk_for_date(target_date: date) -> List[Dict]:
    print(f"[mykeenenow] Fetching URLs for {target_date.isoformat()}")
    urls = myk_get_urls_for_date(target_date)
    print(f"[mykeenenow] Found {len(urls)} URLs (capped at {MAX_ARTICLES_PER_SITE})")

    articles: List[Dict] = []
    for u in urls:
        try:
            art = myk_scrape_article(u, fallback_date=target_date)
            if art:
                articles.append(art)
        except Exception as e:
            print(f"[mykeenenow]   [ERROR] Failed to scrape {u}: {e}")
            continue
        time.sleep(0.5)

    return articles


# ==========================
# CLI
# ==========================

SITE_FUNCTIONS: Dict[str, Callable[[date], List[Dict]]] = {
    "wmur": scrape_wmur_for_date,
    "vtdigger": scrape_vtdigger_for_date,
    "wcax": scrape_wcax_for_date,
    "mykeenenow": scrape_myk_for_date,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape local news sites into Stories/<date>/<site>/Original as .txt files"
    )
    parser.add_argument(
        "--site",
        choices=["wmur", "vtdigger", "wcax", "mykeenenow", "all"],
        default="all",
        help="Which site to scrape (default: all)",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Target date in YYYY-MM-DD (default: today)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("Invalid --date format. Use YYYY-MM-DD.")
    else:
        target_date = date.today()

    if args.site == "all":
        sites = list(SITE_FUNCTIONS.keys())
    else:
        sites = [args.site]

    print(f"Target date: {target_date.isoformat()}")
    print(f"Sites: {', '.join(sites)}")
    print("Output root:", ROOT_DIR.resolve())

    for site_slug in sites:
        scraper_fn = SITE_FUNCTIONS[site_slug]
        print(f"\n=== Scraping {site_slug} ===")
        try:
            articles = scraper_fn(target_date)
        except Exception as e:
            print(f"[{site_slug}] ERROR during scrape: {e}")
            continue

        save_articles_for_site(site_slug, target_date, articles)

    print("\nDone.")


if __name__ == "__main__":
    main()
