"""PB-4: template source must not import Level-0 packages directly."""

import ast
import pathlib

import pytest

PROHIBITED_IMPORTS = ("agenticstar", "agenticstar_agentcore", "mediator")


def _scan_imports(filepath: pathlib.Path) -> list[str]:
    tree = ast.parse(filepath.read_text(), filename=str(filepath))
    violations = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if any(name == prefix or name.startswith(f"{prefix}.") for prefix in PROHIBITED_IMPORTS):
                violations.append(f"{filepath}:{node.lineno} — prohibited import {name}")
    return violations


def test_no_prohibited_imports_in_src() -> None:
    src_dir = pathlib.Path(__file__).parents[2] / "src"
    if not src_dir.exists():
        pytest.skip("src/ directory not found")
    violations = []
    for filepath in src_dir.rglob("*.py"):
        violations.extend(_scan_imports(filepath))
    assert violations == [], "Import isolation violations:\n" + "\n".join(violations)
