#!/usr/bin/env python3
"""
skills/audit-orchestrator/scripts/beyond_problem.py

Proactive beyond-problem suggestions are dynamically generated in merge_report.py
via generate_proactive_findings() tailored to site context.
"""

from typing import Optional


def get_beyond_problem_suggestions(url: str = "", findings: Optional[list] = None) -> list[dict]:
    """
    Deprecated: Delegates to merge_report.generate_beyond_problem_suggestions.
    Kept for backward compatibility.
    """
    try:
        from merge_report import generate_beyond_problem_suggestions
    except ImportError:
        from skills.audit_orchestrator.scripts.merge_report import generate_beyond_problem_suggestions
    return generate_beyond_problem_suggestions(url, findings)


# Alias for backward compatibility
generate_beyond_problem_suggestions = get_beyond_problem_suggestions

