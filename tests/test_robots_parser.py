import pytest
from pathlib import Path
import check_access


def test_no_robots_txt_all_allowed():
    """Test that when there is no robots.txt (simulated 404 / None), all crawlers are allowed."""
    rp = check_access.parse_robots_txt(None, "https://example.com")
    assert rp.can_fetch("GPTBot", "https://example.com/")
    assert rp.can_fetch("GPTBot", "https://example.com/products")
    assert rp.can_fetch("Googlebot", "https://example.com/admin")
    assert rp.can_fetch("ClaudeBot", "https://example.com/blog")


def test_robots_block_gptbot(repo_root: Path):
    """Test robots.txt with User-agent: GPTBot\\nDisallow: / blocks GPTBot but allows other agents."""
    fixture_path = repo_root / "tests" / "fixtures" / "robots_block_gptbot.txt"
    robots_content = fixture_path.read_text(encoding="utf-8")

    rp = check_access.parse_robots_txt(robots_content, "https://example.com")
    assert not rp.can_fetch("GPTBot", "https://example.com/")
    assert not rp.can_fetch("GPTBot", "https://example.com/about")
    assert rp.can_fetch("Googlebot", "https://example.com/")


def test_robots_partial_block(repo_root: Path):
    """Test robots.txt with User-agent: *\\nDisallow: /admin blocks /admin but allows /."""
    fixture_path = repo_root / "tests" / "fixtures" / "robots_partial_block.txt"
    robots_content = fixture_path.read_text(encoding="utf-8")

    rp = check_access.parse_robots_txt(robots_content, "https://example.com")
    assert not rp.can_fetch("GPTBot", "https://example.com/admin")
    assert not rp.can_fetch("Googlebot", "https://example.com/private/data")
    assert rp.can_fetch("GPTBot", "https://example.com/")
    assert rp.can_fetch("GPTBot", "https://example.com/products")


def test_robots_sitemap_detected(repo_root: Path):
    """Test robots.txt with a Sitemap: directive detects the sitemap URL."""
    fixture_path = repo_root / "tests" / "fixtures" / "robots_partial_block.txt"
    robots_content = fixture_path.read_text(encoding="utf-8")

    sitemap_url = check_access.extract_sitemap_from_robots(robots_content)
    assert sitemap_url == "https://example.com/sitemap.xml"

    # Also test direct string with Sitemap directive
    direct_content = "User-agent: *\nAllow: /\nSitemap: https://testdomain.org/sitemap_index.xml"
    detected = check_access.extract_sitemap_from_robots(direct_content)
    assert detected == "https://testdomain.org/sitemap_index.xml"
