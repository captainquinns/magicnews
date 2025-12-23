import streamlit as st
import sys
import time
from datetime import date
from pathlib import Path

# --- IMPORT YOUR EXISTING LOGIC ---
from summarize_archive import (
    parse_article_file, 
    rewrite_with_ai, 
    rewritten_txt_path, 
    ArticleMetadata
)

# --- PAGE CONFIG ---
st.set_page_config(page_title="News Rewriter", layout="wide", page_icon="🗞️")

# --- POPUP DIALOG FUNCTION ---
@st.dialog("Original Article Text")
def show_file_content(file_path):
    """Opens a modal popup with the file contents."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        st.text_area("Raw Text", content, height=500, disabled=True)
    except Exception as e:
        st.error(f"Could not read file: {e}")

# --- HELPER FUNCTIONS ---
def get_original_files(root_path, target_date, site):
    path = root_path / str(target_date) / site / "Original"
    if not path.exists():
        return []
    
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
            
            files.append({
                "path": f, 
                "filename": f.name, 
                "title": title, 
                "url": url,
                "site": site
            })
        except Exception:
            continue
    return files

def get_rewritten_content(original_path_obj):
    out_path = rewritten_txt_path(original_path_obj)
    if out_path.exists():
        return out_path.read_text(encoding="utf-8", errors="ignore")
    return None

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

# --- SIDEBAR CONTROLS ---
st.sidebar.title("Controls")

default_path = str(Path("Stories").resolve())
root_input = st.sidebar.text_input("Archive Folder Path", value=default_path)
ROOT_DIR = Path(root_input).expanduser().resolve()

if not ROOT_DIR.exists():
    st.sidebar.error("⚠️ Folder not found!")

st.sidebar.divider()
selected_date = st.sidebar.date_input("Select Date", date.today())
st.sidebar.info(f"Looking in:\n{ROOT_DIR}\n\nFor date:\n{selected_date}")


# --- MAIN LAYOUT ---
tab1, tab2 = st.tabs(["📝 Select & Rewrite", "✅ Proof & Review"])
SITES = ["wmur", "wcax", "vtdigger", "mykeenenow"]

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
    
    if total_files_found > 0:
        for site, files in all_site_files.items():
            select_all_key = f"all_{site}"
            is_select_all = st.session_state.get(select_all_key, False)
            for f in files:
                chk_key = f"chk_{f['filename']}"
                if is_select_all or st.session_state.get(chk_key, False):
                    selected_files_to_process.append(f)

    # TOP ACTION BAR
    c_info, c_btn = st.columns([3, 1])
    with c_info:
        st.subheader(f"Found {total_files_found} articles for {selected_date}")
        if not total_files_found:
            st.warning("No articles found. Check your Folder Path or run the scraper.")
    
    with c_btn:
        count = len(selected_files_to_process)
        if st.button(f"🚀 Rewrite ({count})", type="primary", disabled=count==0, use_container_width=True):
            process_files(selected_files_to_process)

    st.divider()

    # RENDER FILE LISTS
    for site in SITES:
        if site not in all_site_files:
            continue
            
        files = all_site_files[site]
        st.markdown(f"### {site.upper()}")
        
        st.checkbox(f"Select All {site.upper()}", key=f"all_{site}")

        for f in files:
            # Layout: [Checkbox] [Link] [View Button]
            # We give the View Button a fixed small width
            c1, c2, c3 = st.columns([0.05, 0.85, 0.10])
            
            with c1:
                disabled_state = st.session_state.get(f"all_{site}", False)
                val = True if disabled_state else st.session_state.get(f"chk_{f['filename']}", False)
                st.checkbox("", value=val, key=f"chk_{f['filename']}", disabled=disabled_state, label_visibility="collapsed")
            
            with c2:
                if f['url']:
                    st.markdown(f"[{f['title']}]({f['url']})")
                else:
                    st.write(f"**{f['title']}**")
            
            with c3:
                # The Popup Button
                if st.button("📄", key=f"view_{f['filename']}", help="View scraped text"):
                    show_file_content(f['path'])
        
        st.divider()

# --- TAB 2: REVIEW ---
with tab2:
    st.header("Review Dashboard")
    
    found_any = False
    
    for site in SITES:
        files = get_original_files(ROOT_DIR, selected_date, site)
        
        rewritten_pairs = []
        for f in files:
            content = get_rewritten_content(f['path'])
            if content:
                rewritten_pairs.append((f, content))
        
        if rewritten_pairs:
            found_any = True
            st.markdown(f"### {site.upper()}")
            
            for meta, new_text in rewritten_pairs:
                with st.expander(f"✅ {meta['title']}", expanded=False):
                    
                    c_toggle, c_link = st.columns([1, 3])
                    with c_toggle:
                        show_orig = st.toggle("Compare with Original", key=f"swap_{meta['filename']}")
                    with c_link:
                        if meta['url']:
                            st.markdown(f"🔗 [Open Original Article]({meta['url']})")

                    st.divider()
                    
                    if show_orig:
                        orig_text = meta['path'].read_text(encoding="utf-8", errors="ignore")
                        st.warning(orig_text)
                    else:
                        st.success(new_text)

    if not found_any:
        st.info("No rewritten articles found yet.")