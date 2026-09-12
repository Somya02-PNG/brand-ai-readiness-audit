import re
import pytest
import merge_report

ISO_UTC_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FINDING_ID_REGEX = re.compile(r"^F-\d{3}$")
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_EFFORTS = {"low", "medium", "high"}
VALID_PRIORITIES = {"low", "medium", "high"}


def test_schema_compliance_real_merge_report_output(monkeypatch):
    """
    Test schema compliance using the REAL execution pipeline of merge_report.py.
    Mocks WORKER_SKILLS with stub findings spanning all severity levels (critical, high, medium, low)
    in non-sorted order, invokes merge_report.run, and validates the aggregated report dict.
    """
    stub_findings_by_worker = {
        "stub-low-worker": [
            {
                "title": "Minor missing meta element",
                "severity": "low",
                "evidence": "Homepage lacks optional theme-color meta tag",
                "suggested_action": {
                    "summary": "Add theme-color meta tag to root layout, populated from brand style guide, because consistent UI cues improve presentation. Verify: curl -s https://example.com | grep theme-color.",
                    "priority": "low",
                },
                "mechanism": "Consistent meta elements improve presentation across mobile browsers and parsers.",
                "fix_effort": "low",
                "verification": "curl -s https://example.com | grep theme-color",
            }
        ],
        "stub-high-worker": [
            {
                "title": "Product pages lack Product schema JSON-LD",
                "severity": "high",
                "evidence": "Sampled product URLs lack schema.org Product markup",
                "suggested_action": {
                    "summary": "Add Product JSON-LD to product detail templates, populated from e-commerce database, because AI assistants require structured data to cite product offerings. Verify: curl -s https://example.com/product/1 | grep 'application/ld+json'.",
                    "priority": "high",
                },
                "mechanism": "Missing schema deprives AI models of explicit semantic entities and pricing.",
                "fix_effort": "medium",
                "verification": "curl -s https://example.com/product/1 | grep 'application/ld+json'",
            }
        ],
        "stub-critical-worker": [
            {
                "title": "Robots.txt completely blocks AI crawlers",
                "severity": "critical",
                "evidence": "robots.txt Disallow: / directive blocks GPTBot and PerplexityBot",
                "suggested_action": {
                    "summary": "Update robots.txt to allow AI search user-agents, populated from crawler registry, because disallow rules prevent retrieval engines from reading content. Verify: curl -sI https://example.com/robots.txt.",
                    "priority": "critical",
                },
                "mechanism": "Search and AI crawlers cannot index or cite content that is blocked by robots.txt.",
                "fix_effort": "low",
                "verification": "curl -sI https://example.com/robots.txt",
            }
        ],
        "stub-medium-worker": [
            {
                "title": "High internal navigation depth (>3 levels)",
                "severity": "medium",
                "evidence": "Key product documentation is nested 4 levels deep from root",
                "suggested_action": {
                    "summary": "Flatten documentation hierarchy, populated from top-level navigation, because shallow architectures reduce crawler hop latency. Verify: curl -s https://example.com/sitemap.xml.",
                    "priority": "medium",
                },
                "mechanism": "Excessive nesting depth creates crawl friction and increases bounce rate for arriving visitors.",
                "fix_effort": "medium",
                "verification": "curl -s https://example.com/sitemap.xml",
            }
        ],
    }

    class StubWorkerModule:
        def __init__(self, findings):
            self._findings = findings

        def run(self, url):
            return list(self._findings)

    # Intentionally provide workers in non-sorted severity order (low, high, critical, medium)
    # to verify that merge_report.run properly sorts them critical > high > medium > low.
    mocked_worker_skills = [
        ("stub-low-worker", "check_low.py", "stub-low-worker"),
        ("stub-high-worker", "check_high.py", "stub-high-worker"),
        ("stub-critical-worker", "check_critical.py", "stub-critical-worker"),
        ("stub-medium-worker", "check_medium.py", "stub-medium-worker"),
    ]

    monkeypatch.setattr(merge_report, "WORKER_SKILLS", mocked_worker_skills)
    monkeypatch.setattr(
        merge_report,
        "_import_worker",
        lambda folder, script: StubWorkerModule(stub_findings_by_worker.get(folder, [])),
    )

    # Invoke the real merge_report entrypoint
    report = merge_report.run("https://example.com")

    # 1. Top-level keys: site, audited_at, summary, findings, beyond_problem_suggestions
    expected_top_keys = {"site", "audited_at", "summary", "findings", "beyond_problem_suggestions"}
    assert set(report.keys()) == expected_top_keys, f"Top-level keys mismatch: {set(report.keys())}"
    assert report["site"] == "example.com"
    assert ISO_UTC_REGEX.match(report["audited_at"]), f"audited_at must be ISO 8601 UTC with trailing Z: {report['audited_at']}"

    # 2. summary has total_findings, critical, high, medium, low
    summary = report["summary"]
    expected_summary_keys = {"total_findings", "critical", "high", "medium", "low"}
    assert set(summary.keys()) == expected_summary_keys, f"Summary keys mismatch: {set(summary.keys())}"
    assert summary["total_findings"] == 4
    assert summary["critical"] == 1
    assert summary["high"] == 1
    assert summary["medium"] == 1
    assert summary["low"] == 1

    # 3. every finding has id, title, severity, evidence, suggested_action (object), mechanism, fix_effort, verification
    findings = report["findings"]
    assert len(findings) == 4

    expected_finding_keys = {
        "id",
        "title",
        "severity",
        "evidence",
        "suggested_action",
        "mechanism",
        "fix_effort",
        "verification",
    }

    # 4. findings sorted critical > high > medium > low
    severities = [f["severity"] for f in findings]
    assert severities == ["critical", "high", "medium", "low"], f"Findings not sorted by severity: {severities}"

    # 5. IDs are sequential F-001, F-002, ...
    for i, finding in enumerate(findings, start=1):
        expected_id = f"F-{i:03d}"
        assert finding["id"] == expected_id, f"Finding index {i} has id {finding.get('id')}, expected {expected_id}"
        assert FINDING_ID_REGEX.match(finding["id"])

        # Check all required finding keys are present
        missing_keys = expected_finding_keys - set(finding.keys())
        assert not missing_keys, f"Finding {finding['id']} missing keys: {missing_keys}"

        assert isinstance(finding["title"], str) and finding["title"]
        assert finding["severity"] in VALID_SEVERITIES
        assert isinstance(finding["evidence"], str) and finding["evidence"]

        # suggested_action MUST be an object (dict), not a string
        action = finding["suggested_action"]
        assert isinstance(action, dict), f"Finding {finding['id']} suggested_action must be an object, got {type(action)}"
        assert "summary" in action and "priority" in action
        assert isinstance(action["summary"], str) and action["summary"]
        assert action["priority"] in VALID_SEVERITIES

        # mechanism, fix_effort, verification
        assert isinstance(finding["mechanism"], str) and finding["mechanism"]
        assert finding["fix_effort"] in VALID_EFFORTS
        assert isinstance(finding["verification"], str) and finding["verification"]

    # 6. beyond_problem_suggestions is a non-empty list
    suggestions = report["beyond_problem_suggestions"]
    assert isinstance(suggestions, list), "beyond_problem_suggestions must be a list"
    assert len(suggestions) > 0, "beyond_problem_suggestions must be non-empty"

    for suggestion in suggestions:
        assert isinstance(suggestion, dict)
        expected_suggestion_keys = {"title", "rationale", "mechanism", "priority"}
        missing_s_keys = expected_suggestion_keys - set(suggestion.keys())
        assert not missing_s_keys, f"Suggestion missing keys: {missing_s_keys}"
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
