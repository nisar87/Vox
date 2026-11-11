"""Open sites and run searches in the user's browser."""

from __future__ import annotations

import os
import re
import subprocess
import webbrowser
from urllib.parse import quote_plus

from .base import tool

SEARCH = {
    "google": "https://www.google.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "amazon": "https://www.amazon.com/s?k={q}",
    "github": "https://github.com/search?q={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "maps": "https://www.google.com/maps/search/{q}",
}
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "maps": "https://www.google.com/maps",
    "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com", "github": "https://github.com",
    "wikipedia": "https://www.wikipedia.org", "amazon": "https://www.amazon.com",
    "reddit": "https://www.reddit.com", "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com", "chatgpt": "https://chatgpt.com",
    "gemini": "https://gemini.google.com", "bing": "https://www.bing.com",
    "twitter": "https://x.com",
}
BROWSER_EXE = {"chrome": "chrome", "edge": "msedge", "firefox": "firefox", "brave": "brave"}


def launch_url(url: str, browser: str = "default") -> None:
    """Open a URL. Replaced in tests."""
    exe = BROWSER_EXE.get(browser)
    if os.name == "nt" and exe:
        subprocess.Popen(["cmd", "/c", "start", "", exe, url], creationflags=0x08000000)
    else:
        webbrowser.open(url)


def _browser(ctx, browser) -> str:
    return browser if browser in BROWSER_EXE else ctx.config["browser"]


@tool("web_search", "Search the web, or a specific site, in the browser.",
      {"query": {"type": "string"},
       "site": {"type": "string", "enum": list(SEARCH), "description": "Where to search. Default google."},
       "browser": {"type": "string", "enum": list(BROWSER_EXE), "description": "Only if the user named one."}},
      ("query",))
def web_search(ctx, query, site="google", browser=None):
    site = site if site in SEARCH else "google"
    launch_url(SEARCH[site].format(q=quote_plus(query)), _browser(ctx, browser))
    where = {"google": "the web", "youtube": "YouTube", "github": "GitHub", "maps": "Google Maps"}.get(site, site.title())
    return {"message": f"Searching {where} for {query}."}


@tool("open_website", "Open a website by name or address.",
      {"site": {"type": "string", "description": "e.g. 'youtube', 'gmail', 'bbc.com'."},
       "browser": {"type": "string", "enum": list(BROWSER_EXE)}},
      ("site",))
def open_website(ctx, site, browser=None):
    key = site.lower().strip()
    if key in SITES:
        url = SITES[key]
    elif re.match(r"^https?://", key):
        url = site.strip()
    elif "." in key and " " not in key:
        url = "https://" + key
    else:
        url = "https://www." + re.sub(r"[^a-z0-9-]", "", key) + ".com"
    launch_url(url, _browser(ctx, browser))
    return {"message": f"Opening {site}."}
