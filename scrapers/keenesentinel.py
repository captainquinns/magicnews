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
#  YOUR VALID COOKIE (Active)
# ==============================================================================
USER_COOKIE = """
cto_bundle=lDNeS19hTGZmV1FablpNaU9WNkZiQWpHMTdxeHJLMGslMkJYQUVzNGlxZWQ3T25QTTlkJTJCa3MybnhGRHJjYyUyRmk0ZE93bWg0bTl4UyUyQmVtYnRyTjR6WWo3cTI0b2FwNUVZN1NWRFRJSThsRVJVWGtqdDV2d3NjTXgzU1BDeVoxU080NlpNa2hr; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22892dfc0c-6a2a-46fa-8b38-fcc1762f3286%5C%22%2C%5B1764464442%2C395000000%5D%5D%22%5D%5D%5D; FCNEC=%5B%5B%22AKsRol_5JX_q7k090qgSuahUyeP8ISfdYfyv1Xngd0AVaW-lO46c_647iiH7oah_00vEDWJySuXsZs3Dyvxuydnlj-WGIUtlQjqyJxDI2ub8olS8vo22UnirdN1BqbXhBEo-yKUHxTgmy59WXeQlymzaMGGg3qxc4A%3D%3D%22%5D%5D; _au_1d=AU1D-0100-001764464442-FS27R8Q3-8R1S; _ga_D76YXV0HZ1=GS2.1.s1765931871$o3$g1$t1765934720$j60$l0$h0; _li_ss=CgA; gc_session_id=8cokj12krjqt2i6mu3kdcl; gcid_first=8c88f49d-cbb7-46ad-b932-ab88d17d062b; _ga=GA1.1.1138918661.1764464443; ajs_anonymous_id=b50e648d-bcb2-4208-b788-cad30f22b24d; ajs_user_id=6b07d9a2-8b97-11ec-b0c9-5cb9017b77dc; _cb=caa6YC5cSqtLpJwm; _cb_svref=external; _chartbeat2=.1765932351921.1765934718537.1.BeGBjQBYo6AJCm7Ws1DHsNQWDqb9rr.7; _chartbeat5=; _ga_4T2EB147B8=GS2.1.s1765931871$o3$g1$t1765934718$j60$l0$h0; _ga_FVWZ0RM4DH=GS2.1.s1765931945$o3$g1$t1765934718$j60$l0$h0; _hjSessionUser_3811413=eyJpZCI6ImMwMGM0MjdkLTY3NDYtNTIzMS04ZjBjLTRkMjcxMWE4NzQ5MyIsImNyZWF0ZWQiOjE3NjQ0NjQ0NDIxNTQsImV4aXN0aW5nIjp0cnVlfQ==; _ma_vws=5|1768526718928; TRINITY_USER_DATA=eyJ1c2VySWRUUyI6MTc2NTkzMjM1MTk3Nn0=; TRINITY_USER_ID=277ba6c6-ceb8-4449-8514-f331f677d386; _pbjs_userid_consent_data=3524755945110770; __eoi=ID=04a4224db103f28a:T=1764468280:RT=1765934713:S=AA-Afjb2leJXorn8uaB4IDcwxHTS; __gads=ID=38416ce2d9616fb5:T=1764468280:RT=1765934713:S=ALNI_MaoyWiaQPSNEkV6hvmeiFnpwbqy1Q; __gpi=UID=0000131657a68939:T=1764468280:RT=1765934713:S=ALNI_MYPNHW_K2sNiAxHqFfHO5qyO7YXyQ; _hjSession_3811413=eyJpZCI6IjMwNjljNGExLTQ3ZDYtNGFmNS1iZWJjLWQyMTE5YzUwMTJmMyIsImMiOjE3NjU5MzE4NzA5NDAsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowLCJzcCI6MH0=; tncms-auth=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiIsImtpZCI6ImY0NzJmMTI0NjZhNzQwMzdhMzJmMzIyZjc0ZjUwNjdiIn0.eyJpc3MiOiJodHRwczovL3d3dy5rZWVuZXNlbnRpbmVsLmNvbS8iLCJpYXQiOjE3NjU5MzMzMTMsIm5iZiI6MTc2NTkzMzMxMiwiZXhwIjoxODYwNTQxMzEzLCJzdWIiOiI2YjA3ZDlhMi04Yjk3LTExZWMtYjBjOS01Y2I5MDE3Yjc3ZGMiLCJqdGkiOiIyOTQ4NzAwYy03Njc3LTRiYTctYjYwZC02ZWIyMzIxZGY3YzUiLCJhcHAiOnt9LCJ0a24iOiIyOTdmNGI2Yi1lY2EyLTQ0MGQtOGVmNi0yOWZlYjcyZGJlODcifQ.avn4aUJYDmYvQUbEHWnDPwVO4dYdP9bllVphHs3WgwAAitGCxzOvzS_o-u2YW9o6qWXcFLfxHYAim6aNNNq4l7JJvhCFu-GB2pvB0Ho-30HJ9ZUFWtdOpBaskNtI2qFdt7sJjvTezAuxua6S67C1Hxmh5xxOwxTThCzHX-S34Nqdnnqqfmxg9w6Opvz493FerJ1wEodQToPHkYH6fWSszO9PgUQqoFT3wDScHFzQjYzkxb4h4kHz9-DfxORvqfsp4SlpPU_pUoIU29qlE32D7Q4tiJ1v24GJv1WU_RSHGFOmuO_mZJ_3xdo7Y5-FMxPkieosCFDPU3zfFfD8kdUWGQ; tncms-authtoken=1; tncms-avatarurl=https%3A%2F%2Fsecure.gravatar.com%2Favatar%2F0a5518701eaa561a93f4068d78a5452c%3Fs%3D100%26d%3Didenticon%26r%3Dg; tncms-dmp-id=fbd9c3fe05c85288886b7e1ce2fa43f974d40898; tncms-screenname=guest436; tncms-services=7041%2C7836; tncms-user=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiIsImtpZCI6ImY0NzJmMTI0NjZhNzQwMzdhMzJmMzIyZjc0ZjUwNjdiIn0.eyJpc3MiOiJodHRwczovL3d3dy5rZWVuZXNlbnRpbmVsLmNvbS8iLCJpYXQiOjE3NjU5MzMzMTMsIm5iZiI6MTc2NTkzMzMxMiwiZXhwIjoxODYwNTQxMzEzLCJzdWIiOiI2YjA3ZDlhMi04Yjk3LTExZWMtYjBjOS01Y2I5MDE3Yjc3ZGMiLCJqdGkiOiIyOTQ4NzAwYy03Njc3LTRiYTctYjYwZC02ZWIyMzIxZGY3YzUiLCJhcHAiOnsic3Vic2NyaXB0aW9uIjp7ImJsb3giOnsic3ViIjp7InNydiI6W3siaWQiOjc4MzYsInN0YSI6ImFjdGl2ZSIsImJlZ24iOiIyMDI1LTA5LTExVDE2OjE0OjQyKzAwOjAwIiwidGVybSI6IjIwMjYtMDMtMTdUMDQ6MDA6MDArMDA6MDAifV19fX0sInVzZXIiOnsic2NyIjoiZ3Vlc3Q0MzYiLCJjcnQiOjE2NDQ2MjQyOTksImVtbCI6eyJzaGExIjoiZmJkOWMzZmUwNWM4NTI4ODg4NmI3ZTFjZTJmYTQzZjk3NGQ0MDg5OCIsInNoYTI1NiI6IjE3ZDI4ZjdhODQ1ODE5NmIwOGM5ZmE5ZDQwZDc3ODk3NDgwMDE0N2Y0YzhmZDkxYTI4MDExY2EzYjk4YWVhOWYifSwiYXZhIjoiaHR0cHM6Ly9zZWN1cmUuZ3JhdmF0YXIuY29tL2F2YXRhci8wYTU1MTg3MDFlYWE1NjFhOTNmNDA2OGQ3OGE1NDUyYz9zPTEwMCZkPWlkZW50aWNvbiZyPWcifX19.u4u1uHrdChurI3CGf7d0zSoxbqQ61xmVEa7dA9TQJyKW2opRBtRecv51LM7vPf9NWLnqr85hz7U71qdC1Q5Hej7LZXfnVfCUwRJXyZE2c-0qRZzkskEVwx4b5IUbj1usv0IOLN9MeQEWiwVgryshRYcuK63q43xBBIvyipKuua3FFjl7wbTu0avD8p1Ek0BWWP5dtOuqKUPoamoOqLlr0kbqzBB19cpMYaPFlH0ROU4V5Df29DQ5ZaaN7CRqdf_qd84JwB9Bbd7495Tc14SDaM6bF_PcckKqUz_4lPcdbMlEFPNXceERhPXmV_i9gUMcKNmmWQk3iU7jxummna-Ikg; tnt-iq-login=1; tncms:meter:assetse9e896aa-1110-11ec-bd0f-93cbe33982ea=1; tncms:meter:assetse2832f2e-1110-11ec-bd0f-53d158595e36=1; _ma_uid=ce7f831f-dbac-4ed3-b742-fc4a4f6b8b32|1768524352201; tncms:meter:assetsd092df44-1110-11ec-bd0f-2710b9165ecb=1; _lc2_fpi_js=dd2a3570363c--01kb9831tkw4m569y4batb8bg6; _li_dcdm_c=.keenesentinel.com; _iiq_fdata=%7B%22pcid%22%3A%22a18774e9-b625-8f62-ae73-09ea612130c9%22%2C%22pcidDate%22%3A1764468295391%7D; logglytrackingsession=7f41e686-08eb-45ce-aaf2-b2d4dcc8ad2a; 33acrossIdFp=kQsUWZhE498Tvbiv9mhfPSM9jWk%2BnyVxCdnvIewC%2Fd4cc7wvgwhttd6JEe%2BawKl6ORMLwS8ORcczIZ5Gp5eIQw%3D%3D; _cc_id=888e1f440d95f24cede2da57126151ff; panoramaId=a84053d54f5931cb3b9bd83c5b3b185ca02cb9d1b580201e717d791030972835; panoramaIdType=panoDevice; panoramaId_expiry=1766536670886; tncms_csrf_token=23ff810af15e049227ed5732d0b961737d089756b3cf25eab5633e7a82ce42f5.8f4c1195c0f07532df9e; _ga_12M2XZC8V4=GS2.1.s1764468279$o1$g1$t1764468297$j60$l0$h0; _lc2_fpi=dd2a3570363c--01kb9831tkw4m569y4batb8bg6; _sp_id.d7d7=c7cc4e56-7cf1-4b75-a553-363954cb7518.1764468280.1.1764468281..f08f03fe-29c9-4e92-bc55-ee3796dda0d0..05de6760-7487-4202-a7a3-da4bef19da51.1764468280217.2; _gcl_au=1.1.1572780234.1764464443
"""
# ==============================================================================

