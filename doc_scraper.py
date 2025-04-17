# --- Standard Libraries ---
import requests
from bs4 import BeautifulSoup, NavigableString, Tag # Added Tag
import json
from urllib.parse import urljoin, urlparse, urlunparse
from urllib import robotparser
import time
import datetime
import io
import re
import logging
import os
import argparse
import sys
import math
import mimetypes

# --- Dependencies need installation ---
# CORE: pip install requests beautifulsoup4
# PDF Parsing: pip install PyPDF2 pdfminer.six
# DOCX Parsing: pip install python-docx
# Tabular Data (CSV/Excel): pip install pandas openpyxl
# DYNAMIC CONTENT (Optional): pip install selenium playwright webdriver-manager
#   + Playwright browsers: run `playwright install` in terminal after pip install
#   + Selenium WebDriver: Ensure chromedriver/geckodriver is in PATH or managed by webdriver-manager

# --- Optional Dependency Handling & Imports ---
PDFMINER_AVAILABLE = False
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
    PDFMINER_AVAILABLE = True
except ImportError:
    pass # Will log warning later

PYPDF2_AVAILABLE = False
try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    pass # Will log warning later

PANDAS_AVAILABLE = False
OPENPYXL_AVAILABLE = False
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
    try:
        import openpyxl
        OPENPYXL_AVAILABLE = True
    except ImportError:
        pass # Will log warning later
except ImportError:
    pass # Will log warning later

DOCX_AVAILABLE = False
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    pass # Will log warning later

# --- Dynamic Content Libs (Optional) ---
SELENIUM_AVAILABLE = False
WEBDRIVER_MANAGER_AVAILABLE = False # webdriver-manager helps manage drivers for selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService # Example for Chrome
    # You might need different Service objects for other browsers (e.g., FirefoxService)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        # from webdriver_manager.firefox import GeckoDriverManager # Example for Firefox
        WEBDRIVER_MANAGER_AVAILABLE = True
    except ImportError:
        # Log later that webdriver-manager is recommended if Selenium is used without it
        pass
    SELENIUM_AVAILABLE = True
except ImportError:
    # Log later if Selenium fallback is enabled but lib is missing
    pass

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    # Log later if Playwright fallback is enabled but lib is missing
    pass


# --- Configuration ---
USER_AGENT = 'MyCodingAgentScraper/2.1 (+http://your-website-or-contact.com/bot-info)'
REQUEST_DELAY_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 25 # Timeout for standard requests
DYNAMIC_FETCH_TIMEOUT_SECONDS = 60 # Longer timeout for browser automation
BASE_OUTPUT_DIR = "scraped_docs"

# --- Selectors for finding the main content block(s) in HTML ---
# IMPORTANT: These are EXAMPLES and MUST be customized per target website
MAIN_CONTENT_SELECTORS = [
    'article', '[role="main"]', 'main', '.main-content', '#content',
    '.entry-content', '.post-content', '#main-content',
]
# --- Selectors for identifying section headings within main content ---
# Script will try to group content under these headings. Customize as needed.
SECTION_HEADING_SELECTORS = ['h2', 'h3'] # Look for H2s, then H3s within H2s etc.

# --- Selectors/Patterns for identifying supporting document links ---
# Customize these based on the target site structure
SUPPORTING_LINK_SELECTORS = [
    'a[href$=".pdf"]', 'a[href$=".docx"]', 'a[href$=".csv"]', 'a[href$=".xlsx"]', 'a[href$=".txt"]', # Direct file links
    '.downloads a', '#attachments a', '.references a', '.related-documents a' # Links within specific sections
]
ALLOWED_SUPPORTING_DOC_EXTENSIONS = ['.pdf', '.docx', '.csv', '.xlsx', '.txt', '.html', '.htm']

# --- Dynamic Content Fallback Configuration ---
# Set ONE of these to True if you want dynamic fallback. Playwright is often easier.
USE_SELENIUM_FALLBACK = False
USE_PLAYWRIGHT_FALLBACK = True # Recommended if installed

# If initial HTML fetch gets less content than this, try dynamic fallback (if enabled)
MIN_HTML_CONTENT_LENGTH = 500
# Wait time for dynamic content to load in milliseconds (Playwright) or seconds (Selenium)
DYNAMIC_WAIT_TIME = 7 # Seconds (adjust as needed)

# Content Chunking Parameters (Applied PER SECTION if sectioning is successful)
CHAR_LIMIT = 35000
LINE_LIMIT = 500
CHUNK_OVERLAP_CHARS = 200

# --- Ethical Scraping Reminder ---
# ALWAYS check the website's 'robots.txt' file AND Terms of Service. Respect rules.

# --- Dynamic Content Note ---
# Fallbacks using Selenium/Playwright are included but require separate setup.


# --- Helper Functions ---

