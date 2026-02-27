#!/usr/bin/env python3
"""Check for unused mock fixtures in test suite.

Analyzes conftest.py and test files to detect defined but unused fixtures.
Exit code 1 if unused fixtures found.

Usage:
    python scripts/check_unused_mocks.py
"""

import ast
import re
import sys
from pathlib import Path
from typing import Any


def extract_fixtures(conftest_file: Path) -> set[str]:
    """Extract fixture names from conftest.py."""
    try:
        tree = ast.parse(conftest_file.read_text())
    except Exception as e:
        print(f"Error parsing {conftest_file}: {e}", file=sys.stderr)
        return set()
    
    fixtures = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "fixture":
                    fixtures.add(node.name)
                elif isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                    fixtures.add(node.name)
                elif isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Name) and decorator.func.id == "fixture":
                        fixtures.add(node.name)
                    elif isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "fixture":
                        fixtures.add(node.name)
    
    return fixtures


def check_fixture_usage(test_dir: Path, fixture_name: str, all_fixtures: set[str]) -> bool:
    """Check if fixture is used in any test file or by other fixtures."""
    # Check if used by other fixtures in conftest.py
    conftest_file = test_dir / "conftest.py"
    if conftest_file.exists():
        conftest_content = conftest_file.read_text()
        # Check if fixture is a parameter of another fixture
        for other_fixture in all_fixtures:
            if other_fixture != fixture_name:
                fixture_def_pattern = rf"def {other_fixture}\([^)]*\b{fixture_name}\b"
                if re.search(fixture_def_pattern, conftest_content):
                    return True
    
    for test_file in test_dir.glob("**/*.py"):
        if test_file.name == "conftest.py":
            continue
        
        content = test_file.read_text()
        
        # Check function parameters
        param_pattern = rf"def test_\w+\([^)]*\b{fixture_name}\b"
        if re.search(param_pattern, content):
            return True
        
        # Check fixture usage in test body
        if f"{fixture_name}(" in content or f"{fixture_name}." in content:
            return True
        
        # Check usefixtures decorator
        if f'usefixtures("{fixture_name}")' in content or f"usefixtures('{fixture_name}')" in content:
            return True
    
    return False


def main() -> None:
    """Main entry point."""
    test_dir = Path(__file__).parent.parent / "tests"
    conftest_file = test_dir / "conftest.py"
    
    if not conftest_file.exists():
        print(f"Error: {conftest_file} not found", file=sys.stderr)
        sys.exit(1)
    
    fixtures = extract_fixtures(conftest_file)
    
    # Exclude autouse fixtures, special fixtures, and common infrastructure fixtures
    exclude = {
        "enforce_autospec", "fake", "_pytest_", "tmp_path", "monkeypatch",
        # Infrastructure fixtures that may be used indirectly
        "mock_bedrock_client", "mock_boto3_client", "mock_slack_client",
        "mock_bedrock_model", "mock_subprocess_run", "mock_open_file",
        "tmp_workspace", "mock_agentcore_available", "mock_agentcore_unavailable"
    }
    fixtures = {f for f in fixtures if not any(ex in f for ex in exclude)}
    
    unused = []
    for fixture in fixtures:
        if not check_fixture_usage(test_dir, fixture, fixtures):
            unused.append(fixture)
    
    if unused:
        print("❌ Unused fixtures found:\n")
        for fixture in sorted(unused):
            print(f"  - {fixture}")
        print(f"\nTotal: {len(unused)} unused fixtures")
        sys.exit(1)
    else:
        print("✅ All fixtures are used")
        sys.exit(0)


if __name__ == "__main__":
    main()
