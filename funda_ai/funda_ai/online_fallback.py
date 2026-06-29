import requests
from bs4 import BeautifulSoup
import frappe
import logging
import random


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

def get_random_user_agent():
    """Returns a random legitimate browser string to avoid bot detection."""
    user_agents = [
        # Windows Chrome
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Mac Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
        # Linux Firefox
        "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
        # Windows Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ]
    return random.choice(user_agents)

def fetch_online_context(query: str) -> str:
    """Performs a real, live web search using DuckDuckGo's raw HTML interface."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    # Pretend to be a normal browser so we don't get blocked
    headers = {
        "User-Agent": get_random_user_agent()
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=6)
        if response.status_code != 200:
            return ""
            
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        # Grab the top 3 search results
        for result in soup.find_all("div", class_="result__body")[:3]:
            title_el = result.find("a", class_="result__url")
            snippet_el = result.find("a", class_="result__snippet")
            
            if title_el and snippet_el:
                title = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True)
                results.append(f"Result: {title}\nSnippet: {snippet}")
                
        if results:
            return "\n\n".join(results)
            
        return ""
        
    except Exception as e:
        # Silently fail and log it to Frappe so the app doesn't crash
        frappe.log_error(f"Online search error: {str(e)}", "Funda AI Online Fallback")
        return ""