def setup_logging(log_file_path):
    """Configures logging to file and console."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    try:
        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Error setting up file logger at {log_file_path}: {e}", file=sys.stderr)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("webdriver_manager").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)

    log_lib_availability() # Log lib status after logger is ready

def log_lib_availability():
    """Logs the status of optional libraries."""
    # PDF
    if PDFMINER_AVAILABLE: logging.info("pdfminer.six found, will be used for PDF extraction.")
    elif PYPDF2_AVAILABLE: logging.info("pdfminer.six not found. Found PyPDF2 as fallback for PDF extraction.")
    else: logging.warning("Neither pdfminer.six nor PyPDF2 found. PDF parsing will be skipped.")
    # Tabular
    if PANDAS_AVAILABLE:
        logging.info("Pandas found, will be used for CSV/Excel extraction.")
        if OPENPYXL_AVAILABLE: logging.info("openpyxl found, enabling Pandas .xlsx support.")
        else: logging.warning("openpyxl not found. Pandas cannot read .xlsx files without it.")
    else: logging.warning("Pandas not found. CSV/Excel parsing will use basic methods or be skipped.")
    # DOCX
    if DOCX_AVAILABLE: logging.info("python-docx found, will be used for DOCX extraction.")
    else: logging.warning("python-docx not found. DOCX parsing will be skipped.")
    # Dynamic Fetching
    if USE_SELENIUM_FALLBACK:
        if SELENIUM_AVAILABLE:
            logging.info("Selenium fallback enabled and library found.")
            if not WEBDRIVER_MANAGER_AVAILABLE:
                logging.warning("webdriver-manager not found. Ensure WebDriver (e.g., chromedriver) is in PATH or specify its path manually in fetch_page_source_selenium.")
        else:
            logging.error("Selenium fallback enabled in config, but selenium library not found. Install with: pip install selenium webdriver-manager")
    if USE_PLAYWRIGHT_FALLBACK:
        if PLAYWRIGHT_AVAILABLE:
             logging.info("Playwright fallback enabled and library found. Ensure browsers are installed (`playwright install`).")
        else:
             logging.error("Playwright fallback enabled in config, but playwright library not found. Install with: pip install playwright && playwright install")

def get_robot_parser(start_url):
    """Fetches and parses the robots.txt file for the site."""
    parsed_uri = urlparse(start_url)
    robots_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/robots.txt"
    logging.info(f"Attempting to fetch robots.txt from: {robots_url}")

    rp = robotparser.RobotFileParser()
    rp.set_timeout(REQUEST_TIMEOUT_SECONDS)
    rp.set_url(robots_url)
    try:
        rp.read()
        if not rp.mtime():
             logging.warning(f"Failed to read or parse robots.txt from {robots_url} (check network/permissions or if file exists). Assuming allowed.")
             rp.allow_all = True
             rp.disallow_all = False
        logging.info(f"Finished processing robots.txt request for {parsed_uri.netloc}. Rules will be applied.")
        return rp
    except Exception as e:
        logging.error(f"Unexpected error reading robots.txt from {robots_url}: {e}. Assuming allowed.")
        rp.allow_all = True
        rp.disallow_all = False
        return rp


def can_fetch_url(robot_parser, url):
    """Checks if the URL is allowed by robots.txt for our User-Agent."""
    if robot_parser is None:
        logging.warning(f"No robots.txt parser available, proceeding cautiously for {url}")
        return True
    try:
        # Ensure URL is properly escaped before passing to can_fetch
        from urllib.parse import quote
        parsed_url = urlparse(url)
        # Quote the path and query if they exist
        path_quoted = quote(parsed_url.path) if parsed_url.path else '/'
        query_quoted = quote(parsed_url.query) if parsed_url.query else ''
        # Reconstruct a minimal URL suitable for can_fetch (scheme, netloc, path, query)
        check_url = urlunparse(('', '', path_quoted, '', query_quoted, ''))

        allowed = robot_parser.can_fetch(USER_AGENT, check_url)
        if not allowed:
            logging.warning(f"Access disallowed by robots.txt: {url}")
        return allowed
    except Exception as e:
        logging.error(f"Error during robots.txt check for {url}: {e}. Assuming allowed.")
        return True


def fetch_url(url, robot_parser, stream=False):
    """Fetches content from a URL using requests, checking robots.txt first."""
    if not can_fetch_url(robot_parser, url):
        return "ROBOTS_DISALLOWED"

    logging.info(f"Fetching (requests): {url}")
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS, stream=stream)
        response.raise_for_status()
        logging.info(f"Successfully fetched (requests): {url} (Status: {response.status_code})")
        time.sleep(REQUEST_DELAY_SECONDS)
        return response
    except requests.exceptions.Timeout:
        logging.error(f"Timeout error fetching {url} after {REQUEST_TIMEOUT_SECONDS} seconds (requests).")
        return "FETCH_TIMEOUT"
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error fetching {url} (requests): {e}")
        return "FETCH_ERROR"


def make_absolute_url(base_url, link):
    """Converts a relative link to an absolute URL."""
    try:
        abs_url = urljoin(base_url, link.strip())
        parsed_abs = urlparse(abs_url)
        if parsed_abs.scheme in ['http', 'https']:
            return abs_url
        else:
            logging.warning(f"Generated URL has invalid scheme: {abs_url} (from base: {base_url}, link: {link})")
            return None
    except ValueError as e:
        logging.warning(f"Could not join base '{base_url}' with link '{link}': {e}")
        return None

def get_file_extension(url):
    """Extracts the file extension from a URL path."""
    if not url: return None
    try:
        path = urlparse(url).path
        if '.' in os.path.basename(path):
            return os.path.splitext(path)[1].lower()
        return None
    except Exception as e:
        logging.warning(f"Could not parse URL/get extension for '{url}': {e}")
        return None

def sanitize_filename(name, allow_slash=False):
    """Removes or replaces characters illegal in filenames/paths."""
    if not isinstance(name, str): name = str(name) # Ensure string
    name = re.sub(r'^https?:\/\/', '', name)
    if allow_slash:
        name = re.sub(r'[\\*?:"<>|]', '_', name)
    else:
         name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('_./\\')
    return name[:80]

def save_json(data, filepath):
    """Saves data to a JSON file with UTF-8 encoding."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Saved JSON: {filepath}")
    except IOError as e:
        logging.error(f"IOError writing JSON to {filepath}: {e}")
    except TypeError as e:
         logging.error(f"TypeError (data not JSON serializable) for {filepath}: {e}")
    except Exception as e:
         logging.error(f"Unexpected error saving JSON to {filepath}: {e}")

