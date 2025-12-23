from .wmur import scrape as scrape_wmur
from .wcax import scrape as scrape_wcax
from .vtdigger import scrape as scrape_vtdigger
from .mykeenenow import scrape as scrape_mykeenenow
from .base import save_articles
from .keenesentinel import scrape as scrape_keenesentinel
from .reformer import scrape as scrape_reformer

# Registry of available scrapers
# Keys = command line argument names
# Values = the scrape function to call
AVAILABLE_SCRAPERS = {
    "wmur": scrape_wmur,
    "wcax": scrape_wcax,
    "vtdigger": scrape_vtdigger,
    "mykeenenow": scrape_mykeenenow,
    "keenesentinel": scrape_keenesentinel,
    "reformer": scrape_reformer,
}