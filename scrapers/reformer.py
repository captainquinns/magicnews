import re
import time
import json
import requests
from datetime import datetime, date
from typing import List, Dict, Optional, Union
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from .base import logger

# ==============================================================================
#  PASTE YOUR BRATTLEBORO REFORMER COOKIE HERE
# ==============================================================================
USER_COOKIE = """
_ml_id=3e14d3f3-0770-400e-bb81-816c756c1ac3.1765936187.1.1765936338.1765936187; _ml_ses=*; AWSALB=meNnbGEbkxIrI2/UYXlT0VtQQMajqSqKI8bP2WODiJr1F5hs2XJ39QUallhuOUtpAv2qeJIrUil+wb+rNSD2NgOrLD7Klekc84Xzfr+UcHCVqwuNdC0DA7kxTleK; AWSALBCORS=meNnbGEbkxIrI2/UYXlT0VtQQMajqSqKI8bP2WODiJr1F5hs2XJ39QUallhuOUtpAv2qeJIrUil+wb+rNSD2NgOrLD7Klekc84Xzfr+UcHCVqwuNdC0DA7kxTleK; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%224ffc8087-272e-4d0a-a91f-7c1335ab5f30%5C%22%2C%5B1765936187%2C120000000%5D%5D%22%5D%5D%5D; FCNEC=%5B%5B%22AKsRol_6kpZw7XOLbEzKth4C7yskHiUnBCGl3I562Sic6QCEk-yBaGUbxgN2HAWWyjhdCGO54yOMhFLhhtSi4C62_PUUvYRLu0zciDLGsxo1zAiyqfL5dm1em0Yhc7espaLPNHCH07HV8xpVBoxt1ELGhxvFDjzaPQ%3D%3D%22%5D%5D; cto_bundle=Jgc9Gl9rSk1OYmJmZjNuJTJCUFp5T3VXZWYxVUlvNjhtc29ER2pKZGF2dVo3ejVIT1NlQmdFWVp6T3VIR2QyMHFSODBjVHNkOGZTTmhTMGdVRGM0SiUyQjlLVUZ1dnJhTWNXNlZuVjdtYjZKTGFyVkpIUEFpYml6TEZ6TkdUd1MydWxvc05jVU8; _au_1d=AU1D-0100-001765936187-A974WA0N-9N3I; _ga=GA1.1.1183864495.1765936187; _ga_12M2XZC8V4=GS2.1.s1765936187$o1$g1$t1765936327$j60$l0$h0; _ga_4T2EB147B8=GS2.1.s1765936187$o1$g1$t1765936327$j60$l0$h0; _ga_EKHNFZ1N3P=GS2.1.s1765936187$o1$g1$t1765936327$j60$l0$h0; _ga_FVWZ0RM4DH=GS2.1.s1765936265$o1$g1$t1765936327$j60$l0$h0; _sp_uid=amFyZWRAbWFnaWM5NjcuY29t%2C1; ajs_anonymous_id=5c8427b4-be3a-44fa-8a06-306e9eaaf309; _empowerlocal_vid=32dfa9f1-ac68-48c4-91e4-95935ad64905; _pbjs_userid_consent_data=3524755945110770; flipp-uid=a870586d-509e-432b-a653-d53b4dc3091c; _sp_id.afb4=ee0568b3-1750-424c-aa6c-0d81883325f3.1765936187.1.1765936324..28ef9697-6f9a-487f-948d-f8247aaf8441....0; _sp_ses.afb4=*; blaize_jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJQcm9kIjoiZ29sZCIsImlzcyI6ImF1dGgwIiwiSUQiOiJqYXJlZEBtYWdpYzk2Ny5jb20iLCJleHAiOjE3NjYwMjI2ODR9.DXOBIIL6OUG0PWtyLW9eNjcBrU2nkC1SQIdE8tBL1f0; blaize_session=c9ee3a91-6ced-4d41-b679-aaad9dfccc59; blaize_tracking_id=6da8d913-2e09-4361-a75b-55c98b895c71; nw_auth=Y; nw_hash=bf62354c8bfbf5a4ad1a367aea86dcbd; nw_login=jared@magic967.com; nwssmcookie=Y; 33acrossIdFp=b5Rm55CQv%2FTiVTZRMP3xzjHzC7kDySc04Mk2pgdx9NAF2fOlBImc%2B%2B9Lb%2BrXiiouF1z2f9vtONk67WW7VjLrnQ%3D%3D; __eoi=ID=c79fc6078162ac83:T=1765936187:RT=1765936187:S=AA-Afja9-VIqJ76knIGsP2I4FiEw; __gads=ID=39fe84f37af86e27:T=1765936187:RT=1765936187:S=ALNI_MZtAICaGxL8RolM4zB5_xTxE7sD5w; __gpi=UID=0000131c87bafe78:T=1765936187:RT=1765936187:S=ALNI_MZcwpgLOrbXW-s2Pik0ly0Ig8zdLw; _cc_id=39a818e35a8580baddec48f3f466f674; panoramaId=2e4133f17d1f9f8f8615aa55b77e185ca02c0e4117bd30c550290e7dba044e29; panoramaIdType=panoDevice; panoramaId_expiry=1766540987026; _iiq_fdata=%7B%22pcid%22%3A%223044de9c-8031-4966-2696-c0023a8cbeb0%22%2C%22pcidDate%22%3A1765936187493%2C%22isOptedOut%22%3Afalse%2C%22gdprString%22%3A%22%22%2C%22gppString%22%3A%22%22%2C%22uspString%22%3A%221---%22%2C%22sCal%22%3A1765936187942%2C%22dbsaved%22%3A%22false%22%2C%22group%22%3A%22A%22%7D; tncms_csrf_token=1e68dfeeeda8b0cb4807b2eb2edc38f83e53722d79636165781bc378dc25e484.a0c36ee0cfa5224d760e
"""
# ==============================================================================