# --- Dynamic Content Fetching Functions (Additions) ---
def fetch_page_source_selenium(url, wait_time=DYNAMIC_WAIT_TIME):
    """Uses Selenium to fetch page source after JavaScript execution."""
    if not SELENIUM_AVAILABLE:
        logging.error("Selenium fallback called, but Selenium is not available.")
        return None

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={USER_AGENT}")

    driver = None
    try:
        if WEBDRIVER_MANAGER_AVAILABLE:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        else:
            logging.warning("webdriver-manager not found. Attempting to use WebDriver from PATH.")
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(DYNAMIC_FETCH_TIMEOUT_SECONDS)
        logging.info(f"Fetching with Selenium: {url}")
        driver.get(url)
        logging.info(f"Waiting {wait_time}s for dynamic content (Selenium)...")
        time.sleep(wait_time)
        page_source = driver.page_source
        logging.info(f"Successfully fetched dynamic source (Selenium) for: {url}")
        return page_source
    except Exception as e:
        logging.error(f"Selenium failed to fetch {url}: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def fetch_page_source_playwright(url, wait_time_ms=DYNAMIC_WAIT_TIME * 1000):
     """Uses Playwright to fetch page source after JavaScript execution."""
     if not PLAYWRIGHT_AVAILABLE:
         logging.error("Playwright fallback called, but Playwright is not available.")
         return None

     page_source = None
     pw = None; browser = None # Initialize outside try
     try:
         pw = sync_playwright().start()
         browser = pw.chromium.launch(headless=True)
         context = browser.new_context(user_agent=USER_AGENT)
         page = context.new_page()
         logging.info(f"Fetching with Playwright: {url}")
         page.goto(url, timeout=DYNAMIC_FETCH_TIMEOUT_SECONDS * 1000, wait_until='domcontentloaded')
         logging.info(f"Waiting {wait_time_ms}ms for dynamic content (Playwright)...")
         page.wait_for_timeout(wait_time_ms)
         page_source = page.content()
         logging.info(f"Successfully fetched dynamic source (Playwright) for: {url}")
         browser.close()
         pw.stop()
         return page_source
     except Exception as e:
         logging.error(f"Playwright failed to fetch {url}: {e}")
         if browser: browser.close() # Ensure browser is closed on error
         if pw: pw.stop() # Ensure Playwright process is stopped
         return None
# --- End of Dynamic Content Fetching Additions ---


# --- Content Extraction Functions ---

# ADDED this function definition back:
def extract_html_content(soup, selectors_list):
    """Extracts text content from specific parts of an HTML page (soup object), trying multiple selectors."""
    content_parts = []
    found_content = False
    for selector in selectors_list:
        try:
            elements = soup.select(selector)
            if elements:
                found_content = True
                for element in elements:
                    paragraphs = [p.strip() for p in element.get_text(separator='\n', strip=True).splitlines() if p.strip()]
                    text = '\n'.join(paragraphs)
                    content_parts.append(text)
                logging.info(f"Extracted HTML content using selector: '{selector}'")
        except Exception as e:
            logging.warning(f"Error applying HTML selector '{selector}': {e}")
            continue

    if content_parts:
        return "\n\n".join(content_parts)
    elif soup.body:
        logging.warning("No specific HTML content selectors matched. Falling back to extracting all text from body.")
        body_text = soup.body.get_text(separator='\n', strip=True)
        paragraphs = [p.strip() for p in body_text.splitlines() if p.strip()]
        return '\n'.join(paragraphs)
    else:
        logging.warning("No specific HTML content selectors matched and no <body> tag found.")
        return ""

def extract_html_metadata(soup):
    """Extracts metadata (title, meta tags) from HTML soup."""
    metadata = {}
    try:
        title_tag = soup.find('title')
        metadata['title'] = title_tag.string.strip() if title_tag and title_tag.string else None
    except Exception as e: logging.warning(f"Error extracting title: {e}"); metadata['title'] = None
    meta_tags_to_extract = { 'description': 'description', 'keywords': 'keywords', 'author': 'author', 'og_title': 'og:title', 'og_description': 'og:description', 'og_type': 'og:type', 'og_url': 'og:url', 'og_site_name': 'og:site_name' }
    for key, name_or_prop in meta_tags_to_extract.items():
        try:
            if ':' in name_or_prop: tag = soup.find('meta', property=name_or_prop)
            else: tag = soup.find('meta', attrs={'name': name_or_prop})
            if tag and tag.get('content'): metadata[key] = tag['content'].strip()
            else: metadata[key] = None
        except Exception as e: logging.warning(f"Error extracting meta tag '{name_or_prop}': {e}"); metadata[key] = None
    return {k: v for k, v in metadata.items() if v}


def extract_sections_from_html(soup, main_selectors, heading_selectors):
    """Attempts to extract content structured by sections based on heading tags."""
    main_content_element = None
    for selector in main_selectors:
        try:
            main_content_element = soup.select_one(selector)
            if main_content_element:
                logging.info(f"Found main content area using selector: '{selector}' for section extraction.")
                break
        except Exception as e: logging.warning(f"Error finding main content with selector '{selector}': {e}")
    if not main_content_element:
        logging.warning("Could not find main content area using provided selectors. Cannot extract sections.")
        return None
    sections = []; current_section_content = []; current_title = "Introduction / Content Before First Heading"; current_level = 0
    def process_node(node):
        nonlocal current_section_content, current_title, current_level
        if isinstance(node, Tag):
            heading_level = 0
            if node.name in heading_selectors:
                 try: heading_level = int(node.name[1:])
                 except ValueError: heading_level = 99
            if heading_level > 0:
                if current_section_content:
                     full_content = "\n".join(p.strip() for p in " ".join(current_section_content).splitlines() if p.strip())
                     if full_content: sections.append({"title": current_title, "content": full_content, "level": current_level})
                     current_section_content = []
                current_title = node.get_text(strip=True) or f"Untitled Section ({node.name})"; current_level = heading_level
                logging.debug(f"Found section: '{current_title}' (Level: {current_level})")
            else:
                 if node.name not in ['script', 'style', 'nav', 'footer', 'header', 'aside']:
                     text_content = node.get_text(separator='\n', strip=True)
                     if text_content:
                          is_leaf_like = not node.find(lambda tag: tag.name not in ['br', 'span', 'a', 'b', 'i', 'em', 'strong'])
                          if is_leaf_like: current_section_content.append(text_content)
                          else:
                              for child in node.children: process_node(child)
        elif isinstance(node, NavigableString):
            text = node.strip()
            if text: current_section_content.append(text)
    for child_node in main_content_element.children: process_node(child_node)
    if current_section_content:
        full_content = "\n".join(p.strip() for p in " ".join(current_section_content).splitlines() if p.strip())
        if full_content: sections.append({"title": current_title, "content": full_content, "level": current_level})
    if not sections:
         logging.warning("Could not extract any sections based on headings. Falling back to full text.")
         full_text = extract_html_content(soup, main_selectors) # Use original function
         if full_text: return [{"title": "Full Page Content", "content": full_text, "level": 0}]
         else: return []
    return sections

# PDF, DOCX, Tabular, Text extraction functions
def extract_pdf_content(content_bytes, url):
    """Extracts text from PDF byte content using pdfminer.six (preferred) or PyPDF2."""
    # (Same logic as before)
    text = ""; extractor_used = "none"
    if PDFMINER_AVAILABLE:
        try: text = pdfminer_extract_text(io.BytesIO(content_bytes)); extractor_used = "pdfminer.six"; logging.info(f"Extracted PDF text ({len(text)} chars) [pdfminer]: {url}")
        except Exception as e: logging.warning(f"pdfminer.six failed for {url}: {e}. Trying PyPDF2."); text = ""
    elif PYPDF2_AVAILABLE:
        try:
            with io.BytesIO(content_bytes) as f:
                reader = PdfReader(f); pdf_text_parts = []
                if reader.is_encrypted:
                     logging.warning(f"PDF is encrypted: {url}")
                     try:
                         if reader.decrypt('') == 0: raise RuntimeError("Decryption failed")
                     except Exception as de: logging.error(f"Failed decryption for {url}: {de}"); return f"Error: PDF encrypted/decryption failed."
                for i, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text();
                        if page_text: pdf_text_parts.append(page_text)
                    except Exception as pe: logging.warning(f"Error page {i+1} PDF {url}: {pe}")
                text = "\n".join(pdf_text_parts); extractor_used = "PyPDF2"; logging.info(f"Extracted PDF text ({len(text)} chars) [PyPDF2]: {url}")
        except Exception as e: logging.error(f"PyPDF2 failed for {url}: {e}"); text = f"Error: PyPDF2 parse failed: {e}"; extractor_used = "failed"
    else: logging.error(f"No PDF library for {url}."); return "Error: No PDF library."
    if not text and extractor_used not in ["none", "failed"]: logging.warning(f"No text extracted from PDF {url} ({extractor_used})."); return ""
    elif extractor_used == "failed": return text
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]; return '\n'.join(paragraphs)

