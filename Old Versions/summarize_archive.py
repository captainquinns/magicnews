#!/usr/bin/env python3
import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, List, Tuple

from openai import OpenAI


# ====== CONFIG DEFAULTS ======

# New default root layout:
# /Users/.../NewsArchive/Stories/<YYYY-MM-DD>/<site>/Original/<TITLE>.md
DEFAULT_ARCHIVE_ROOT = Path("Stories")

# Allowed input article extensions
ARTICLE_EXTENSIONS = {".md", ".txt"}

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# OpenAI client – expects OPENAI_API_KEY in env
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# ====== DATA MODELS ======

@dataclass
class ArticleMetadata:
    site_id: str
    date_str: str          # YYYY-MM-DD from folder
    article_path: str      # relative to root
    title: Optional[str]
    url: Optional[str]
    published_date: Optional[str]  # if parsed from file
    scraped_at: Optional[str]      # if present in file


# ====== FILE DISCOVERY ======

def discover_article_files(root: Path) -> List[Path]:
    """
    Recursively find all article files under the root that match ARTICLE_EXTENSIONS.

    IMPORTANT:
    - Skips anything inside a 'Rewritten' directory so we never rewrite our own output.
    """
    if not root.exists():
        logging.error(f"Archive root does not exist: {root}")
        return []

    files: List[Path] = []
    for ext in ARTICLE_EXTENSIONS:
        files.extend(root.rglob(f"*{ext}"))

    # Only real files, and skip anything in a Rewritten folder
    files = [
        f for f in files
        if f.is_file() and "Rewritten" not in f.parts
    ]

    logging.info(f"Discovered {len(files)} candidate article files under {root}")
    return sorted(files)


def parse_site_and_date_from_path(root: Path, file_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Infer (site_id, date_str) from the file path relative to root.

    Supports two layouts:

      1) Legacy archive layout:
           root/<site>/<YYYY-MM-DD>/file.ext

      2) New Stories layout:
           root/<YYYY-MM-DD>/<site>/Original/file.ext
           root/<YYYY-MM-DD>/<site>/Rewritten/file.ext
    """
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return None, None

    parts = rel.parts
    if len(parts) < 2:
        return None, None

    # Pattern 1: <site>/<YYYY-MM-DD>/...
    site_candidate = parts[0]
    if len(parts) >= 2:
        second = parts[1]
        try:
            _ = date.fromisoformat(second)
            return site_candidate, second
        except ValueError:
            pass

    # Pattern 2: <YYYY-MM-DD>/<site>/...
    first = parts[0]
    if len(parts) >= 2:
        second = parts[1]
        try:
            _ = date.fromisoformat(first)
            return second, first
        except ValueError:
            pass

    return None, None


# ====== ARTICLE PARSING (TITLE / PUBLISHED / BODY) ======

def parse_article_file(path: Path) -> Tuple[ArticleMetadata, str]:
    """
    Read a single article file, return (metadata, body_text).

    Assumes a simple Markdown-like format (like the WMUR scraper emits):
      - First line starting with '# ' is the title
      - Lines containing 'URL:' / 'Published:' / 'Scraped at:' are metadata
      - Everything else is body text
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logging.error(f"Failed to read {path}: {e}")
        raise

    lines = text.splitlines()

    title: Optional[str] = None
    url: Optional[str] = None
    published_date: Optional[str] = None
    scraped_at: Optional[str] = None
    body_lines: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Title
        if stripped.startswith("# ") and title is None:
            title = stripped[2:].strip()
            continue

        lower = stripped.lower()

        # URL
        if lower.startswith("url:"):
            url = stripped.split(":", 1)[-1].strip()
            continue
        if lower.startswith("- **url:**"):
            # e.g. "- **URL:** https://..."
            url = stripped.split("**url:**", 1)[-1].strip()
            continue

        # Published date
        if lower.startswith("published:"):
            published_date = stripped.split(":", 1)[-1].strip()
            continue
        if lower.startswith("- **published:**"):
            published_date = stripped.split("**published:**", 1)[-1].strip()
            continue

        # Scraped at
        if lower.startswith("scraped at:"):
            scraped_at = stripped.split(":", 1)[-1].strip()
            continue
        if lower.startswith("- **scraped at:**"):
            scraped_at = stripped.split("**scraped at:**", 1)[-1].strip()
            continue

        # Skip obvious separators
        if stripped.startswith("---"):
            continue

        body_lines.append(line)

    body_text = "\n".join(body_lines).strip()

    meta = ArticleMetadata(
        site_id="",
        date_str="",
        article_path="",
        title=title,
        url=url,
        published_date=published_date,
        scraped_at=scraped_at,
    )

    return meta, body_text


# ====== AI CALL (REWRITE) ======

def _call_openai(prompt: str, model: str = "gpt-4o-mini") -> str:
    """
    Low-level OpenAI call using the Responses API. Returns plain text.
    """
    if not client.api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in the environment.")

    resp = client.responses.create(
        model=model,
        instructions=(
            "You are an experienced news editor who rewrites stories in clear, "
            "original language without copying phrasing."
        ),
        input=prompt,
        max_output_tokens=1500,  # safety cap on length
    )

    # New OpenAI Responses API exposes a convenience .output_text
    return resp.output_text.strip()  # type: ignore[attr-defined]


