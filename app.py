import streamlit as st
import sys
import time
import pyperclip
import shutil
from datetime import date
from pathlib import Path
from collections import defaultdict
from streamlit.runtime.scriptrunner import get_script_run_ctx

st.cache_data.clear()

# --- NEW AUTO-SHUTDOWN WATCHDOG ---
import threading
import os
from streamlit.runtime import Runtime

def watch_for_disconnect():
    """
    Background process: Checks every 2 seconds if a browser is connected.
    If no browsers are connected, it kills the terminal process.
    """
    while True:
        time.sleep(5)
        try:
            # Check if there are any active browser sessions
            if not Runtime.instance()._session_mgr.list_active_sessions():
                # Double check after a short wait (in case of page refresh)
                time.sleep(5)
                if not Runtime.instance()._session_mgr.list_active_sessions():
                    print("Browser closed. Shutting down server...")
                    os._exit(0) # Force kills the terminal
        except Exception:
            pass # Runtime might not be ready yet, just keep waiting

# Start the watchdog thread only once when the app launches
if "watchdog_started" not in st.session_state:
    threading.Thread(target=watch_for_disconnect, daemon=True).start()
    st.session_state.watchdog_started = True
# ----------------------------------

# --- IMPORT REWRITER LOGIC ---
from summarize_archive import (
    parse_article_file, 
    rewrite_with_ai, 
    merge_with_ai,
    rewritten_txt_path, 
    ArticleMetadata
)

from scrapers import AVAILABLE_SCRAPERS, save_articles
import scrapers.base

# --- CONFIG ---
LOGO_PATH = Path("/Users/quinnwilson/Documents/NewsArchive/assets/Magic-96.7-Pink-Transparent.png")
TAG_COLORS = {
    "None": "None",
    "Red Group": "🔴",
    "Blue Group": "🔵",
    "Green Group": "🟢",
    "Yellow Group": "🟡",
    "Purple Group": "🟣"
}

st.set_page_config(page_title="News Rewriter", layout="wide", page_icon="🗞️")