def extract_docx_content(content_bytes, url):
    """Extracts text from DOCX."""
    # (Same logic as before)
    if not DOCX_AVAILABLE: return "Error: python-docx not installed."
    try:
        with io.BytesIO(content_bytes) as f:
            document = docx.Document(f); docx_text_parts = [p.text for p in document.paragraphs if p.text]; text = "\n".join(docx_text_parts)
        logging.info(f"Extracted DOCX text ({len(text)} chars) for {url}")
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]; return '\n'.join(paragraphs)
    except Exception as e: logging.error(f"Error parsing DOCX {url}: {e}"); return f"Error: Failed DOCX parse: {e}"

def extract_tabular_data(content_bytes, url, file_ext):
    """Extracts data from CSV or Excel using Pandas if available."""
    # (Same logic as before)
    if not PANDAS_AVAILABLE:
        if file_ext == '.csv': return extract_basic_csv(content_bytes, url)
        else: return "Error: Pandas library not installed."
    data_io = io.BytesIO(content_bytes)
    try:
        if file_ext == '.csv':
            df = None
            for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                try: data_io.seek(0); df = pd.read_csv(data_io, encoding=encoding, low_memory=False, on_bad_lines='warn'); logging.info(f"Parsed CSV ({encoding}, shape {df.shape}) [Pandas]: {url}"); break
                except UnicodeDecodeError: continue
                except Exception as pd_err: logging.warning(f"Pandas read_csv ({encoding}) failed: {pd_err}"); df = None
            if df is None: raise ValueError("Could not decode/parse CSV [Pandas].")
            return df.astype(object).where(pd.notnull(df), None).to_dict(orient='records')
        elif file_ext == '.xlsx':
            if not OPENPYXL_AVAILABLE: return "Error: openpyxl required by Pandas for .xlsx."
            data_io.seek(0); excel_data = pd.read_excel(data_io, sheet_name=None, engine='openpyxl')
            logging.info(f"Parsed Excel (Sheets: {list(excel_data.keys())}) [Pandas]: {url}")
            output_data = {}
            for sheet_name, df_sheet in excel_data.items(): output_data[sheet_name] = df_sheet.astype(object).where(pd.notnull(df_sheet), None).to_dict(orient='records')
            return output_data
        else: return f"Error: Pandas cannot handle '{file_ext}'."
    except Exception as e:
        logging.error(f"Error processing tabular data ({file_ext}) [Pandas]: {e}")
        if file_ext == '.csv': logging.info(f"Falling back to basic CSV: {url}"); return extract_basic_csv(content_bytes, url)
        return f"Error: Failed processing tabular data: {e}"

def extract_basic_csv(content_bytes, url):
    """Basic CSV parsing fallback (list of lists)."""
    # (Same logic as before)
    try:
        text_content = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try: text_content = content_bytes.decode(encoding); logging.info(f"Decoded basic CSV ({encoding}) for {url}"); break
            except UnicodeDecodeError: continue
        if text_content is None: raise ValueError("Could not decode CSV.")
        import csv; reader = csv.reader(io.StringIO(text_content.replace('\x00', '')), delimiter=',', quotechar='"'); data = list(reader)
        logging.info(f"Parsed basic CSV (rows: {len(data)}) for {url}"); return data
    except Exception as e: logging.error(f"Error basic CSV for {url}: {e}"); return f"Error: Failed basic CSV: {e}"