# Brattleboro Reformer API Config
# Note: They use the same /search/ endpoint structure as Keene Sentinel (BLOX CMS)
SEARCH_API_URL = "https://www.reformer.com/search/"
BASE_URL = "https://www.reformer.com"

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Accept": "application/json, text/javascript, */*; q=0.01", 
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.reformer.com/local-news/",
    "Cookie": USER_COOKIE.strip()
}

def clean_html_text(raw_html: Union[str, List]) -> List[str]:
    """Helper to convert raw HTML (or list of strings) into clean paragraphs."""
    if not raw_html: return []
    
    # Handle list input (common in BLOX API)
    if isinstance(raw_html, list):
        raw_html = "".join([str(x) for x in raw_html])
        
    soup = BeautifulSoup(raw_html, "lxml")
    
    paragraphs = []
    # Stop words to cut off footer noise
    stops = ["copyright", "subscribe", "sign up", "print", "email", "click here"]

    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t: continue
        
        lowered = t.lower()
        if any(stop in lowered for stop in stops) and len(lowered) < 50:
            continue
            
        paragraphs.append(t)
    return paragraphs

def scrape(target_date: date) -> List[Dict]:
    if "PASTE_YOUR" in USER_COOKIE:
        logger.error("[Reformer] PLEASE PASTE YOUR COOKIE IN scraper/reformer.py")
        return []

    logger.info(f"[Reformer] Contacting JSON API for {target_date}...")
    
    # API Parameters for Local News
    # c[] filters by category. 'local-news' is the standard slug.
    params = {
        "f": "json",
        "t": "article",
        "c[]": "local-news", # Targeted category
        "l": "50",           # Limit
        "sort": "starttime", # Sort by publication time
        "sd": "desc",        # Descending order
    }

    try:
        resp = requests.get(SEARCH_API_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[Reformer] API Request Failed: {e}")
        return []

    rows = data.get("rows", [])
    logger.info(f"[Reformer] API returned {len(rows)} raw items.")

    valid_articles = []
    
    for row in rows:
        # --- Date Logic ---
        start_time_obj = row.get("starttime")
        start_time_str = ""
        
        if isinstance(start_time_obj, dict):
            start_time_str = start_time_obj.get("iso8601") or start_time_obj.get("value")
        elif isinstance(start_time_obj, str):
            start_time_str = start_time_obj
            
        if not start_time_str: continue
        
        try:
            # Parse ISO: "2025-12-16T10:00:00-05:00"
            dt_str = start_time_str.split("T")[0]
            y, m, d = map(int, dt_str.split("-"))
            pub_date = date(y, m, d)
        except (ValueError, AttributeError):
            continue
            
        # Strict Date Check
        if pub_date != target_date:
            continue

        # --- Content Logic ---
        title = row.get("title", "Untitled")
        
        # Build full URL
        raw_url = row.get("url", "")
        url = urljoin(BASE_URL, raw_url)
        
        # Extract Body
        raw_body = row.get("content") or row.get("body")
        if not raw_body: continue

        paragraphs = clean_html_text(raw_body)
        if not paragraphs: continue

        logger.info(f"[Reformer] + MATCH: {title[:30]}...")
        
        valid_articles.append({
            "url": url,
            "title": title,
            "date": pub_date,
            "paragraphs": paragraphs
        })

    return valid_articles