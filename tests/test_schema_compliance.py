import re
import pytest
import merge_report

ISO_UTC_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FINDING_ID_REGEX = re.compile(r"^F-\d{3}$")
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_EFFORTS = {"low", "medium", "high"}
VALID_PRIORITIES = {"low", "medium", "high"}


def test_schema_compliance_exact_shape():
    """Assert the emitted report matches the exact specification schema."""
    sample_findings = [
        {
            "id": "temp-2",
            "title": "Blocked by robots.txt",
            "severity": "critical",
            "evidence": "GPTBot blocked at /",
            "suggested_action": {
                "summary": "Allow GPTBot in robots.txt",
                "priority": "critical",
            },
            "mechanism": "Crawlers cannot index or cite content that is blocked by robots.txt.",
            "fix_effort": "low",
            "verification": "curl -sI https://example.com/robots.txt",
        },
        {
            "id": "temp-1",
            "title": "No schema markup on product pages",
            "severity": "high",
            "evidence": "0 of 5 product pages contain Product JSON-LD",
            "suggested_action": {
                "summary": "Add Product JSON-LD to product pages",
                "priority": "high",
            },
            "mechanism": "Missing schema deprives AI models of explicit semantic entities.",
            "fix_effort": "medium",
            "verification": "curl -s https://example.com/products | grep 'application/ld+json'",
        },
        {
            "title": "Missing meta description",
            "severity": "medium",
            "evidence": "Homepage has no meta description",
            "suggested_action": {
                "summary": "Add meta description",
                "priority": "medium",
            },
            "mechanism": "Meta descriptions help search engines understand page summaries.",
            "fix_effort": "low",
            "verification": "curl -s https://example.com | grep '<meta name=\"description\"'",
        },
    ]

    sample_suggestions = [
        {
            "title": "Consider publishing an /llms.txt summary file",
            "rationale": "llms.txt provides a concise index for AI crawlers.",
            "mechanism": "Enables direct ingestion without crawl overhead.",
            "priority": "medium",
        }
    ]

    report = merge_report.build_report(
        "https://example.com",
        sample_findings,
        beyond_problem_suggestions=sample_suggestions,
    )

    # 1. Top-level keys
    assert set(report.keys()) == {
        "site",
        "audited_at",
        "summary",
        "findings",
        "beyond_problem_suggestions",
    }
    assert report["site"] == "example.com"
    assert ISO_UTC_REGEX.match(report["audited_at"]), f"audited_at is not ISO 8601 UTC with Z: {report['audited_at']}"

    # 2. Summary
    summary = report["summary"]
    assert set(summary.keys()) == {"total_findings", "critical", "high", "medium", "low"}
    assert summary["total_findings"] == 3
    assert summary["critical"] == 1
    assert summary["high"] == 1
    assert summary["medium"] == 1
    assert summary["low"] == 0

    # 3. Findings
    findings = report["findings"]
    assert len(findings) == 3

    # Check sorting: critical > high > medium > low
    severities = [f["severity"] for f in findings]
    assert severities == ["critical", "high", "medium"]

    for i, finding in enumerate(findings, start=1):
        expected_id = f"F-{i:03d}"
        assert finding["id"] == expected_id
        assert FINDING_ID_REGEX.match(finding["id"])
        assert isinstance(finding["title"], str) and finding["title"]
        assert finding["severity"] in VALID_SEVERITIES
        assert isinstance(finding["evidence"], str) and finding["evidence"]

        # suggested_action MUST be an object, not a string
        action = finding["suggested_action"]
        assert isinstance(action, dict), "suggested_action MUST be an object"
        assert set(action.keys()) == {"summary", "priority"}
        assert isinstance(action["summary"], str) and action["summary"]
        assert action["priority"] in VALID_SEVERITIES

        # mechanism, fix_effort, verification
        assert isinstance(finding["mechanism"], str) and finding["mechanism"]
        assert finding["fix_effort"] in VALID_EFFORTS
        assert isinstance(finding["verification"], str) and finding["verification"]

    # 4. beyond_problem_suggestions
    suggestions = report["beyond_problem_suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert set(suggestion.keys()) == {"title", "rationale", "mechanism", "priority"}
    assert isinstance(suggestion["title"], str) and suggestion["title"]
    assert isinstance(suggestion["rationale"], str) and suggestion["rationale"]
    assert isinstance(suggestion["mechanism"], str) and suggestion["mechanism"]
    assert suggestion["priority"] in VALID_PRIORITIES


def test_safe_defaults_on_missing_or_raw_fields():
    """Assert build_report never crashes on missing fields and emits safe defaults."""
    incomplete_findings = [
        {
            # Missing id, mechanism, fix_effort, verification; suggested_action as plain string
            "title": "Incomplete raw worker finding",
            "severity": "CRITICAL",  # uppercase test
            "evidence": "Some raw evidence",
            "suggested_action": "Fix the issue immediately.",
        },
        {
            # Completely minimal finding with invalid severity
            "title": "Minimal finding",
            "severity": "unknown_sev",
        },
    ]

    report = merge_report.build_report("https://shop.test", incomplete_findings, beyond_problem_suggestions=None)

    assert report["site"] == "shop.test"
    assert ISO_UTC_REGEX.match(report["audited_at"])
    assert isinstance(report["beyond_problem_suggestions"], list)

    findings = report["findings"]
    assert len(findings) == 2

    # F-001 from critical, F-002 from fallback low
    assert findings[0]["id"] == "F-001"
    assert findings[0]["severity"] == "critical"
    assert isinstance(findings[0]["suggested_action"], dict)
    assert findings[0]["suggested_action"]["summary"] == "Fix the issue immediately."
    assert findings[0]["suggested_action"]["priority"] == "critical"
    assert findings[0]["mechanism"]
    assert findings[0]["fix_effort"] in VALID_EFFORTS
    assert findings[0]["verification"]

    assert findings[1]["id"] == "F-002"
    assert findings[1]["severity"] == "low"
    assert isinstance(findings[1]["suggested_action"], dict)
    assert findings[1]["suggested_action"]["priority"] == "low"
    assert findings[1]["mechanism"]
    assert findings[1]["fix_effort"] in VALID_EFFORTS
    assert findings[1]["verification"]


def test_beyond_problem_suggestions_always_populated_at_least_six():
    """Assert beyond_problem_suggestions is always populated with at least 6 suggestions in every report."""
    report = merge_report.build_report("https://example.com", [], beyond_problem_suggestions=[])
    assert isinstance(report["beyond_problem_suggestions"], list)
    assert len(report["beyond_problem_suggestions"]) >= 6
    assert report["findings"] == []
    assert report["summary"]["total_findings"] == 0



def test_sorting_by_severity_then_id():
    """Assert findings are sorted by severity, then by id."""
    raw = [
        {"id": "B-002", "severity": "critical", "title": "Critical 2"},
        {"id": "B-001", "severity": "critical", "title": "Critical 1"},
        {"id": "A-002", "severity": "high", "title": "High 2"},
        {"id": "A-001", "severity": "high", "title": "High 1"},
    ]
    assigned = merge_report.assign_ids(raw)
    assert assigned[0]["id"] == "F-001"
    assert assigned[0]["title"] == "Critical 1"
    assert assigned[1]["id"] == "F-002"
    assert assigned[1]["title"] == "Critical 2"
    assert assigned[2]["id"] == "F-003"
    assert assigned[2]["title"] == "High 1"
    assert assigned[3]["id"] == "F-004"
    assert assigned[3]["title"] == "High 2"


def test_worker_findings_follow_suggested_action_pattern(repo_root):
    """Verify that every finding action across skills/*/scripts/*.py matches the required pattern."""
    import ast
    import glob

    pattern = re.compile(r".+populated from .+, because .+\. Verify: .+", re.DOTALL)
    scripts = glob.glob(str(repo_root / "skills" / "*" / "scripts" / "*.py"))
    assert len(scripts) >= 6

    for script_path in scripts:
        with open(script_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if func_name in ("make_finding", "making_finding"):
                    # Check action parameter
                    action_val = None
                    for kw in node.keywords:
                        if kw.arg == "action":
                            if isinstance(kw.value, ast.Constant):
                                action_val = kw.value.value
                            elif isinstance(kw.value, ast.JoinedStr):
                                parts = [p.value if isinstance(p, ast.Constant) else "X" for p in kw.value.values]
                                action_val = "".join(parts)
                    if action_val is None and len(node.args) >= 4:
                        arg3 = node.args[3]
                        if isinstance(arg3, ast.Constant):
                            action_val = arg3.value
                        elif isinstance(arg3, ast.JoinedStr):
                            parts = [p.value if isinstance(p, ast.Constant) else "X" for p in arg3.values]
                            action_val = "".join(parts)

                    if action_val is not None:
                        assert pattern.match(action_val), (
                            f"{script_path} line {node.lineno}: action does not match pattern: {action_val}"
                        )

                    # Check fix_effort if passed as keyword
                    kwargs = {kw.arg: kw.value for kw in node.keywords}
                    if "fix_effort" in kwargs and isinstance(kwargs["fix_effort"], ast.Constant):
                        assert kwargs["fix_effort"].value in VALID_EFFORTS, (
                            f"{script_path} line {node.lineno}: invalid fix_effort"
                        )

