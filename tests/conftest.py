import sys
from pathlib import Path
import pytest

# Ensure repo root and script folders are on sys.path for direct module imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "skills" / "crawl-access-audit" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "audit-orchestrator" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "render-readability-audit" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "structured-data-audit" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "freshness-corroboration-audit" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "entity-clarity-audit" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "skills" / "engagement-audit" / "scripts"))


@pytest.fixture
def repo_root() -> Path:
    """Fixture returning the repository root directory as a Path."""
    return Path(__file__).parent.parent
