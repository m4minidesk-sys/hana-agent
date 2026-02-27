#!/usr/bin/env python3
"""Generate mock fixtures from Python source files using AST analysis.

Usage:
    python scripts/generate_mock_fixtures.py src/yui/tools/new.py
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Any


def extract_public_interfaces(source_file: Path) -> list[dict[str, Any]]:
    """Extract public classes and functions from source file (R4: public only)."""
    try:
        tree = ast.parse(source_file.read_text())
    except Exception as e:
        print(f"Error parsing {source_file}: {e}", file=sys.stderr)
        return []
    
    interfaces = []
    # Only iterate top-level nodes to avoid picking up class methods as standalone functions
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            interfaces.append({"type": "class", "name": node.name, "methods": _extract_methods(node)})
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            interfaces.append({"type": "function", "name": node.name, "params": _extract_params(node)})
    
    return interfaces


def _extract_methods(class_node: ast.ClassDef) -> list[str]:
    """Extract public method names from class."""
    return [n.name for n in class_node.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def _extract_params(func_node: ast.FunctionDef) -> list[str]:
    """Extract parameter names from function."""
    return [arg.arg for arg in func_node.args.args if arg.arg != "self"]


def generate_stub_fixture(interface: dict[str, Any], module_path: str) -> str:
    """Generate stub fixture code (R5: stub/spy over mock)."""
    if interface["type"] == "class":
        return _generate_class_stub(interface, module_path)
    else:
        return _generate_function_stub(interface, module_path)


def _generate_class_stub(interface: dict[str, Any], module_path: str) -> str:
    """Generate stub for class."""
    name = interface["name"]
    fixture_name = f"mock_{name.lower()}"
    
    code = f'''@pytest.fixture
def {fixture_name}(fake):
    """Stub for {module_path}.{name} (R5: stub/spy pattern).
    
    Uses faker for realistic data (R6).
    """
    with patch("{module_path}.{name}") as stub:
        spec_methods = {interface["methods"]!r}
        for method in spec_methods:
            getattr(stub, method).return_value = fake.pydict()
'''
    
    code += "        yield stub\n"
    return code


def _generate_function_stub(interface: dict[str, Any], module_path: str) -> str:
    """Generate stub for function."""
    name = interface["name"]
    fixture_name = f"mock_{name}"
    
    return f'''@pytest.fixture
def {fixture_name}(fake):
    """Stub for {module_path}.{name} (R5: stub/spy pattern).
    
    Uses faker for realistic data (R6).
    """
    with patch("{module_path}.{name}") as stub:
        stub.return_value = fake.pydict()
        yield stub
'''


def generate_factory_fixture(interface: dict[str, Any]) -> str:
    """Generate factory fixture with faker (R6: realistic data)."""
    name = interface["name"]
    factory_name = f"{name}Factory"
    
    return f'''@pytest.fixture
def {factory_name.lower()}(fake):
    """Factory for {name} with faker-generated realistic data (R6).
    
    Usage: {factory_name.lower()}(field1=value1, field2=value2)
    """
    def _factory(**overrides):
        defaults = {{
            "id": fake.uuid4(),
            "name": fake.name(),
            "created_at": fake.date_time(),
        }}
        defaults.update(overrides)
        return defaults
    return _factory
'''


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate mock fixtures from Python source")
    parser.add_argument("source_file", type=Path, help="Python source file to analyze")
    parser.add_argument("--factory", action="store_true", help="Generate factory fixtures (R6)")
    args = parser.parse_args()
    
    if not args.source_file.exists():
        print(f"Error: {args.source_file} not found", file=sys.stderr)
        sys.exit(1)
    
    interfaces = extract_public_interfaces(args.source_file)
    
    if not interfaces:
        print(f"No public interfaces found in {args.source_file}", file=sys.stderr)
        sys.exit(0)
    
    module_path = ".".join(args.source_file.with_suffix("").parts)
    
    print("# Generated fixtures — add to tests/conftest.py\n")
    
    for interface in interfaces:
        if args.factory:
            print(generate_factory_fixture(interface))
        else:
            print(generate_stub_fixture(interface, module_path))


if __name__ == "__main__":
    main()
