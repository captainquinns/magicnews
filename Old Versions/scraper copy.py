import argparse
import logging
import sys
from datetime import datetime, date
from scrapers import AVAILABLE_SCRAPERS, save_articles

# Setup logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Main")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape local news sites into Stories/<date>/<site>/Original"
    )
    
    site_choices = list(AVAILABLE_SCRAPERS.keys()) + ["all"]
    
    parser.add_argument(
        "--site",
        choices=site_choices,
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

    # 1. Parse Date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid --date format. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = date.today()

    # 2. Determine Sites to Run
    if args.site == "all":
        sites_to_run = list(AVAILABLE_SCRAPERS.keys())
    else:
        sites_to_run = [args.site]

    logger.info(f"Target date: {target_date}")
    logger.info(f"Sites to scrape: {', '.join(sites_to_run)}")

    # 3. Run Scrapers
    for site_slug in sites_to_run:
        logger.info(f"\n=== Starting Scrape: {site_slug} ===")
        scrape_func = AVAILABLE_SCRAPERS[site_slug]
        
        try:
            # Delegate to the specific module
            articles = scrape_func(target_date)
            
            # Delegate saving to the base utility
            save_articles(site_slug, target_date, articles)
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR scraping {site_slug}: {e}", exc_info=True)
            # We continue to the next site instead of crashing the whole process
            continue

    logger.info("\n=== All Tasks Complete ===")

if __name__ == "__main__":
    main()