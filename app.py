import xml.etree.ElementTree as ET
import feedparser
from datetime import datetime, timedelta
import ssl
import os
from pathlib import Path
import pickle
import json
from bs4 import BeautifulSoup
import requests
from email.utils import parsedate_to_datetime  # pour parser dates RFC 2822 (RSS)
import logging
from urllib.parse import urljoin

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATA_OUTPUT = Path("./output")
DATA_OUTPUT.mkdir(parents=True, exist_ok=True)

LOG_FILE = f"{DATA_OUTPUT}/_app.log"

CACHE_FILE = './_rss_cache.pkl'

CANDIDATE_FEEDS = [
    "/feed/",
    "/atom.xml",
    "/rss.xml",
]

USING_CACHE = False


# Vider le log au démarrage
open(LOG_FILE, "w", encoding="utf-8").close()

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,  # passe à logging.DEBUG si tu veux plus de détails
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
    force=True,  # remplace toute config passée ailleurs
)
logger = logging.getLogger("rss_app")

os.system('clear')

# Session HTTP partagée, sans proxies système, avec en-têtes et timeouts par défaut
session = requests.Session()
session.trust_env = False  # ignore les proxies du système et variables d'env

DEFAULT_TIMEOUT = (5, 15)  # 5s pour se connecter, 15s pour lire la réponse
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Ignore SSL certificate verification
ssl._create_default_https_context = ssl._create_unverified_context


# Load cache from disk
def load_cache():
    try:
        with open(CACHE_FILE, 'rb') as f:
            return pickle.load(f)
    except (FileNotFoundError, EOFError):
        return {}

# Save cache to disk
def save_cache(cache):
    if USING_CACHE:
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump(cache, f)

def get_cache(entry):
    if USING_CACHE and entry in rss_cache:
        cached_time, cached_item = rss_cache[entry]
        if datetime.now() - cached_time < timedelta(days=1):
            logger.debug(f"Using cached for {entry}: {cached_item}")
            return cached_item
    return None

def in_cache(entry, value):
    if USING_CACHE and entry in rss_cache:
        rss_cache[entry] = (datetime.now(), value)
        save_cache(rss_cache)

def extract_entry_datetime(entry):
    # 1) Priorité aux champs parsés par feedparser
    if 'published_parsed' in entry and entry['published_parsed']:
        return datetime(*entry['published_parsed'][:6])
    if 'updated_parsed' in entry and entry['updated_parsed']:
        return datetime(*entry['updated_parsed'][:6])
    # 2) Fallback sur les chaînes si dispo (RSS/Atom variés)
    if 'published' in entry and entry['published']:
        try:
            return parsedate_to_datetime(entry['published']).replace(tzinfo=None)
        except Exception:
            pass
    if 'updated' in entry and entry['updated']:
        try:
            return parsedate_to_datetime(entry['updated']).replace(tzinfo=None)
        except Exception:
            pass
    return None


def try_candidate_feeds(base_url: str) -> str | None:
    for path in CANDIDATE_FEEDS:
        url = urljoin(base_url, path)
        try:
            resp = session.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=DEFAULT_TIMEOUT,
                allow_redirects=True,
            )
            # Attention à la priorité des "and/or"
            if resp.status_code == 200 and (b"<rss" in resp.content or b"<feed" in resp.content):
                logger.info(f"Candidate feed OK: {url}")
                return resp.url  # URL finale après redirection
        except Exception as e:
            logger.debug(f"Candidate fail {url}: {e}")
    return None

