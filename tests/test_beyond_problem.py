import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "skills" / "audit-orchestrator" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from beyond_problem import get_beyond_problem_suggestions

VALID_PRIORITIES = {"low", "medium", "high"}
REQUIRED_KEYS = {"title", "rationale", "mechanism", "priority"}


def test_beyond_problem_suggestions_structure_and_counts():
    """
    Test get_beyond_problem_suggestions:
    - Returns a list with proactive entries
    - Every entry contains: title, rationale, mechanism, priority
    - Every priority value is in {'low', 'medium', 'high'}
    """
    suggestions = get_beyond_problem_suggestions("https://example.com")

    # 1. Assert it returns a list with entries
    assert isinstance(suggestions, list), f"Expected list, got {type(suggestions).__name__}"
    assert len(suggestions) >= 2, f"Expected at least 2 suggestions, got {len(suggestions)}"

    # 2 & 3. Assert every entry has keys and valid priority
    for i, entry in enumerate(suggestions):
        assert isinstance(entry, dict), f"Entry {i} must be a dict, got {type(entry).__name__}"

        # Assert every entry has keys: title, rationale, mechanism, priority
        missing_keys = REQUIRED_KEYS - set(entry.keys())
        assert not missing_keys, f"Entry {i} ({entry.get('title')}) missing required keys: {missing_keys}"

        # Assert non-empty strings for title, rationale, mechanism
        assert isinstance(entry["title"], str) and entry["title"].strip(), f"Entry {i} title must be non-empty string"
        assert isinstance(entry["rationale"], str) and entry["rationale"].strip(), f"Entry {i} rationale must be non-empty string"
        assert isinstance(entry["mechanism"], str) and entry["mechanism"].strip(), f"Entry {i} mechanism must be non-empty string"

        # Assert priority values are in {"low", "medium", "high"}
        assert entry["priority"] in VALID_PRIORITIES, f"Entry {i} priority '{entry['priority']}' not in {VALID_PRIORITIES}"
