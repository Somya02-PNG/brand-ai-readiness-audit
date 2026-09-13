import pytest
import merge_report


def test_fallback_low_severity_when_worker_returns_nothing():
    """Assert fallback low-severity finding is emitted when a worker returns nothing (None)."""
    # Test handle_worker_result directly
    fallback_findings = merge_report.handle_worker_result(None, "crawl-access-audit")
    assert isinstance(fallback_findings, list)
    assert len(fallback_findings) >= 1
    fallback = fallback_findings[0]
    assert fallback["severity"] == "low"
    assert "crawl-access-audit" in fallback["skill_source"]

    # Test collect_findings when results list contains None
    results = [None]
    collected = merge_report.collect_findings(results)
    assert len(collected) >= 1
    assert collected[0]["severity"] == "low"


def test_sequential_ids_assigned():
    """Assert F-001, F-002, F-003 IDs are assigned sequentially."""
    raw_findings = [
        {"title": "Finding A", "severity": "medium"},
        {"title": "Finding B", "severity": "critical"},
        {"title": "Finding C", "severity": "high"},
    ]
    assigned = merge_report.assign_ids(raw_findings)
    assert len(assigned) == 3
    assert assigned[0]["id"] == "F-001"
    assert assigned[1]["id"] == "F-002"
    assert assigned[2]["id"] == "F-003"


def test_findings_sorted_by_severity():
    """Assert findings are sorted by severity: critical > high > medium > low."""
    raw_findings = [
        {"title": "Finding Low", "severity": "low"},
        {"title": "Finding Critical", "severity": "critical"},
        {"title": "Finding Medium", "severity": "medium"},
        {"title": "Finding High", "severity": "high"},
    ]
    assigned = merge_report.assign_ids(raw_findings)
    severities = [f["severity"] for f in assigned]
    assert severities == ["critical", "high", "medium", "low"]


def test_beyond_problem_suggestions_populated_in_every_report():
    """Assert beyond-problem suggestions are populated in every report, tailored to the site."""
    report = merge_report.build_report("https://example.com", [])
    suggestions = report["beyond_problem_suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) >= 2

    # Verify required keys and values for each suggestion
    for s in suggestions:
        assert set(s.keys()) == {"title", "rationale", "mechanism", "priority"}
        assert isinstance(s["title"], str) and len(s["title"]) > 0
        assert isinstance(s["rationale"], str) and len(s["rationale"]) > 0
        assert isinstance(s["mechanism"], str) and len(s["mechanism"]) > 0
        assert s["priority"] in ("low", "medium", "high")

    # Verify proactive coverage of key AI-readiness concepts
    corpus = " ".join(
        f"{s['title']} {s['rationale']} {s['mechanism']}".lower() for s in suggestions
    )
    assert "faq" in corpus or "llms.txt" in corpus or "wikidata" in corpus


def test_orchestrator_run_merges_all_workers(monkeypatch):
    """Assert that the real orchestrator merge_report.run executes workers in parallel and merges findings."""
    mock_workers = [
        ("worker-crawl", "crawl.py", "worker-crawl"),
        ("worker-schema", "schema.py", "worker-schema"),
    ]
    worker_findings = {
        "worker-crawl": [
            {
                "title": "Blocked bot",
                "severity": "critical",
                "evidence": "Robots blocked",
                "suggested_action": {
                    "summary": "Fix robots, populated from config, because AI cannot crawl. Verify: curl -sI https://example.com/robots.txt.",
                    "priority": "critical",
                },
            }
        ],
        "worker-schema": [
            {
                "title": "Missing meta",
                "severity": "medium",
                "evidence": "No meta",
                "suggested_action": {
                    "summary": "Add meta, populated from content, because summaries help search. Verify: curl -s https://example.com.",
                    "priority": "medium",
                },
            }
        ],
    }

    class MockWorker:
        def __init__(self, findings):
            self._findings = findings

        def run(self, url):
            return list(self._findings)

    monkeypatch.setattr(merge_report, "WORKER_SKILLS", mock_workers)
    monkeypatch.setattr(
        merge_report,
        "_import_worker",
        lambda folder, script: MockWorker(worker_findings.get(folder, [])),
    )

    report = merge_report.run("https://example.com")
    assert isinstance(report, dict)
    assert report["site"] == "example.com"
    assert report["summary"]["total_findings"] == 2
    assert report["summary"]["critical"] == 1
    assert report["summary"]["medium"] == 1
    assert report["findings"][0]["severity"] == "critical"
    assert report["findings"][0]["id"] == "F-001"
    assert report["findings"][1]["severity"] == "medium"
    assert report["findings"][1]["id"] == "F-002"
    assert len(report["beyond_problem_suggestions"]) >= 2


def test_compute_summary_separates_coverage_gaps():
    """Assert compute_summary excludes coverage_gap: True findings from total_findings and severities, counting them under coverage_gaps."""
    findings = [
        {"title": "Real Critical", "severity": "critical"},
        {"title": "Real Medium", "severity": "medium"},
        {"title": "Real Low", "severity": "low"},
        {"title": "Worker Timeout Fallback", "severity": "low", "coverage_gap": True},
        {"title": "Worker Error Fallback", "severity": "low", "coverage_gap": True},
    ]

    summary = merge_report.compute_summary(findings)
    assert summary["total_findings"] == 3
    assert summary["critical"] == 1
    assert summary["high"] == 0
    assert summary["medium"] == 1
    assert summary["low"] == 1
    assert summary["coverage_gaps"] == 2