def get_rss_url_from_website(website_url):

    cached_rss_url = get_cache(website_url)
    if cached_rss_url:
        return cached_rss_url

    try:
        logger.info(f"GET {website_url}")
        response = session.get(
            website_url,
            headers=DEFAULT_HEADERS,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # 2) D’abord chercher via balise <link> standard
        rss_link = soup.find("link", type="application/rss+xml")
        atom_link = soup.find("link", type="application/atom+xml")

        found = None
        if rss_link and rss_link.get("href"):
            found = urljoin(website_url, rss_link["href"])
        elif atom_link and atom_link.get("href"):
            found = urljoin(website_url, atom_link["href"])

        # 3) Si pas trouvé, essayer les candidates
        if not found:
            found = try_candidate_feeds(website_url)

        if found:
            in_cache(website_url, found)
            logger.info(f"Found RSS/Atom for {website_url}: {found}")
            return found
        else:
            logger.warning(f"No RSS/Atom link found on {website_url}")
            return None

    except requests.Timeout:
        logger.warning(f"Timeout fetching website {website_url}")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching website {website_url}: {e}")
        return None    

def fetch_feed(rss_url):
    try:
        logger.info(f"fetch_feed {rss_url}")
        headers = DEFAULT_HEADERS 
        response = session.get(
            rss_url,
            headers=headers,
            allow_redirects=True,
            timeout=DEFAULT_TIMEOUT,
        )

        if 400 <= response.status_code < 600:
            logger.warning(f"HTTP {response.status_code} for {rss_url}")
            return {"bozo": 1, "http_status": response.status_code, "entries": []}

        logger.info(f"Reditect URL: {response.url}")
        # Parse the final URL content with feedparser
        feed = feedparser.parse(response.content)

        if feed:
            bozo = getattr(feed, 'bozo', None) if hasattr(feed, 'bozo') else feed.get('bozo', 0)
            entries = getattr(feed, 'entries', None) if hasattr(feed, 'entries') else feed.get('entries', [])
            http_status = feed.get('http_status') if isinstance(feed, dict) else None
            logger.info(f"bozo {bozo} http_status {http_status}")
            return bozo, entries, http_status

        return None

    except requests.Timeout:
        logger.warning(f"Timeout fetching the feed {rss_url}")
        return None
       
    except requests.RequestException as e:
        logger.error(f"Error fetching the feed: {e}")
        return None


def fetch_and_cache_feed(rss_url, web_url=None, mode=1):
    logger.info(f"fetch try 1 {rss_url}")
    bozo, entries, http_status = fetch_feed(rss_url)

    if not bozo and mode == 1:
        logger.warning(f"Feed error for {rss_url}")
        new_rss = get_rss_url_from_website(web_url)
        logger.info(f"New RSS URL from website {web_url}: {new_rss}")
        if new_rss and new_rss != rss_url:
            # Mettre à jour le cache de découverte (déjà fait dans get_rss_url_from_website)
            return fetch_and_cache_feed(new_rss, None, mode=2)  # relancer sur le nouveau flux

    exit()


    # Cas d'erreur: HTTP 404/410/403/... ou bozo sans entries
    if (http_status and http_status >= 400) or (bozo and not entries) or not bozo:
        logger.warning(f"Feed error for {rss_url} (status={http_status})")
        # Tenter de retrouver un flux depuis le site si web_url dispo
        if web_url:
            new_rss = get_rss_url_from_website(web_url)
            logger.info(f"New RSS URL from website {web_url}: {new_rss}")
            if new_rss and new_rss != rss_url:
                # Mettre à jour le cache de découverte (déjà fait dans get_rss_url_from_website)
                return fetch_and_cache_feed(new_rss, None)  # relancer sur le nouveau flux

        # Échec final: stocker une marque d'échec pour éviter retry incessant
        failure_payload = json.dumps({
            "error": "not_found" if http_status == 404 else "fetch_error",
            "status": http_status or 0,
            "entries": []
        })
        in_cache( rss_url, failure_payload)
        return {"entries": []}

    # Cas OK: normaliser et cacher
    feed_data = {
        'entries': [
            {
                'title': getattr(entry, 'title', None),
                'link': getattr(entry, 'link', None),
                'published': getattr(entry, 'published', None),
                'published_parsed': getattr(entry, 'published_parsed', None),
                'updated': getattr(entry, 'updated', None),
                'updated_parsed': getattr(entry, 'updated_parsed', None),
            }
            for entry in feed.entries
        ]
    }
    feed_json = json.dumps(feed_data)
    in_cache(rss_url, feed_json)
    return feed_data


def read_opml(file_path):
    """Read and parse the OPML file."""
    tree = ET.parse(file_path)
    return tree.getroot()


def sort_rss(categories):
    """Sort the feeds in each category by update frequency, with active sites first.
       En cas d'égalité, tri alphabétique par titre.
    """
    for category_title, feeds in categories.items():
        categories[category_title] = sorted(
            feeds,
            key=lambda feed: (
                feed[2] == -1 or feed[2] == 0,                  # sites morts/aucun update en dernier
                feed[2] if isinstance(feed[2], (int, float)) else float('inf'),
                feed[0].casefold()                               # titre pour départager
            )
        )

def write_markdown(categories, file_path):
    """Write the categories and feeds to a Markdown file."""
    # Calculer le total de sites
    total_sites = sum(len(feeds) for feeds in categories.values())
    # Date du jour en JJ/MM/AAAA
    today_str = datetime.now().strftime("%d/%m/%Y")

    with open(file_path, 'w', encoding='utf-8') as md_file:

        md_file.write(
            f"Les {total_sites} sites suivis sur [Feedly](https://feedly.com/) au {today_str} "
            f"(liste mise en forme avec [Feedly-OPML-markdown](https://github.com/tcrouzet/Feedly-OPML-markdown))\n\n"
        )

        for category_title in sorted(categories.keys(), key=str.casefold):
            feeds = categories[category_title]
            md_file.write(f"### {category_title}\n\n")
            for title, html_url, stats in feeds:
                md_file.write(f"- [{title}]({html_url}) {format_stats(stats)}\n")
            md_file.write("\n")

def parse_opml_to_categories(root):
    """Parse the OPML root element into a dictionary of categories."""
    categories = {}
    for category in root.findall('.//outline[@text]'):
        category_title = category.get('title')
        logger.info(category_title)

        feeds = []
        for outline in category.findall('outline'):
            title = outline.get('title')
            html_url = outline.get('htmlUrl')
            xml_url = outline.get('xmlUrl')
            if title and html_url and xml_url:
                logger.info(f"Processing RSS feed: {xml_url}")
                stats = rss_stats(xml_url, html_url)
                logger.info(f"Stats: {stats}")
                feeds.append((title, html_url, stats))
        
        if category_title and feeds:
            categories[category_title] = feeds
    return categories


def feed_parser(rss_url, html_url):
    """Parse the RSS feed and return the feed object."""

    logger.info(f"Parsing feed {rss_url}, {html_url}")

    try:
        # Check if the URL is in the cache and if it's still valid

        cached_feed_json = get_cache(rss_url)
        if cached_feed_json:
            # Use cached feed
            feed = json.loads(cached_feed_json)
            logger.info(f"Using cached feed for {rss_url}")
        else:
            # Fetch new feed
            logger.info(f"Fetching new feed {rss_url}")
            feed = fetch_and_cache_feed(rss_url, html_url)

        return feed

    except Exception as e:
        logger.exception(f"Feed_parser error: {e}")
        return None

def rss_stats(rss_url, html_url):
    feed = feed_parser(rss_url, html_url)
    if not feed:
        return -1

    dates = []
    for entry in feed.get('entries', []):
        dt = extract_entry_datetime(entry)
        if dt:
            dates.append(dt)

    logger.info(f"Extracted {len(dates)} dates")
    if len(dates) > 1:
        dates.sort(reverse=True)
        intervals = [(dates[i] - dates[i + 1]).total_seconds() for i in range(len(dates) - 1)]
        return int(sum(intervals) / len(intervals))
    elif len(dates) == 1:
        return 1  # fréquence inconnue mais actif: valeur minimale
    else:
        return 0  # pas d'actualisation identifiable
    

def format_stats(index):
    """Format the update index into a readable string."""
    if index == -1:
        return "Site mort"
    elif index == 0:
        return "Pas d'actualisation"
    elif index == 1:
        return "Un seul article dans le feed"
    
    # Convert seconds to days
    days = index / (24 * 3600)
    
    if days < 1:
        # More than one publication per day
        return f"{round(1 / days)} fois par jour"
    elif days < 7:
        # Publications per week
        return f"{round(7 / days)} fois par semaine"
    elif days < 30:
        # Publications per month
        return f"{round(30 / days)} fois par mois"
    elif days < 365:
        # Publications per year
        return f"{round(365 / days)} fois par an"
    else:
        # Publications per decade
        return f"{round(3650 / days)} fois par décennie"    

def opml_to_markdown(opml_file_path, markdown_file_path):
    """Convert OPML file to Markdown format."""
    root = read_opml(opml_file_path)
    categories = parse_opml_to_categories(root)
    logger.info("Sorting…")
    sort_rss(categories)
    write_markdown(categories, markdown_file_path)


# Convert gmi text links to OPML
def gmi_to_opml(input_file, output_file):
    """Convert a text file with RSS feeds to OPML format."""
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    opml_content = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="1.0">', '<head>', '<title>RSS Feeds</title>', '</head>', '<body>']

    current_category = None

    for line in lines:
        line = line.strip()
        if line.startswith('##'):
            # New category
            current_category = line[2:].strip()
            opml_content.append(f'<outline text="{current_category}" title="{current_category}">')
        elif line.startswith('=>'):
            # New feed
            parts = line.split(' ', 2)
            if len(parts) >= 2:
                url = parts[1].strip()
                title = parts[2].strip() if len(parts) > 2 else url
                opml_content.append(f'<outline type="rss" text="{title}" title="{title}" xmlUrl="{url}" htmlUrl="{url}"/>')

    # Close the last category
    if current_category:
        opml_content.append('</outline>')

    opml_content.append('</body>')
    opml_content.append('</opml>')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(opml_content))


