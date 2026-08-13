# ================================================================
# GIDEON — integrations/web.py
# ----------------------------------------------------------------
# External data-fetching calls: Serper search, Firecrawl page
# reading, OpenWeatherMap, NewsAPI. Grouped together — same reasoning
# as integrations/providers.py: small, no shared coupling with core
# logic, simpler as one file on a phone workflow than four.
#
# Tag-parsing functions (extract_search_trigger, extract_read_trigger)
# are NOT here — those parse [SEARCH:...]/[READ:...] out of an LLM
# reply, which is core-agent logic, not an external call. They stay
# in server.py. Likewise run_research() (orchestrates search + read +
# extraction + knowledge-graph storage) stays in server.py — it's a
# skill, not a plain integration.
# ================================================================

import re
import requests

from config.environment import SERPER_KEY, FIRECRAWL_KEY, WEATHER_KEY, NEWS_KEY
from integrations.client import SESSION


# ── SERPER (search) ──────────────────────────────────────────────

def web_search(query: str) -> str:
    """
    Calls Serper.dev Google Search API and returns a short plain-text
    summary of the top results, or '' on any failure.
    Serper response: { "organic": [ { "title", "snippet", "link" }, ... ] }
    Free tier: 2500 queries/month, no credit card required.
    """
    if not SERPER_KEY:
        print("[Search] SERPER_KEY not configured")
        return ""
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY":    SERPER_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": 5},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"[Search] Serper returned {r.status_code}: {r.text[:200]}")
            return ""

        data    = r.json()
        results = data.get("organic", [])[:5]
        if not results:
            return ""

        lines = []
        for item in results:
            title   = item.get("title",   "").strip()
            snippet = item.get("snippet", "").strip()
            snippet = re.sub(r'<[^>]+>', '', snippet)   # strip any stray HTML
            if title and snippet:
                lines.append(f"- {title}: {snippet}")

        # include answerBox if Serper returned one (e.g. weather, sports, quick facts)
        answer_box = data.get("answerBox", {})
        if answer_box:
            answer = (
                answer_box.get("answer") or
                answer_box.get("snippet") or
                answer_box.get("snippetHighlighted", [""])[0]
            )
            if answer:
                lines.insert(0, f"Direct answer: {answer}")

        return "\n".join(lines[:6])
    except Exception as e:
        print(f"[Search] exception: {e}")
        return ""


def web_search_with_links(query: str, num: int = 5) -> list:
    """
    Like web_search(), but returns structured results with URLs intact
    instead of a display-formatted string. web_search()'s output drops
    links entirely since it's built for showing snippets in a reply —
    Research Mode needs the actual URLs to hand to firecrawl_read().
    Returns [] on any failure.
    """
    if not SERPER_KEY:
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        results = r.json().get("organic", [])[:num]
        return [
            {
                "title":   item.get("title", "").strip(),
                "snippet": re.sub(r'<[^>]+>', '', item.get("snippet", "").strip()),
                "url":     item.get("link", "").strip(),
            }
            for item in results if item.get("link")
        ]
    except Exception as e:
        print(f"[Research] search exception: {e}")
        return []


# ── FIRECRAWL (full page reader) ─────────────────────────────────
# Free tier: 500 credits/month, 1 credit per scrape.

def firecrawl_read(url: str) -> str:
    if not FIRECRAWL_KEY:
        print("[Firecrawl] FIRECRAWL_KEY not configured")
        return ""
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {FIRECRAWL_KEY}",
                "Content-Type":  "application/json",
            },
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=20,
        )
        if r.status_code != 200:
            print(f"[Firecrawl] HTTP {r.status_code}")
            return ""
        return r.json().get("data", {}).get("markdown", "")[:4000].strip()
    except Exception as e:
        print(f"[Firecrawl] error: {e}")
        return ""


# ── WEATHER (OpenWeatherMap) ──────────────────────────────────────

def get_weather(city: str = "") -> str:
    if not WEATHER_KEY:
        return ""
    try:
        r = SESSION.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city or "Lagos", "appid": WEATHER_KEY, "units": "metric"},
            timeout=5,
        )
        d = r.json()
        if d.get("cod") == 200:
            return (f"Weather in {d['name']}: {d['weather'][0]['description']}, "
                    f"{d['main']['temp']}°C, feels like {d['main']['feels_like']}°C, "
                    f"humidity {d['main']['humidity']}%.")
    except Exception as e:
        print(f"[Weather] {e}")
    return ""


def extract_city_from_weather_query(msg: str) -> str:
    """
    Fixes the bug where 'weather in New York tomorrow?' produced
    'New York tomorrow?' as the city. Strips trailing time words
    and punctuation.
    """
    ml = msg.lower()
    idx = ml.find(" in ")
    if idx < 0:
        return ""
    city = msg[idx + 4:].strip()
    # strip common trailing time/question words
    city = re.sub(
        r'\b(today|tomorrow|tonight|this week|right now|now)\b',
        '', city, flags=re.IGNORECASE
    ).strip()
    city = city.rstrip("?!.,").strip()
    return city[:50]


# ── NEWS (NewsAPI) ─────────────────────────────────────────────────

def get_news() -> str:
    if not NEWS_KEY:
        return ""
    try:
        r = SESSION.get(
            "https://newsapi.org/v2/top-headlines",
            params={"apiKey": NEWS_KEY, "country": "ng", "pageSize": 3},
            timeout=5,
        )
        arts = r.json().get("articles", [])
        hl = [a["title"] for a in arts[:3] if a.get("title")]
        return "Latest news: " + ". ".join(hl) if hl else ""
    except Exception as e:
        print(f"[News] {e}")
    return ""
