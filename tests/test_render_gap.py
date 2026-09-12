import os
import sys
import tempfile
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

# Add render-readability-audit script directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "skills" / "render-readability-audit" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_render_gap import compute_render_gap, extract_visible_text_bs4


def test_ssr_page_has_low_render_gap(tmp_path):
    """
    Test 1: Server-Side Rendered page with <h1> and two <p> tags (no JS).
    Verifies that the render gap between raw HTML and headless Playwright DOM is < 5%.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Server-Side Rendered Article</title>
</head>
<body>
    <h1>Understanding Modern AI Search Architecture</h1>
    <p>Modern artificial intelligence search engines and answer assistants ingest web content to build semantic representations.</p>
    <p>By delivering clean server-side rendered HTML without client JavaScript barriers, websites ensure accurate citation and discovery.</p>
</body>
</html>"""

    test_file = tmp_path / "ssr_page.html"
    test_file.write_text(html_content, encoding="utf-8")

    # Extract raw text from HTML without JS execution
    raw_text = extract_visible_text_bs4(html_content)

    # Render with headless Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(test_file.as_uri())
        rendered_text = page.evaluate("document.body.innerText") or ""
        browser.close()

    gap = compute_render_gap(raw_text, rendered_text)
    assert gap < 5.0, f"Expected SSR render gap to be below 5%, got {gap}%"


def test_js_injected_content_has_high_render_gap(tmp_path):
    """
    Test 2: Single-page application style page with empty <div id="root"> and
    a <script> that injects 200 words of dynamic content.
    Verifies that the render gap is > 50%.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Client-Side Hydrated SPA</title>
</head>
<body>
    <div id="root"></div>
    <script>
        const vocabulary = [
            "artificial", "intelligence", "search", "optimization", "readiness",
            "semantic", "crawling", "discovery", "visibility", "indexing",
            "knowledge", "entity", "relevance", "generation", "summarization",
            "assistant", "citation", "corroboration", "freshness", "architecture",
            "performance", "latency", "benchmark", "analysis", "evaluation"
        ];
        const words = [];
        for (let i = 0; i < 200; i++) {
            words.push(vocabulary[i % vocabulary.length]);
        }
        document.getElementById("root").innerText = words.join(" ");
    </script>
</body>
</html>"""

    test_file = tmp_path / "js_spa_page.html"
    test_file.write_text(html_content, encoding="utf-8")

    # Extract raw text from HTML without JS execution (script is stripped)
    raw_text = extract_visible_text_bs4(html_content)

    # Render with headless Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(test_file.as_uri())
        rendered_text = page.evaluate("document.body.innerText") or ""
        browser.close()

    gap = compute_render_gap(raw_text, rendered_text)
    assert gap > 50.0, f"Expected JS-injected render gap to be above 50%, got {gap}%"
