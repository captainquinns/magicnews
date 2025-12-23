import streamlit as st
import sys
import time
import pyperclip
import shutil
from datetime import date
from pathlib import Path

# --- IMPORT REWRITER LOGIC ---
from summarize_archive import (
    parse_article_file, 
    rewrite_with_ai, 
    rewritten_txt_path, 
    ArticleMetadata
)

# --- IMPORT SCRAPER LOGIC ---
from scrapers import AVAILABLE_SCRAPERS, save_articles
import scrapers.base

# --- CONFIG & PATHS ---
LOGO_PATH = Path("/Users/quinnwilson/Documents/NewsArchive/assets/Magic-96.7-Pink-Transparent.png")

# --- PAGE CONFIG ---
st.set_page_config(page_title="News Rewriter", layout="wide", page_icon="🗞️")

# --- CUSTOM COLORS (CSS) ---
st.markdown("""
    <style>
    a { color: #27d2e2 !important; text-decoration: none; font-weight: bold; }
    a:hover { text-decoration: underline; }
    
    div.stButton > button {
        background-color: #40297b !important;
        color: white !important;
        border: 1px solid #40297b !important;
    }
    div.stButton > button:hover {
        background-color: #5336a0 !important;
        border-color: #5336a0 !important;
    }
    
    .link-container { padding-top: 8px; }
    
    /* Align checkbox with expander header */
    div[data-testid="stColumn"] {
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    </style>
""", unsafe_allow_html=True)

# --- POPUP DIALOG FUNCTION ---
@st.dialog("Original Article Text")
def show_file_content(file_path):
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        st.text_area("Raw Text", content, height=500, disabled=True)
    except Exception as e:
        st.error(f"Could not read file: {e}")

# --- HELPER FUNCTIONS ---
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
    """
    Checks both 'Published' and 'Rewritten' folders.
    Returns: (content, is_posted, current_path)
    """
    # 1. Check Published Folder First
    pub_file = root_dir / "Published" / str(target_date) / original_path_obj.name
    # Also check rewritten suffix in published
    pub_file_rewritten = root_dir / "Published" / str(target_date) / rewritten_txt_path(original_path_obj).name
    
    if pub_file.exists():
        return pub_file.read_text(encoding="utf-8", errors="ignore"), True, pub_file
    if pub_file_rewritten.exists():
        return pub_file_rewritten.read_text(encoding="utf-8", errors="ignore"), True, pub_file_rewritten

    # 2. Check Rewritten Folder (Drafts)
    draft_path = rewritten_txt_path(original_path_obj)
    if draft_path.exists():
        return draft_path.read_text(encoding="utf-8", errors="ignore"), False, draft_path
        
    return None, False, None

def toggle_publish_status(current_path, is_posted, root_dir, target_date, original_path_obj):
    """Moves file between Published and Rewritten folders."""
    try:
        if not is_posted:
            # Move TO Published
            dest_dir = root_dir / "Published" / str(target_date)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / current_path.name
            shutil.move(str(current_path), str(dest_file))
            st.toast(f"✅ Posted: {original_path_obj.name}")
        else:
            # Move BACK to Rewritten (Drafts)
            # We need to reconstruct the original rewritten path structure
            # Default logic from summarize_archive: Stories/DATE/SITE/Rewritten/file.txt
            parts = list(original_path_obj.parts)
            if "Original" in parts:
                idx = parts.index("Original")
                parts[idx] = "Rewritten"
                dest_file = Path(*parts)
            else:
                # Fallback if structure is weird
                dest_file = original_path_obj.with_suffix(".rewritten.txt")
            
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current_path), str(dest_file))
            st.toast(f"↩️ Un-posted: {original_path_obj.name}")
            
    except Exception as e:
        st.error(f"Action failed: {e}")

def process_files(file_list):
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(file_list)
    success_count = 0
    for i, item in enumerate(file_list):
        status_text.text(f"Rewriting {i+1}/{total}: {item['title']}...")
        try:
            meta, body_text = parse_article_file(item['path'])
            meta.site_id = item['site']
            rewritten_text, _ = rewrite_with_ai(body_text, title=meta.title)
            out_path = rewritten_txt_path(item['path'])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as f:
                f.write(rewritten_text)
                f.write("\n")
            success_count += 1
        except Exception as e:
            st.error(f"Failed to rewrite {item['filename']}: {e}")
        progress_bar.progress((i + 1) / total)
    status_text.text(f"Complete! Processed {success_count} articles.")
    time.sleep(1)
    st.rerun()

# --- SIDEBAR ---
st.sidebar.title("Controls")
default_path = str(Path("Stories").resolve())
root_input = st.sidebar.text_input("Archive Folder Path", value=default_path)
ROOT_DIR = Path(root_input).expanduser().resolve()

if ROOT_DIR.exists(): scrapers.base.ROOT_DIR = ROOT_DIR
else: st.sidebar.error("⚠️ Folder not found!")

st.sidebar.divider()
selected_date = st.sidebar.date_input("Select Date", date.today())

if st.sidebar.button("🔄 Scrape Manually", type="primary"):
    st.sidebar.caption("Starting scraper...")
    scrape_progress = st.sidebar.progress(0)
    total_sites = len(AVAILABLE_SCRAPERS)
    for idx, (site_slug, scrape_func) in enumerate(AVAILABLE_SCRAPERS.items()):
        try:
            articles = scrape_func(selected_date)
            save_articles(site_slug, selected_date, articles)
            st.sidebar.success(f"✅ {site_slug.upper()} Done")
        except Exception as e:
            st.sidebar.error(f"❌ {site_slug.upper()} Failed: {e}")
        scrape_progress.progress((idx + 1) / total_sites)
    st.sidebar.success("All scrapers finished!")
    time.sleep(1)
    st.rerun()