# --- CSS ---
st.markdown("""
    <style>
    a { color: #27d2e2 !important; text-decoration: none; font-weight: bold; }
    div.stButton > button { background-color: #40297b !important; color: white !important; border: 1px solid #40297b !important; }
    .link-container { padding-top: 8px; }
    
    /* Align checkbox and expander vertically in Review tab */
    div[data-testid="stColumn"] > div {
        display: flex;
        align-items: center;
        height: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# --- AUTO-CLEANUP LOGIC ---
def cleanup_old_files(root_dir: Path, days_to_keep: int = 30):
    """Deletes folders older than X days based on their YYYY-MM-DD name."""
    if not root_dir.exists():
        return

    from datetime import date, datetime, timedelta
    import shutil

    cutoff_date = date.today() - timedelta(days=days_to_keep)
    deleted_count = 0

    # Folders to check: Stories/DATE and Stories/Published/DATE
    search_paths = [root_dir, root_dir / "Published"]

    for base_path in search_paths:
        if not base_path.exists(): continue
        
        for folder in base_path.iterdir():
            if not folder.is_dir(): continue
            
            # Try to parse folder name as YYYY-MM-DD
            try:
                folder_date = datetime.strptime(folder.name, "%Y-%m-%d").date()
                if folder_date < cutoff_date:
                    shutil.rmtree(folder)
                    deleted_count += 1
            except ValueError:
                # Skip folders that aren't named as dates (like 'assets')
                continue
    
    if deleted_count > 0:
        st.sidebar.warning(f"Cleanup: Removed {deleted_count} folders older than {days_to_keep} days.")

@st.dialog("Original Article Text")
def show_file_content(file_path):
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    st.text_area("Raw Text", content, height=500, disabled=True)

@st.cache_data(ttl=3600)
def get_original_files(root_path, target_date, site):
    path = root_path / str(target_date) / site / "Original"
    if not path.exists(): return []
    files = []
    for f in sorted(path.glob("*.txt")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            title = lines[0].strip() if lines else f.name
            url = ""
            for line in lines[:10]: 
                if line.lower().startswith("url:"):
                    url = line.split(":", 1)[1].strip()
                    break
            files.append({"path": f, "filename": f.name, "title": title, "url": url, "site": site})
        except: continue
    return files

def get_status_and_content(original_path_obj, root_dir, target_date):
    pub_file = root_dir / "Published" / str(target_date) / original_path_obj.name
    pub_file_rewritten = root_dir / "Published" / str(target_date) / rewritten_txt_path(original_path_obj).name
    if pub_file.exists(): return pub_file.read_text(encoding="utf-8", errors="ignore"), True, pub_file
    if pub_file_rewritten.exists(): return pub_file_rewritten.read_text(encoding="utf-8", errors="ignore"), True, pub_file_rewritten
    draft_path = rewritten_txt_path(original_path_obj)
    if draft_path.exists(): return draft_path.read_text(encoding="utf-8", errors="ignore"), False, draft_path
    return None, False, None

def toggle_publish_status(current_path, is_posted, root_dir, target_date, original_path_obj):
    try:
        if not is_posted:
            dest_dir = root_dir / "Published" / str(target_date)
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current_path), str(dest_dir / current_path.name))
        else:
            parts = list(original_path_obj.parts)
            if "Original" in parts:
                parts[parts.index("Original")] = "Rewritten"
                dest_file = Path(*parts)
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current_path), str(dest_file))
    except Exception as e: st.error(f"Action failed: {e}")

def process_grouped_files(selected_items):
    progress_bar = st.progress(0)
    status_text = st.empty()
    buckets = defaultdict(list)
    for item in selected_items:
        unique_key = f"tag_{item['site']}_{item['filename']}"
        tag = st.session_state.get(unique_key, "None")
        buckets[tag].append(item)
    
    total_tasks = len(buckets)
    for i, (tag, items) in enumerate(buckets.items()):
        # If it's the "None" bucket, show the count. Otherwise, show the Group Name.
        if tag == "None":
            status_text.text(f"Processing {len(items)} individual articles...")
        else:
            status_text.text(f"Processing {tag} group...")
        try:
            if tag == "None" or len(items) == 1:
                for item in items:
                    meta, body = parse_article_file(item['path'])
                    rewritten, _ = rewrite_with_ai(body, title=meta.title)
                    out = rewritten_txt_path(item['path'])
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(rewritten, encoding="utf-8")
            else:
                article_data = []
                for item in items:
                    meta, body = parse_article_file(item['path'])
                    article_data.append({'title': meta.title, 'text': body, 'site': item['site']})
                merged_text = merge_with_ai(article_data)
                out = rewritten_txt_path(items[0]['path'])
                out = out.parent / f"Merged_{tag.replace(' ','_')}_{items[0]['filename']}"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(merged_text, encoding="utf-8")
        except Exception as e: st.error(f"Group {tag} failed: {e}")
        progress_bar.progress((i + 1) / total_tasks)
    status_text.text("Complete!")
    time.sleep(1)
    st.rerun()

# --- SIDEBAR & HEADER ---
st.sidebar.title("Controls")
ROOT_DIR = Path(st.sidebar.text_input("Archive Folder Path", value=str(Path("Stories").resolve()))).expanduser().resolve()
cleanup_old_files(ROOT_DIR, days_to_keep=30)
if ROOT_DIR.exists(): scrapers.base.ROOT_DIR = ROOT_DIR
selected_date = st.sidebar.date_input("Select Date", date.today())

if st.sidebar.button("🔄 Scrape Manually", type="primary"):
    for site_slug, scrape_func in AVAILABLE_SCRAPERS.items():
        try:
            articles = scrape_func(selected_date)
            save_articles(site_slug, selected_date, articles)
        except: pass
    st.rerun()

if LOGO_PATH.exists(): st.image(str(LOGO_PATH), width=400) 
else: st.title("🎙️ Magic News Rewriter")

tab1, tab2 = st.tabs(["📝 Select & Rewrite", "✅ Proof & Review"])
SITES = ["keenesentinel", "reformer", "wmur", "wcax", "vtdigger", "mykeenenow"]

# --- TAB 1: SELECTION ---
with tab1:
    all_site_files = {} 
    total_found = 0
    for site in SITES:
        files = get_original_files(ROOT_DIR, selected_date, site)
        if files: 
            all_site_files[site] = files
            total_found += len(files)

    c_info, c_btn = st.columns([3, 1])
    with c_info: st.subheader(f"Found {total_found} articles")
    with c_btn:
        if st.button("🚀 Process Selection", type="primary", use_container_width=True):
            to_run = []
            for site, files in all_site_files.items():
                is_all = st.session_state.get(f"all_{site}", False)
                for f in files:
                    chk_key = f"chk_{site}_{f['filename']}"
                    if is_all or st.session_state.get(chk_key, False):
                        to_run.append(f)
            if to_run: process_grouped_files(to_run)

    st.divider()

    for site in SITES:
        if site not in all_site_files: continue
        st.markdown(f"### {site.upper()}")
        st.checkbox(f"Select All {site.upper()}", key=f"all_{site}")

        for f in all_site_files[site]:
            c1, c2, c3, c4 = st.columns([0.05, 0.73, 0.12, 0.10])
            with c1:
                chk_key = f"chk_{site}_{f['filename']}"
                val = True if st.session_state.get(f"all_{site}") else st.session_state.get(chk_key, False)
                st.checkbox(f"Select {f['title']}", value=val, key=chk_key, label_visibility="collapsed")
            with c2:
                if f['url']: st.markdown(f"[{f['title']}]({f['url']})")
                else: st.write(f"**{f['title']}**")
            with c3:
                tag_key = f"tag_{site}_{f['filename']}"
                st.selectbox("Tag", options=list(TAG_COLORS.values()), key=tag_key, label_visibility="collapsed")
            with c4:
                if st.button("📄", key=f"view_{site}_{f['filename']}"): show_file_content(f['path'])
        st.divider()

# --- TAB 2: REVIEW (UI FIX FOR POSTED CHECKBOX) ---
with tab2:
    st.header("Review Dashboard")
    found_any = False
    for site in SITES:
        files = get_original_files(ROOT_DIR, selected_date, site)
        rew_dir = ROOT_DIR / str(selected_date) / site / "Rewritten"
        merged_files = list(rew_dir.glob("Merged_*.txt")) if rew_dir.exists() else []
        
        rewritten_items = []
        for f in files:
            content, is_posted, current_path = get_status_and_content(f['path'], ROOT_DIR, selected_date)
            if content: rewritten_items.append({"meta": f, "content": content, "is_posted": is_posted, "path": current_path, "type": "Normal"})
        
        for mf in merged_files:
            pub_m = ROOT_DIR / "Published" / str(selected_date) / mf.name
            actual_path = pub_m if pub_m.exists() else mf
            is_m_posted = pub_m.exists()
            rewritten_items.append({
                "meta": {"title": mf.name, "filename": mf.name, "url": None, "path": mf, "site": site}, 
                "content": actual_path.read_text(encoding="utf-8", errors="ignore"), 
                "is_posted": is_m_posted, 
                "path": actual_path, 
                "type": "Merged"
            })

        if rewritten_items:
            found_any = True
            st.markdown(f"### {site.upper()}")
            for item in rewritten_items:
                # Column setup to place checkbox to the far left of the expander
                c_check, c_exp = st.columns([0.03, 0.97])
                
                with c_check:
                    p_key = f"p_{item['meta']['site']}_{item['meta']['filename']}"
                    p_state = st.checkbox(f"Posted status for {item['meta']['title']}", value=item['is_posted'], key=p_key, label_visibility="collapsed")
                    if p_state != item['is_posted']:
                        toggle_publish_status(item['path'], item['is_posted'], ROOT_DIR, selected_date, item['meta'].get('path'))
                        st.rerun()
                        
                with c_exp:
                    icon = "🚀" if item['is_posted'] else "✅"
                    with st.expander(f"{icon} {item['meta']['title']}", expanded=False):
                        c_t, c_c, c_l = st.columns([0.25, 0.2, 0.55])
                        with c_t: show_orig = st.toggle("View Original", key=f"s_{item['meta']['site']}_{item['meta']['filename']}")
                        with c_c:
                            if st.button("📋 Copy", key=f"cp_{item['meta']['site']}_{item['meta']['filename']}"):
                                pyperclip.copy(item['content'])
                                st.toast("Copied!")
                        with c_l: 
                            if item['meta']['url']: st.markdown(f"<a href='{item['meta']['url']}' target='_blank'>🔗 Open Original</a>", unsafe_allow_html=True)
                        st.divider()
                        if show_orig and item['type'] == "Normal": st.warning(item['meta']['path'].read_text(encoding="utf-8", errors="ignore"))
                        else:
                            st.text_area("Final Text", value=item['content'], height=300, label_visibility="collapsed")

    if not found_any: st.info("No rewritten articles found yet.")