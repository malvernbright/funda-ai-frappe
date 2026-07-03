import requests
import random
from bs4 import BeautifulSoup
import frappe
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_random_user_agent():
    """Returns a rotating legit user agent string to protect local environments from blocking rules."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    ]
    return random.choice(user_agents)

def fetch_online_context(query: str) -> str:
    """Queries DuckDuckGo raw HTML index fallback with total error containment mechanics."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {"User-Agent": get_random_user_agent()}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=6)
        if response.status_code != 200:
            return ""
            
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        for result in soup.find_all("div", class_="result__body")[:3]:
            title_el = result.find("a", class_="result__url")
            snippet_el = result.find("a", class_="result__snippet")
            
            if title_el and snippet_el:
                title = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True)
                results.append(f"Source Link: {title}\nSummary context: {snippet}")
                
        if results:
            return "\n\n".join(results)
        return ""
        
    except Exception as parse_error:
        # Wrap the error silently to prevent system-wide logging crash overflows
        frappe.log_error(f"Web Context Failure: {str(parse_error)[:100]}", "Funda AI Search Supressor")
        return ""