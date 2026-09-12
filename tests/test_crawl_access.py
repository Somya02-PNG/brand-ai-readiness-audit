from pathlib import Path
from typing import Optional
import pytest
import check_access


class MockResponse:
    def __init__(self, status_code: int = 200, text: str = "", headers: Optional[dict] = None):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"


def test_no_robots_txt_404_treated_as_all_allowed_in_evidence(monkeypatch):
    """Test that HTTP 404 on robots.txt is treated as 'all allowed' and recorded in evidence."""
    mock_404 = MockResponse(status_code=404, text="Not Found")
    monkeypatch.setattr(check_access, "safe_get", lambda url, **kwargs: mock_404)

    findings, rp = check_access.audit_robots("https://example.com")

    # Verify all crawlers allowed
    assert rp is not None
    assert rp.allow_all is True
    assert rp.can_fetch("GPTBot", "https://example.com/")
    assert rp.can_fetch("ClaudeBot", "https://example.com/products")
    assert rp.can_fetch("PerplexityBot", "https://example.com/about")

    # Verify evidence records 'all allowed'
    robots_findings = [f for f in findings if f["title"] == "robots.txt not found or unreachable"]
    assert len(robots_findings) == 1
    assert "all allowed" in robots_findings[0]["evidence"].lower()


def test_no_robots_txt_connection_error_treated_as_all_allowed_in_evidence(monkeypatch):
    """Test that connection error on robots.txt is treated as 'all allowed' and recorded in evidence."""
    monkeypatch.setattr(check_access, "safe_get", lambda url, **kwargs: None)

    findings, rp = check_access.audit_robots("https://example.com")

    # Verify all crawlers allowed
    assert rp is not None
    assert rp.allow_all is True
    assert rp.can_fetch("GPTBot", "https://example.com/")
    assert rp.can_fetch("OAI-SearchBot", "https://example.com/")

    # Verify evidence records 'all allowed' and 'connection error'
    robots_findings = [f for f in findings if f["title"] == "robots.txt not found or unreachable"]
    assert len(robots_findings) == 1
    assert "all allowed" in robots_findings[0]["evidence"].lower()
    assert "connection error" in robots_findings[0]["evidence"].lower()


def test_cloudflare_403_emits_diagnostic(repo_root: Path, monkeypatch):
    """Test that Cloudflare/bot-wall 403 emits 'Automated access blocked — manual review needed' diagnostic."""
    fixture_path = repo_root / "tests" / "fixtures" / "cloudflare_403.html"
    cf_html = fixture_path.read_text(encoding="utf-8")

    cf_resp = MockResponse(
        status_code=403,
        text=cf_html,
        headers={"Server": "Cloudflare", "cf-ray": "8c1234567890abcd"},
    )
    monkeypatch.setattr(check_access, "safe_get", lambda url, **kwargs: cf_resp)

    findings, _ = check_access.audit_robots("https://example.com")

    diag_findings = [
        f for f in findings
        if f["title"] == "Automated access blocked — manual review needed"
    ]
    assert len(diag_findings) == 1
    diag = diag_findings[0]
    assert diag["severity"] == "low"
    assert "cloudflare" in diag["evidence"].lower() or "bot-wall" in diag["evidence"].lower()
    assert "manual review needed" in diag["evidence"].lower()


def test_non_english_page_no_crash(repo_root: Path, monkeypatch):
    """Test that parsing and link extraction on a non-English page does not crash."""
    fixture_path = repo_root / "tests" / "fixtures" / "page_non_english.html"
    html = fixture_path.read_text(encoding="utf-8")

    # Test extract_internal_links directly with non-English characters
    links = check_access.extract_internal_links(html, "https://example.com", "https://example.com")
    assert len(links) >= 6
    assert any("ソフトウェア" in l for l in links)
    assert any("produkte" in l or "ru" in l for l in links)

    # Test audit_http_status with non-English page
    resp = MockResponse(status_code=200, text=html)
    monkeypatch.setattr(check_access, "CRAWL_DELAY", 0)
    monkeypatch.setattr(check_access, "safe_get", lambda url, **kwargs: resp)
    monkeypatch.setattr(check_access, "get_redirect_chain", lambda url: [(url, 200)])

    findings, statuses = check_access.audit_http_status("https://example.com", "https://example.com")
    assert isinstance(findings, list)
    assert len(statuses) > 0


def test_over_100_links_page_caps_at_20_and_states_cap_in_evidence(repo_root: Path, monkeypatch):
    """Test that a page with >100 links caps fetches at 20 and states the cap in evidence."""
    fixture_path = repo_root / "tests" / "fixtures" / "page_many_links.html"
    html = fixture_path.read_text(encoding="utf-8")

    def mock_safe_get(url, **kwargs):
        if url == "https://example.com":
            return MockResponse(status_code=200, text=html)
        return MockResponse(status_code=200, text="<html><body>Subpage</body></html>")

    monkeypatch.setattr(check_access, "CRAWL_DELAY", 0)
    monkeypatch.setattr(check_access, "safe_get", mock_safe_get)
    monkeypatch.setattr(check_access, "get_redirect_chain", lambda url: [(url, 200)])

    findings, page_statuses = check_access.audit_http_status("https://example.com", "https://example.com")

    # Assert fetches capped at 20
    assert len(page_statuses) <= 20
    assert len(page_statuses) == 20

    # Assert evidence states the cap
    cap_findings = [f for f in findings if "capped at 20" in f["evidence"].lower()]
    assert len(cap_findings) >= 1
    assert ">100 links" in cap_findings[0]["evidence"]
    assert cap_findings[0]["severity"] == "low"


def test_crawler_matching_case_insensitive_and_wildcard():
    """Test that every crawler in the registry is matched case-insensitively and handles wildcard *."""
    all_crawlers = [agent for agent, _ in check_access.AI_CRAWLERS]

    # 1. Test case-insensitivity with lowercase directives
    lower_robots = "\n".join([f"User-agent: {c.lower()}\nDisallow: /" for c in all_crawlers])
    rp_lower = check_access.parse_robots_txt(lower_robots, "https://example.com")
    for c in all_crawlers:
        assert not rp_lower.can_fetch(c, "https://example.com/"), f"{c} should be blocked by lowercase directive"

    # 2. Test case-insensitivity with UPPERCASE directives
    upper_robots = "\n".join([f"User-agent: {c.upper()}\nDisallow: /" for c in all_crawlers])
    rp_upper = check_access.parse_robots_txt(upper_robots, "https://example.com")
    for c in all_crawlers:
        assert not rp_upper.can_fetch(c, "https://example.com/"), f"{c} should be blocked by uppercase directive"

    # 3. Test wildcard User-agent: * blocks all by default
    wildcard_robots = "User-agent: *\nDisallow: /"
    rp_wildcard = check_access.parse_robots_txt(wildcard_robots, "https://example.com")
    for c in all_crawlers:
        assert not rp_wildcard.can_fetch(c, "https://example.com/"), f"{c} should be blocked by wildcard *"

    # 4. Test wildcard with specific exception
    exception_robots = "User-agent: *\nDisallow: /\n\nUser-agent: OAI-SearchBot\nAllow: /"
    rp_exception = check_access.parse_robots_txt(exception_robots, "https://example.com")
    assert rp_exception.can_fetch("OAI-SearchBot", "https://example.com/")
    assert not rp_exception.can_fetch("GPTBot", "https://example.com/")
