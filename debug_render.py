"""Debug script: show raw word count vs rendered word count for a URL."""
import sys, time
sys.path.insert(0, ".")

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BrandAuditBot/1.0)"}

def extract_visible_text_bs4(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script","style","head","meta","noscript","template"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)

def tokenize(text):
    import re
    return set(re.findall(r"[a-z]{3,}", text.lower()))

url = sys.argv[1] if len(sys.argv) > 1 else "https://react.dev"

print(f"Testing: {url}")
resp = requests.get(url, headers=HEADERS, timeout=15)
raw_text = extract_visible_text_bs4(resp.text)
raw_tokens = tokenize(raw_text)
print(f"Raw HTML word count (visible): {len(raw_text.split())}")
print(f"Raw token set size: {len(raw_tokens)}")
print(f"First 200 chars of raw text: {raw_text[:200]!r}")
print()

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=20_000)
        rendered_text = page.evaluate("document.body.innerText") or ""
        page.close()
        context.close()
        browser.close()
    
    rendered_tokens = tokenize(rendered_text)
    print(f"Playwright rendered word count: {len(rendered_text.split())}")
    print(f"Rendered token set size: {len(rendered_tokens)}")
    print(f"First 200 chars of rendered text: {rendered_text[:200]!r}")
    print()
    
    missing = rendered_tokens - raw_tokens
    gap_pct = len(missing) / max(len(rendered_tokens), 1) * 100
    print(f"Tokens in rendered but NOT in raw: {len(missing)}")
    print(f"Render gap: {gap_pct:.1f}%")
    print(f"Sample missing tokens: {list(missing)[:20]}")
except Exception as e:
    print(f"Playwright error: {e}")