def rewrite_with_ai(article_text: str, title: Optional[str] = None) -> Tuple[str, str]:
    """
    Call the AI model to produce a FULLY REWRITTEN VERSION of the article.

    Returns:
      - rewritten_article (string) → first line = rewritten headline, blank line, then story body
      - model_name        (string)
    """
    model_name = "gpt-4o-mini"

    prompt = f"""
You are rewriting a local news article so that it is textually distinct from the original.

Your job:
- Rewrite the article COMPLETELY in your own words.
- Do NOT copy any full sentences or distinctive phrases from the original.
- Do NOT use quotation marks at all. No direct quotes, even short ones.
- Any speech or statements should be converted into indirect speech (for example: he said she was struggling, instead of quoting exact words).
- You MAY keep proper nouns, names, places, dates, and numbers the same, but the surrounding wording and sentence structure must be different.
- Vary sentence structure and vocabulary so it reads like someone else wrote the story from scratch based on the same facts.
- Match roughly the same level of detail and length as the original article.

Output format:
- First line: a strong rewritten headline for the story.
- Then a blank line.
- Then the full rewritten article body.
- Do NOT add any labels, section headings, or commentary.

Original article title: {title or "N/A"}

Original article text:
\"\"\"{article_text[:12000]}\"\"\"
""".strip()

    rewritten = _call_openai(prompt=prompt, model=model_name).strip()

    # Nuke any quotation marks the model might still include
    for ch in ['"', "“", "”", "‘", "’"]:
        rewritten = rewritten.replace(ch, "")

    return rewritten, model_name


# ====== OUTPUT PATH LOGIC ======

def rewritten_txt_path(article_path: Path) -> Path:
    """
    Given an article file path, return where the rewritten .txt should go.

    New Stories layout (preferred):
      root/<YYYY-MM-DD>/<site>/Original/<title>.ext
        -> root/<YYYY-MM-DD>/<site>/Rewritten/<title>.txt

    Legacy layout (no 'Original' folder):
      /path/to/article.ext -> /path/to/article.ext.rewritten.txt
    """
    parts = article_path.parts

    if "Original" in parts:
        original_dir = article_path.parent          # .../Original
        site_dir = original_dir.parent             # .../<site>
        rewritten_dir = site_dir / "Rewritten"
        out_name = article_path.stem + ".txt"      # force plain .txt
        return rewritten_dir / out_name

    # Fallback: old behavior
    return article_path.with_suffix(article_path.suffix + ".rewritten.txt")


# ====== MAIN PROCESSING ======

def process_articles(
    root: Path,
    site_filter: Optional[str],
    date_filter: Optional[str],
    force: bool = False,
    limit: Optional[int] = None,
) -> None:
    """
    Walk the archive, filter by site/date, and rewrite articles.
    """
    all_files = discover_article_files(root)
    processed = 0
    rewritten_count = 0
    skipped_existing = 0
    skipped_filtered = 0
    errors = 0

    for article_path in all_files:
        processed += 1

        site_id, date_str = parse_site_and_date_from_path(root, article_path)
        if site_id is None or date_str is None:
            skipped_filtered += 1
            continue

        # Apply CLI filters
        if site_filter and site_id != site_filter:
            skipped_filtered += 1
            continue
        if date_filter and date_str != date_filter:
            skipped_filtered += 1
            continue

        rel_path = article_path.relative_to(root)
        out_path = rewritten_txt_path(article_path)

        if out_path.exists() and not force:
            logging.info(f"[SKIP existing] {rel_path}")
            skipped_existing += 1
            continue

        logging.info(f"[PROCESS] {rel_path} (site={site_id}, date={date_str})")

        # Parse article file
        try:
            meta, body_text = parse_article_file(article_path)
        except Exception:
            errors += 1
            continue

        if not body_text:
            logging.warning(f"No body text found in {rel_path}, skipping.")
            errors += 1
            continue

        # Fill in metadata fields from path
        meta.site_id = site_id
        meta.date_str = date_str
        meta.article_path = str(rel_path)

        # AI rewrite
        try:
            rewritten_article, model_name = rewrite_with_ai(
                article_text=body_text,
                title=meta.title,
            )
            logging.debug(f"Model used: {model_name}")
        except Exception as e:
            logging.error(f"AI rewrite failed for {rel_path}: {e}")
            errors += 1
            continue

        # Write a simple .txt file containing ONLY the rewritten title + story
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as f:
                f.write(rewritten_article)
                f.write("\n")
            logging.info(f"[WRITE] {out_path.relative_to(root)}")
            rewritten_count += 1
        except Exception as e:
            logging.error(f"Failed to write rewritten file for {rel_path}: {e}")
            errors += 1

        if limit is not None and rewritten_count >= limit:
            logging.info(f"Hit rewrite limit ({limit}), stopping.")
            break

    logging.info("==== RUN COMPLETE ====")
    logging.info(f"Processed files:     {processed}")
    logging.info(f"Rewritten:           {rewritten_count}")
    logging.info(f"Skipped existing:    {skipped_existing}")
    logging.info(f"Skipped (filtered):  {skipped_filtered}")
    logging.info(f"Errors:              {errors}")


# ====== CLI ENTRYPOINT ======

def main():
    parser = argparse.ArgumentParser(
        description="Rewrite local news article files using an AI model."
    )
    parser.add_argument(
        "--root",
        type=str,
        default=str(DEFAULT_ARCHIVE_ROOT),
        help="Root archive directory (default: ./Stories)",
    )
    parser.add_argument(
        "--site",
        type=str,
        default=None,
        help="Only process articles for this site_id (e.g. 'wmur').",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Only process articles for this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing rewritten files instead of skipping them.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of new rewrites to create this run.",
    )

    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    site_filter = args.site
    date_filter = args.date
    force = args.force
    limit = args.limit

    process_articles(
        root=root,
        site_filter=site_filter,
        date_filter=date_filter,
        force=force,
        limit=limit,
    )


if __name__ == "__main__":
    main()