st.sidebar.info(f"Looking in:\n{ROOT_DIR}\n\nFor date:\n{selected_date}")

if LOGO_PATH.exists(): st.image(str(LOGO_PATH), width=400) 
else: st.title("🎙️ Magic News Rewriter")

# --- MAIN LAYOUT ---
tab1, tab2 = st.tabs(["📝 Select & Rewrite", "✅ Proof & Review"])
SITES = ["keenesentinel", "reformer", "wmur", "wcax", "vtdigger", "mykeenenow"]

# --- TAB 1: SELECTION ---
with tab1:
    all_site_files = {} 
    total_files_found = 0
    for site in SITES:
        files = get_original_files(ROOT_DIR, selected_date, site)
        if files:
            all_site_files[site] = files
            total_files_found += len(files)

    selected_files_to_process = []
    
    c_info, c_btn = st.columns([3, 1])
    with c_info:
        st.subheader(f"Found {total_files_found} articles for {selected_date}")
        if not total_files_found: st.warning("No articles found.")
    
    with c_btn:
        count = len(selected_files_to_process)
        if st.button(f"🚀 Rewrite", type="primary", use_container_width=True):
            to_run = []
            for site, files in all_site_files.items():
                is_all = st.session_state.get(f"all_{site}", False)
                for f in files:
                    if is_all or st.session_state.get(f"chk_{f['filename']}", False):
                        to_run.append(f)
            if to_run: process_files(to_run)
            else: st.error("Select articles first!")

    st.divider()

    for site in SITES:
        if site not in all_site_files: continue
        files = all_site_files[site]
        st.markdown(f"### {site.upper()}")
        st.checkbox(f"Select All {site.upper()}", key=f"all_{site}")

        for f in files:
            c1, c2, c3 = st.columns([0.05, 0.85, 0.10])
            with c1:
                disabled_state = st.session_state.get(f"all_{site}", False)
                val = True if disabled_state else st.session_state.get(f"chk_{f['filename']}", False)
                st.checkbox("", value=val, key=f"chk_{f['filename']}", disabled=disabled_state, label_visibility="collapsed")
            with c2:
                if f['url']: st.markdown(f"[{f['title']}]({f['url']})")
                else: st.write(f"**{f['title']}**")
            with c3:
                if st.button("📄", key=f"view_{f['filename']}"): show_file_content(f['path'])
        st.divider()

# --- TAB 2: REVIEW ---
with tab2:
    st.header("Review Dashboard")
    found_any = False
    
    for site in SITES:
        files = get_original_files(ROOT_DIR, selected_date, site)
        
        rewritten_pairs = []
        for f in files:
            # Check status (Posted vs Rewritten)
            content, is_posted, current_path = get_status_and_content(f['path'], ROOT_DIR, selected_date)
            
            if content:
                rewritten_pairs.append({
                    "meta": f, 
                    "content": content, 
                    "is_posted": is_posted,
                    "current_path": current_path
                })
        
        if rewritten_pairs:
            found_any = True
            st.markdown(f"### {site.upper()}")
            
            for item in rewritten_pairs:
                meta = item['meta']
                is_posted = item['is_posted']
                
                # === NEW LAYOUT: [Checkbox] [Expander] ===
                col_check, col_exp = st.columns([0.05, 0.95])
                
                with col_check:
                    # The "Posted" Checkmark
                    posted_state = st.checkbox(
                        "Posted", 
                        value=is_posted, 
                        key=f"posted_chk_{meta['filename']}", 
                        label_visibility="collapsed",
                        help="Check to mark as Posted (Moves file to Published folder)"
                    )
                    
                    # Logic to trigger move if state changed
                    if posted_state != is_posted:
                        toggle_publish_status(item['current_path'], is_posted, ROOT_DIR, selected_date, meta['path'])
                        time.sleep(0.1)
                        st.rerun()

                with col_exp:
                    # Visual feedback in title
                    icon = "✅" if not is_posted else "🚀" # Check for rewrite, Rocket for Posted
                    title_label = f"{icon} {meta['title']}"
                    
                    with st.expander(title_label, expanded=False):
                        
                        # [Toggle] [Copy] [Link]
                        c_toggle, c_copy, c_link = st.columns([0.25, 0.2, 0.55])
                        
                        with c_toggle:
                            show_orig = st.toggle("View Original", key=f"swap_{meta['filename']}")
                        
                        with c_copy:
                            if st.button("📋 Copy Text", key=f"copy_{meta['filename']}"):
                                try:
                                    pyperclip.copy(item['content'])
                                    st.toast("Copied to clipboard!", icon="✅")
                                except Exception as e:
                                    st.error(f"Copy failed: {e}")

                        with c_link:
                            if meta['url']:
                                st.markdown(f"<div class='link-container'><a href='{meta['url']}' target='_blank'>🔗 Open Article Website</a></div>", unsafe_allow_html=True)

                        st.divider()
                        
                        if show_orig:
                            orig_text = meta['path'].read_text(encoding="utf-8", errors="ignore")
                            st.warning(orig_text)
                        else:
                            st.success(item['content'])

    if not found_any:
        st.info("No rewritten articles found yet. Go to 'Select & Rewrite' to process some!")