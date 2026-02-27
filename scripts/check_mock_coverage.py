#!/usr/bin/env python3
"""Check mock coverage for external dependencies in test files.

Detects unmocked external dependencies (boto3, slack_sdk, httpx, etc.) and reports them.
Exit code 1 if unmocked dependencies found.

Usage:
    python scripts/check_mock_coverage.py
"""

import ast
import sys
from pathlib import Path
from typing import Any


EXTERNAL_DEPS = {
    "boto3", "slack_sdk", "httpx", "requests", "openai", "anthropic",
    "subprocess", "os.system", "os.popen", "socket", "urllib"
}


def extract_imports(test_file: Path) -> set[str]:
    """Extract imported modules from test file."""
    try:
        tree = ast.parse(test_file.read_text())
    except Exception as e:
        print(f"Error parsing {test_file}: {e}", file=sys.stderr)
        return set()
    
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    
    return imports


def check_mocked(test_file: Path, imported_module: str) -> bool:
    """Check if imported module is mocked in test file."""
    content = test_file.read_text()
    
    # Check if it's an integration/e2e test (allowed to use real APIs)
    if "pytest.mark.integration" in content or "pytest.mark.e2e" in content:
        return True
    
    # Check for patch/MagicMock/Mock usage
    mock_patterns = [
        f'patch("{imported_module}',
        f"patch('{imported_module}",
        f'patch("src.yui.{imported_module}',
        f"patch('src.yui.{imported_module}",
        f'patch("yui.{imported_module}',
        f"patch('yui.{imported_module}",
        f"mock_{imported_module}",
        f"@patch",
        f"MagicMock(spec={imported_module}",
        f"Mock(spec={imported_module}",
        # Check for fixture parameters that mock the module
        f"mock_{imported_module.replace('.', '_')}",
    ]
    
    return any(pattern in content for pattern in mock_patterns)


def check_test_file(test_file: Path) -> dict[str, list[str]]:
    """Check single test file for unmocked external dependencies."""
    imports = extract_imports(test_file)
    external_imports = imports & EXTERNAL_DEPS
    
    # Special case: tests that legitimately use raw sockets (IPC, etc.)
    # Detected by checking if socket is used as a test subject, not as external dependency
    if "socket" in external_imports:
        content = test_file.read_text()
        # socket used as test subject (mocking the socket itself) is OK
        if "mock_socket" in content or "patch" in content and "socket" in content:
            external_imports.discard("socket")
    
    unmocked = []
    for module in external_imports:
        if not check_mocked(test_file, module):
            unmocked.append(module)
    
    return {"file": str(test_file), "unmocked": unmocked} if unmocked else {}


def main() -> None:
    """Main entry point."""
    test_dir = Path(__file__).parent.parent / "tests"
    test_files = list(test_dir.glob("test_*.py"))
    
    unmocked_report = []
    for test_file in test_files:
        result = check_test_file(test_file)
        if result:
            unmocked_report.append(result)
    
    if unmocked_report:
        print("❌ Unmocked external dependencies found:\n")
        for item in unmocked_report:
            print(f"  {item['file']}:")
            for dep in item["unmocked"]:
                print(f"    - {dep}")
        print(f"\nTotal: {len(unmocked_report)} files with unmocked dependencies")
        sys.exit(1)
    else:
        print("✅ All external dependencies are mocked")
        sys.exit(0)


if __name__ == "__main__":
    main()
