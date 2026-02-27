#!/usr/bin/env python3
"""Mock drift detection script for yui-agent.

Usage:
    python scripts/check_mock_drift.py --dry-run
    python scripts/check_mock_drift.py --create-issue
    python scripts/check_mock_drift.py --api bedrock --dry-run
"""

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


def extract_mock_structure(test_file: Path) -> dict[str, dict]:
    """Extract mock response structure from test file using AST."""
    try:
        tree = ast.parse(test_file.read_text())
    except Exception as e:
        print(f"Error parsing {test_file}: {e}", file=sys.stderr)
        return {}
    
    mocks = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "return_value":
                    if isinstance(node.value, ast.Dict):
                        mock_name = ast.unparse(target.value) if hasattr(ast, "unparse") else "unknown"
                        mocks[mock_name] = _extract_dict_keys(node.value)
    
    return mocks


def _extract_dict_keys(node: ast.Dict) -> dict[str, str]:
    """Extract keys from dict AST node."""
    keys = {}
    for k, v in zip(node.keys, node.values):
        if k is None:
            continue
        key_name = k.value if isinstance(k, ast.Constant) else ast.unparse(k) if hasattr(ast, "unparse") else "unknown"
        if isinstance(v, ast.Dict):
            keys[key_name] = "dict"
        elif isinstance(v, ast.List):
            keys[key_name] = "list"
        else:
            keys[key_name] = "value"
    return keys


def get_real_api_structure(api_name: str) -> dict[str, dict]:
    """Call real API and extract response structure."""
    if api_name == "bedrock":
        return _get_bedrock_structure()
    elif api_name == "slack":
        return _get_slack_structure()
    elif api_name == "boto3":
        return _get_boto3_structure()
    else:
        return {}


def _get_bedrock_structure() -> dict[str, dict]:
    """Get Bedrock API response structure."""
    try:
        import boto3
        client = boto3.client("bedrock-runtime", region_name="us-east-1")
        response = client.converse(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hi"}]}],
        )
        return {"converse": _extract_response_keys(response)}
    except Exception as e:
        print(f"Error calling Bedrock API: {e}", file=sys.stderr)
        return {}


def _get_slack_structure() -> dict[str, dict]:
    """Get Slack API response structure."""
    try:
        import os
        from slack_sdk import WebClient
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            print("SLACK_BOT_TOKEN not set", file=sys.stderr)
            return {}
        client = WebClient(token=token)
        response = client.auth_test()
        return {"auth_test": _extract_response_keys(response.data)}
    except Exception as e:
        print(f"Error calling Slack API: {e}", file=sys.stderr)
        return {}


def _get_boto3_structure() -> dict[str, dict]:
    """Get boto3 API response structure."""
    try:
        import boto3
        client = boto3.client("cloudformation", region_name="us-east-1")
        response = client.describe_stacks()
        return {"describe_stacks": _extract_response_keys(response)}
    except Exception as e:
        print(f"Error calling boto3 API: {e}", file=sys.stderr)
        return {}


def _extract_response_keys(response: Any) -> dict[str, str]:
    """Extract keys from response object."""
    if isinstance(response, dict):
        keys = {}
        for k, v in response.items():
            if isinstance(v, dict):
                keys[k] = "dict"
            elif isinstance(v, list):
                keys[k] = "list"
            else:
                keys[k] = "value"
        return keys
    return {}


def compare_structures(mock: dict[str, dict], real: dict[str, dict]) -> dict[str, list]:
    """Compare mock and real structures, return drift report."""
    drift = {}
    
    for api_name, real_keys in real.items():
        mock_keys = mock.get(api_name, {})
        
        missing_in_mock = set(real_keys.keys()) - set(mock_keys.keys())
        extra_in_mock = set(mock_keys.keys()) - set(real_keys.keys())
        
        if missing_in_mock or extra_in_mock:
            drift[api_name] = {
                "missing_in_mock": list(missing_in_mock),
                "extra_in_mock": list(extra_in_mock),
            }
    
    return drift


def generate_issue_body(drift_report: dict[str, list]) -> str:
    """Generate GitHub Issue body from drift report."""
    if not drift_report:
        return "No mock drift detected."
    
    body = "# Mock Drift Detected\n\n"
    body += "The following mocks have drifted from real API responses:\n\n"
    
    for api_name, drift in drift_report.items():
        body += f"## {api_name}\n\n"
        if drift["missing_in_mock"]:
            body += f"**Missing in mock:** {', '.join(drift['missing_in_mock'])}\n\n"
        if drift["extra_in_mock"]:
            body += f"**Extra in mock:** {', '.join(drift['extra_in_mock'])}\n\n"
    
    body += "\n**Action Required:** Update mock responses to match real API structure.\n"
    return body


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Detect mock drift from real APIs")
    parser.add_argument("--dry-run", action="store_true", help="Print drift report without creating issue")
    parser.add_argument("--create-issue", action="store_true", help="Create GitHub issue for drift")
    parser.add_argument("--api", choices=["bedrock", "slack", "boto3"], help="Check specific API only")
    args = parser.parse_args()
    
    # Extract mock structures from test files
    test_dir = Path(__file__).parent.parent / "tests"
    mock_structures = {}
    for test_file in test_dir.glob("test_*.py"):
        mocks = extract_mock_structure(test_file)
        mock_structures.update(mocks)
    
    # Get real API structures
    apis = [args.api] if args.api else ["bedrock", "slack", "boto3"]
    real_structures = {}
    for api in apis:
        real_structures.update(get_real_api_structure(api))
    
    # Compare structures
    drift_report = compare_structures(mock_structures, real_structures)
    
    # Generate output
    issue_body = generate_issue_body(drift_report)
    
    if args.dry_run:
        print(issue_body)
    elif args.create_issue:
        print("GitHub issue creation not implemented (requires gh CLI or API token)")
        print(issue_body)
    else:
        print("Use --dry-run or --create-issue")
        sys.exit(1)


if __name__ == "__main__":
    main()