if __name__ == "__main__":

    # Initialize cache
    rss_cache = load_cache()

    if True:

        TEST_RSS = "http://prollyisnotprobably.com/atom.xml"
        TEST_HTML = "https://theradavist.com"

        logger.info("=== TEST ===")

        # print(get_rss_url_from_website(TEST_HTML))
        # exit()

        feed = feed_parser(TEST_RSS, TEST_HTML)
        if not feed:
            print("Feed None")
        else:
            print(f"Nb entries: {len(feed.get('entries', []))}")
            # Afficher les 5 premières entrées avec leurs champs de date
            for i, e in enumerate(feed.get('entries', [])[:5]):
                print(f"- Entry {i+1}:")
                print("  title:", e.get("title"))
                print("  published:", e.get("published"))
                print("  published_parsed:", e.get("published_parsed"))
                print("  updated:", e.get("updated"))
                print("  updated_parsed:", e.get("updated_parsed"))

            # Calculer les stats avec le nouvel extracteur
            s = rss_stats(TEST_RSS, TEST_HTML)
            print("Stats (seconds avg interval):", s)
        exit()

    opml_file_path = f'{DATA_DIR}/feedly.opml'
    markdown_file_path = f'{DATA_OUTPUT}/output.md'
    opml_to_markdown(opml_file_path, markdown_file_path)