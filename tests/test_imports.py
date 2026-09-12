import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_all_skill_scripts_import_cleanly():
    failures = []
    for script in REPO_ROOT.glob("skills/*/scripts/*.py"):
        if script.name.startswith("_"):
            continue
        sys.path.insert(0, str(script.parent))
        module_name = script.stem
        try:
            importlib.import_module(module_name)
        except Exception as e:
            failures.append(f"{script}: {type(e).__name__}: {e}")
        finally:
            sys.path.pop(0)
    assert not failures, "Import failures:\n" + "\n".join(failures)