SEARCH_API_URL = "https://www.keenesentinel.com/search/"
BASE_URL = "https://www.keenesentinel.com"

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Accept": "application/json, text/javascript, */*; q=0.01", 
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.keenesentinel.com/news/local/",
    "Cookie": USER_COOKIE.strip()
}

def clean_html_text(raw_html: Union[str, List]) -> List[str]:
    """Helper to convert the raw JSON HTML blob into clean paragraphs."""
    if not raw_html: return []
    
    # Handle list input (common in BLOX API)
    if isinstance(raw_html, list):
        raw_html = "".join([str(x) for x in raw_html])
        
    soup = BeautifulSoup(raw_html, "lxml")
    
    paragraphs = []
    stops = ["copyright", "subscribe", "sign up", "print", "email"]

    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if not t: continue
        
        lowered = t.lower()
        if any(stop in lowered for stop in stops) and len(lowered) < 50:
            continue
            
        paragraphs.append(t)
    return paragraphs

def scrape(target_date: date) -> List[Dict]:
    logger.info(f"[KeeneSentinel] Contacting JSON API for {target_date}...")
    
    params = {
        "f": "json",
        "t": "article",
        "c[]": "news/local",
        "l": "100", 
        "sort": "starttime", 
        "sd": "desc",
    }

    try:
        resp = requests.get(SEARCH_API_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"[KeeneSentinel] API Request Failed: {e}")
        return []

    rows = data.get("rows", [])
    logger.info(f"[KeeneSentinel] API returned {len(rows)} raw items.")

    valid_articles = []
    
    for row in rows:
        # Date Logic
        start_time_obj = row.get("starttime")
        start_time_str = ""
        
        if isinstance(start_time_obj, dict):
            start_time_str = start_time_obj.get("iso8601") or start_time_obj.get("value") or start_time_obj.get("iso")
        elif isinstance(start_time_obj, str):
            start_time_str = start_time_obj
            
        if not start_time_str:
            continue
        
        try:
            # Parse ISO date string
            dt_str = start_time_str.split("T")[0]
            y, m, d = map(int, dt_str.split("-"))
            pub_date = date(y, m, d)
        except (ValueError, AttributeError):
            continue
            
        # STRICT DATE CHECK
        if pub_date != target_date:
            continue

        title = row.get("title", "Untitled")
        
        # === FIX: Use urljoin to prevent double domains ===
        raw_url = row.get("url", "")
        url = urljoin(BASE_URL, raw_url)
        
        # Content Logic
        raw_body = row.get("content") or row.get("body")
        if not raw_body: continue

        paragraphs = clean_html_text(raw_body)
        if not paragraphs: continue

        logger.info(f"[KeeneSentinel] + MATCH: {title[:30]}...")
        
        valid_articles.append({
            "url": url,
            "title": title,
            "date": pub_date,
            "paragraphs": paragraphs
        })

    return valid_articles