def extract_text_content(content_bytes, url):
    """Extracts text from plain text byte content."""
    # (Same logic as before)
    try:
        text_content = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
             try: text_content = content_bytes.decode(encoding); logging.info(f"Decoded text file ({encoding}) for {url}"); break
             except UnicodeDecodeError: continue
        if text_content is None: raise ValueError("Could not decode text.")
        paragraphs = [p.strip() for p in text_content.splitlines() if p.strip()]; return '\n'.join(paragraphs)
    except Exception as e: logging.error(f"Error parsing text file {url}: {e}"); return f"Error: Failed text parse: {e}"

# --- Main Scraping Logic (incorporating dynamic fallback) ---

def scrape_site_and_supporting_docs(start_url, run_output_dir, robot_parser):
    """
    Scrapes the main page and supporting documents, saving results to run_output_dir.
    Returns a dictionary representing the index data and a list for embedding data.
    """
    logging.info(f"--- Starting scrape process for: {start_url} ---")
    parsed_start = urlparse(start_url)
    cleaned_start_url = urlunparse(parsed_start._replace(query='', fragment=''))

    index_data = { # (Same structure as before)
        "scrape_metadata": { "start_url": start_url, "cleaned_start_url": cleaned_start_url, "user_agent": USER_AGENT, "timestamp_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "robots_txt_status": "Checked_Allowed" if robot_parser and robot_parser.allow_all else ("Checked_RulesFound" if robot_parser else "Fetch/Parse Failed"), "output_directory": run_output_dir, "total_supporting_links_found": 0, "total_supporting_docs_processed": 0, },
        "main_document": {"url": start_url, "status": "processing"}, "supporting_documents": []
    }
    embedding_data = []

    # --- 1. Fetch and Parse Main Page (with Dynamic Fallback) --- # MODIFIED SECTION
    logging.info(f"Attempting initial fetch (requests): {start_url}")
    main_page_response_or_status = fetch_url(start_url, robot_parser) # Fetch using requests first

    main_page_html = None
    fetch_method_used = "requests"
    content_type_main = None

    if isinstance(main_page_response_or_status, requests.Response): # If requests succeeded
        content_type_main = main_page_response_or_status.headers.get('Content-Type', '').split(';')[0].strip().lower()
        index_data["main_document"]["content_type_header"] = content_type_main
        if 'text/html' in content_type_main:
            try:
                main_page_html = main_page_response_or_status.content.decode('utf-8', errors='ignore') # Decode safely
                logging.info(f"Initial fetch successful (requests). Content length: {len(main_page_html)}")
                # Check if content is too short AND dynamic fallback is enabled
                if len(main_page_html) < MIN_HTML_CONTENT_LENGTH and (USE_SELENIUM_FALLBACK or USE_PLAYWRIGHT_FALLBACK):
                     logging.warning(f"Initial HTML content length ({len(main_page_html)}) < threshold ({MIN_HTML_CONTENT_LENGTH}). Will attempt dynamic fallback.")
                     main_page_html = None # Reset html to trigger fallback
                elif len(main_page_html) < MIN_HTML_CONTENT_LENGTH:
                     logging.warning(f"Initial HTML content length ({len(main_page_html)}) < threshold ({MIN_HTML_CONTENT_LENGTH}), dynamic fallback disabled.")
            except Exception as decode_err:
                 logging.error(f"Error decoding initial HTML response: {decode_err}")
                 main_page_html = None # Treat as fetch failure
        else:
             # If not HTML, report error and exit (no point in dynamic fallback)
             index_data["main_document"]["status"] = "error_not_html"
             index_data["main_document"]["error_message"] = f"Main page is not HTML (Content-Type: {content_type_main})."
             logging.critical(f"Main page {start_url} is not HTML. Aborting.")
             return index_data, embedding_data

    # --- Try dynamic fallback if initial attempt failed, was short, or was disallowed (but we need HTML) ---
    # Fallback only makes sense for HTML pages
    needs_fallback = main_page_html is None and ('text/html' in (content_type_main or '') or content_type_main is None)
    # Also check if initial fetch was disallowed by robots - if so, don't fallback
    should_fallback = needs_fallback and main_page_response_or_status != "ROBOTS_DISALLOWED"

    if should_fallback:
        if isinstance(main_page_response_or_status, str): # Log if initial fetch failed for non-robots reason
             logging.warning(f"Initial fetch failed ({main_page_response_or_status}) or content short. Attempting dynamic fallback.")
        elif main_page_html is None: # Log if decode failed or content was short
             logging.info("Initial HTML content was short or decode failed. Attempting dynamic fallback.")

        # Ensure robots allows the URL again before dynamic fetch
        if can_fetch_url(robot_parser, start_url):
             if USE_PLAYWRIGHT_FALLBACK and PLAYWRIGHT_AVAILABLE:
                 fetch_method_used = "playwright"
                 main_page_html = fetch_page_source_playwright(start_url)
             elif USE_SELENIUM_FALLBACK and SELENIUM_AVAILABLE:
                 fetch_method_used = "selenium"
                 main_page_html = fetch_page_source_selenium(start_url)
             else:
                  logging.warning("Dynamic fallback requested but required libraries/setup not available.")
        # else: Robots disallowed, main_page_html remains None, error handled below

    # --- Check final fetch result ---
    if main_page_html is None:
        error_status = "fetch_error"
        error_msg = f"Failed to fetch main URL content using all methods (requests"
        if USE_PLAYWRIGHT_FALLBACK: error_msg += "/playwright"
        if USE_SELENIUM_FALLBACK: error_msg += "/selenium"
        error_msg += ")."
        # Refine error if initial attempt gave specific status
        if isinstance(main_page_response_or_status, str):
             if main_page_response_or_status == "ROBOTS_DISALLOWED":
                 error_status = "skipped_robots"; error_msg = "Fetch disallowed by robots.txt"
             else: # Other fetch error like timeout/network
                 error_msg = f"Failed to fetch main URL ({main_page_response_or_status}) and dynamic fallback failed or disabled."
        index_data["main_document"]["status"] = error_status
        index_data["main_document"]["error_message"] = error_msg
        logging.critical(f"{error_msg} for {start_url}. Aborting scrape.")
        return index_data, embedding_data

    # --- Parse the final successful HTML ---
    try:
        main_soup = BeautifulSoup(main_page_html, 'html.parser')
        index_data["main_document"]["fetch_method"] = fetch_method_used
        index_data["main_document"]["metadata"] = extract_html_metadata(main_soup)
    except Exception as e:
        index_data["main_document"]["status"] = "error_parsing_html"
        index_data["main_document"]["error_message"] = f"Failed to parse main page HTML (fetched via {fetch_method_used}): {e}"
        logging.critical(f"Failed to parse main page HTML for {start_url}: {e}. Aborting.")
        return index_data, embedding_data

    # --- 2. Extract Sections and Save Main Page Content ---
    # (This section remains the same - uses the successfully parsed main_soup)
    logging.info("Attempting to extract content by sections...")
    extracted_sections = extract_sections_from_html(main_soup, MAIN_CONTENT_SELECTORS, SECTION_HEADING_SELECTORS)
    if extracted_sections is None:
         index_data["main_document"]["status"] = "error_no_main_content_selector_match"
         index_data["main_document"]["error_message"] = "Could not find main content area using defined selectors."
         logging.error("Could not find main content area to extract sections.")
    elif not extracted_sections:
         index_data["main_document"]["status"] = "processed_empty"
         index_data["main_document"]["error_message"] = "Main content area found, but no text or sections extracted."
         logging.warning("Main content area found, but no text or sections extracted.")
    else:
        index_data["main_document"]["sections"] = []
        all_main_text_for_embedding = [] # Still collect full text for embedding file

        for section_index, section in enumerate(extracted_sections):
            section_title = section['title']
            section_content = section['content']
            section_level = section['level']
            sanitized_title = sanitize_filename(section_title) if section_title else f"section_{section_index}"

            logging.info(f"Processing Section: '{section_title}' (Level: {section_level}, Length: {len(section_content)} chars)")
            all_main_text_for_embedding.append(section_content) # Add raw section text for embedding

            section_entry = {
                "title": section_title,
                "level": section_level,
                "content_files": [] # Will contain max one file per section now
            }

            if isinstance(section_content, str) and section_content.startswith("Error:"):
                section_entry["status"] = "error_extracting_content"
                section_entry["error_message"] = section_content
            elif section_content:
                # Save the entire section content to one file
                filename = f"content_main_section{section_index}_{sanitized_title}.json"
                filepath = os.path.join(run_output_dir, filename)
                # Save content directly, no chunking needed here
                section_data = {"url": start_url, "section_title": section_title, "level": section_level, "content": section_content}
                save_json(section_data, filepath)
                section_entry["content_files"].append(filename) # Add the single filename
                section_entry["status"] = "processed"
                logging.info(f"Saved section '{section_title}' content to {filename}")
            else:
                 section_entry["status"] = "processed_empty" # Section found but no content

            index_data["main_document"]["sections"].append(section_entry)

        # Add the combined main text to embedding data
        if all_main_text_for_embedding:
             embedding_data.append({
                  "source_url": cleaned_start_url,
                  "title": index_data["main_document"]["metadata"].get("title", "Main Document"),
                  "text": "\n\n".join(all_main_text_for_embedding) # Join sections for embedding file
             })

        index_data["main_document"]["status"] = "processed"

    # --- 3. Find Supporting Document Links --- # MODIFIED SECTION
    logging.info("Finding potential supporting document links...")
    potential_links = set()
    processed_urls = set([start_url]) # Keep track of URLs already processed or the main page

    # Gather all potential links first using selectors
    for selector in SUPPORTING_LINK_SELECTORS:
        try:
            for link_tag in main_soup.select(selector):
                href = link_tag.get('href')
                if href:
                    abs_url = make_absolute_url(start_url, href)
                    # Add if it's a valid URL and not the page itself
                    if abs_url and abs_url != start_url:
                         potential_links.add(abs_url)
        except Exception as e:
             logging.warning(f"Error processing link selector '{selector}': {e}")

    # Now, filter the gathered potential links
    filtered_links = set() # Initialize the set that will be used later
    for link_url in potential_links:
         # Skip if we somehow added it to processed already (e.g., redirects)
         if link_url in processed_urls:
              continue

         ext = get_file_extension(link_url)
         # Basic MIME type guess, helps for URLs without extensions
         content_type_guess = mimetypes.guess_type(link_url)[0]

         is_allowed_ext = ext in ALLOWED_SUPPORTING_DOC_EXTENSIONS
         # Check if it looks like an HTML page even without a standard extension
         is_likely_html = ext is None and content_type_guess and 'html' in content_type_guess

         if is_allowed_ext or is_likely_html:
              filtered_links.add(link_url)
              # Add to processed_urls here to avoid duplicates if linked multiple times
              processed_urls.add(link_url)
         # else: Log skipped link if desired for debugging
         #    logging.debug(f"Skipping link (disallowed extension/type): {link_url} (ext: {ext}, type: {content_type_guess})")


    index_data["scrape_metadata"]["total_supporting_links_found"] = len(filtered_links) # Count the final filtered set
    logging.info(f"Found {len(filtered_links)} unique supporting document links matching criteria.")

    # --- 4. Process Supporting Documents ---
    doc_counter = 0
    # *** The loop below should now correctly use the 'filtered_links' set defined above ***
    for link_url in filtered_links:
        if link_url in processed_urls: continue
        processed_urls.add(link_url)
        doc_counter += 1
        doc_index_entry = {"url": link_url, "status": "processing"}
        index_data["supporting_documents"].append(doc_index_entry)
        cleaned_link_url = urlunparse(urlparse(link_url)._replace(query='', fragment=''))
        file_ext = get_file_extension(link_url)
        doc_index_entry["file_extension"] = file_ext

        # Fetch supporting document
        doc_response_or_status = fetch_url(link_url, robot_parser)

        if isinstance(doc_response_or_status, str): # Fetch failed or disallowed
            error_status = "fetch_error"; error_msg = f"Failed to fetch URL: {doc_response_or_status}"
            if doc_response_or_status == "ROBOTS_DISALLOWED": error_status = "skipped_robots"; error_msg = "Fetch disallowed by robots.txt"
            doc_index_entry["status"] = error_status; doc_index_entry["error_message"] = error_msg
            continue

        content_type = doc_response_or_status.headers.get('Content-Type', '').split(';')[0].strip().lower()
        doc_index_entry["content_type_header"] = content_type
        doc_content_bytes = doc_response_or_status.content

        extracted_data = None; doc_type = "unknown"; is_structured_data = False
        raw_text_for_embedding = None; fetch_method_used_supp = "requests"; linked_html_content = None

        try:
            # Determine type and extract content
            is_html = 'text/html' in content_type or file_ext in ['.html', '.htm']

            if is_html:
                # --- HTML Processing (with dynamic fallback, save full content) ---
                doc_type = "html"
                try: linked_html_content = doc_content_bytes.decode('utf-8', errors='ignore')
                except Exception as e: logging.warning(f"Could not decode initial linked HTML {link_url}: {e}"); linked_html_content = None
                # Dynamic fallback if needed (requests failed or content too short)
                if linked_html_content is None or (len(linked_html_content) < MIN_HTML_CONTENT_LENGTH and (USE_PLAYWRIGHT_FALLBACK or USE_SELENIUM_FALLBACK)):
                    if can_fetch_url(robot_parser, link_url):
                           if USE_PLAYWRIGHT_FALLBACK and PLAYWRIGHT_AVAILABLE: fetch_method_used_supp = "playwright"; linked_html_content = fetch_page_source_playwright(link_url)
                           elif USE_SELENIUM_FALLBACK and SELENIUM_AVAILABLE: fetch_method_used_supp = "selenium"; linked_html_content = fetch_page_source_selenium(link_url)
                # Process final HTML
                if linked_html_content:
                     try:
                         linked_soup = BeautifulSoup(linked_html_content, 'html.parser')
                         doc_index_entry["metadata"] = extract_html_metadata(linked_soup)
                         doc_index_entry["fetch_method"] = fetch_method_used_supp
                         extracted_data = extract_html_content(linked_soup, MAIN_CONTENT_SELECTORS) # Extract full text
                         logging.info(f"Parsed linked HTML ({fetch_method_used_supp}): {link_url}")
                         if isinstance(extracted_data, str) and not extracted_data.startswith("Error:"): raw_text_for_embedding = extracted_data
                     except Exception as e: logging.error(f"Error parsing linked HTML ({fetch_method_used_supp}) {link_url}: {e}"); extracted_data = f"Error: Failed to parse linked HTML: {e}"
                elif doc_index_entry["status"] == 'processing': extracted_data = "Error: Failed to fetch/parse linked HTML content."
            # --- Non-HTML Processing ---
            elif 'application/pdf' in content_type or file_ext == '.pdf':
                doc_type = "pdf"; extracted_data = extract_pdf_content(doc_content_bytes, link_url)
                if isinstance(extracted_data, str) and not extracted_data.startswith("Error:"): raw_text_for_embedding = extracted_data
            elif 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in content_type or file_ext == '.docx':
                 doc_type = "docx"; extracted_data = extract_docx_content(doc_content_bytes, link_url)
                 if isinstance(extracted_data, str) and not extracted_data.startswith("Error:"): raw_text_for_embedding = extracted_data
            elif 'text/csv' in content_type or file_ext == '.csv':
                 doc_type = "csv"; extracted_data = extract_tabular_data(doc_content_bytes, link_url, '.csv'); is_structured_data = not isinstance(extracted_data, str) or not extracted_data.startswith("Error:")
            elif 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type or file_ext == '.xlsx':
                 doc_type = "excel"; extracted_data = extract_tabular_data(doc_content_bytes, link_url, '.xlsx'); is_structured_data = not isinstance(extracted_data, str) or not extracted_data.startswith("Error:")
            elif 'text/plain' in content_type or file_ext == '.txt':
                 doc_type = "text"; extracted_data = extract_text_content(doc_content_bytes, link_url)
                 if isinstance(extracted_data, str) and not extracted_data.startswith("Error:"): raw_text_for_embedding = extracted_data
            else:
                 logging.warning(f"Skipping content extraction (unhandled type '{content_type}' / ext '{file_ext}'): {link_url}")
                 doc_type = content_type or f"unknown ({file_ext})"; doc_index_entry["status"] = "skipped_unhandled_type"; extracted_data = None

            doc_index_entry["detected_type"] = doc_type

            # Add raw text to embedding data
            if raw_text_for_embedding:
                 embedding_data.append({ "source_url": cleaned_link_url, "title": doc_index_entry.get("metadata", {}).get("title", f"Supporting Document {doc_counter}"), "text": raw_text_for_embedding })

            # --- Save full content (no chunking for supporting docs) ---
            content_files = []
            if isinstance(extracted_data, str) and extracted_data.startswith("Error:"):
                if doc_index_entry["status"] == 'processing': doc_index_entry["status"] = "processing_error"
                doc_index_entry["error_message"] = extracted_data
            elif is_structured_data:
                 filename = f"content_doc{doc_counter}_structured_data.json"
                 filepath = os.path.join(run_output_dir, filename)
                 save_json({"url": link_url, "data_type": doc_type, "data": extracted_data}, filepath)
                 content_files.append(filename); doc_index_entry["status"] = "processed"
            elif isinstance(extracted_data, str) and extracted_data:
                 # Save the *entire* extracted text to a single file
                 filename = f"content_doc{doc_counter}_full.json"
                 filepath = os.path.join(run_output_dir, filename)
                 doc_data = {"url": link_url, "content_type": doc_type, "content": extracted_data}
                 save_json(doc_data, filepath)
                 content_files.append(filename)
                 if doc_index_entry["status"] == 'processing': doc_index_entry["status"] = "processed"
                 logging.info(f"Saved full doc {doc_counter} content to {filename}")
            elif extracted_data is None and doc_index_entry["status"] == "processing":
                 doc_index_entry["status"] = "processed_empty"
                 logging.warning(f"No content extracted for doc {doc_counter} ({link_url}), though type was handled.")

            doc_index_entry["content_files"] = content_files # Store the list (usually just one filename)

        except Exception as e:
            logging.error(f"Unexpected error processing document {link_url}: {e}", exc_info=True)
            doc_index_entry["status"] = "processing_error"; doc_index_entry["error_message"] = f"Unexpected error: {e}"

    index_data["scrape_metadata"]["total_supporting_docs_processed"] = doc_counter
    logging.info(f"--- Finished processing supporting documents ---")
    return index_data, embedding_data

def get_robot_parser(start_url):
        """Fetches and parses the robots.txt file for the site using requests."""
        parsed_uri = urlparse(start_url)
        # Handle cases where netloc might be missing (though unlikely given earlier checks)
        if not parsed_uri.scheme or not parsed_uri.netloc:
            logging.error(f"Invalid URL for robots.txt: {start_url}")
            # Return a default permissive parser if URL is fundamentally broken
            rp = robotparser.RobotFileParser()
            rp.allow_all = True
            rp.disallow_all = False
            return rp

        robots_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/robots.txt"
        logging.info(f"Attempting to fetch robots.txt from: {robots_url}")

        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url) # Still useful to set the URL for context within the parser

        try:
            # Use requests to fetch with timeout and headers
            response = requests.get(
                robots_url,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS # Use the standard request timeout
            )
            # Check for common non-success codes explicitly
            if response.status_code == 404:
                logging.warning(f"robots.txt not found at {robots_url} (HTTP 404). Assuming allowed.")
                rp.allow_all = True
                rp.disallow_all = False
            elif response.status_code >= 400:
                logging.warning(f"HTTP error {response.status_code} fetching robots.txt from {robots_url}. Assuming allowed.")
                rp.allow_all = True
                rp.disallow_all = False
            else:
                # Success: Parse the fetched content
                rp.parse(response.text.splitlines())
                logging.info(f"Successfully fetched and parsed robots.txt for {parsed_uri.netloc}")

        except requests.exceptions.Timeout:
            logging.error(f"Timeout error fetching robots.txt from {robots_url} after {REQUEST_TIMEOUT_SECONDS} seconds. Assuming allowed.")
            rp.allow_all = True
            rp.disallow_all = False
        except requests.exceptions.RequestException as e:
            logging.error(f"Could not fetch robots.txt from {robots_url}: {e}. Assuming allowed.")
            rp.allow_all = True
            rp.disallow_all = False
        except Exception as e:
            logging.error(f"Unexpected error processing robots.txt from {robots_url}: {e}. Assuming allowed.")
            rp.allow_all = True
            rp.disallow_all = False

        # Set modification time based on successful fetch (if possible, though requests doesn't easily expose this like rp.read())
        # We can use the current time as an approximation if needed elsewhere, but mtime() isn't critical for can_fetch()
        # if rp.allow_all is None: # Check if parsing actually happened vs. defaulting
        #    rp.set_last_modified(time.time()) # Not a real method, just illustrating concept

        return rp

# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape a website and its linked documents, saving structured output.")
    parser.add_argument("url", help="The starting URL to scrape.")
    parser.add_argument("--use-selenium", action="store_true", help="Enable Selenium fallback for dynamic content.")
    parser.add_argument("--use-playwright", action="store_true", help="Enable Playwright fallback for dynamic content.")

    if len(sys.argv) == 1: parser.print_help(sys.stderr); sys.exit(1)
    args = parser.parse_args()
    start_url = args.url

    # Override config flags from command-line
    if args.use_selenium: USE_SELENIUM_FALLBACK = True; USE_PLAYWRIGHT_FALLBACK = False
    if args.use_playwright: USE_PLAYWRIGHT_FALLBACK = True; USE_SELENIUM_FALLBACK = False

    parsed_start_url = urlparse(start_url)
    if not all([parsed_start_url.scheme, parsed_start_url.netloc]):
        print(f"Error: Invalid URL: {start_url}. Include scheme (http/https).", file=sys.stderr); sys.exit(1)

    # Setup Output Directory
    domain_part = sanitize_filename(parsed_start_url.netloc)
    path_part = sanitize_filename(parsed_start_url.path.split('/')[1]) if len(parsed_start_url.path.split('/')) > 1 and parsed_start_url.path != '/' else ""
    if path_part and path_part not in ["index", "default", "home", ""]: base_name = f"{domain_part}_{path_part}"
    else: base_name = domain_part
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder_name = f"{base_name}_{timestamp}"
    run_output_dir = os.path.join(BASE_OUTPUT_DIR, run_folder_name)

    try: os.makedirs(run_output_dir, exist_ok=True); print(f"Output will be saved to: {run_output_dir}")
    except OSError as e: print(f"Error creating output directory {run_output_dir}: {e}", file=sys.stderr); sys.exit(1)

    log_file_path = os.path.join(run_output_dir, "scraper.log")
    setup_logging(log_file_path) # Setup logging AFTER output dir is known

    # --- Start Scraping ---
    # Ensure this line EXISTS and is NOT commented out:
    rp = get_robot_parser(start_url) # Fetch robots.txt info

    # Now you can safely call the next function using the 'rp' variable:
    final_index_data, embedding_data = scrape_site_and_supporting_docs(start_url, run_output_dir, rp)

    # --- Save the final index ---
    index_filepath = os.path.join(run_output_dir, "index.json")
    save_json(final_index_data, index_filepath)

    # --- Save the combined embedding source file ---
    embedding_filepath = os.path.join(run_output_dir, "embedding_source.json")
    save_json(embedding_data, embedding_filepath)

    print(f"\n--- Scrape complete ---")
    print(f"Index file saved to: {index_filepath}")
    print(f"Embedding source file saved to: {embedding_filepath}")
    print(f"Log file saved to: {log_file_path}")
    print(f"Content files saved in: {run_output_dir}")