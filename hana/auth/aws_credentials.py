"""HANA AWS credential validation.

Validates that the current environment has usable AWS credentials
for Bedrock API calls, using the standard boto3 credential chain.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_aws_credentials(config: dict[str, Any]) -> dict[str, Any]:
    """Validate that AWS credentials are available and return identity info.

    Uses the standard boto3 credential resolution:
      1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
      2. AWS config files (~/.aws/credentials, ~/.aws/config)
      3. IAM Instance Profile (EC2/ECS)
      4. SSO cache (~/.aws/sso/cache/*)

    Args:
        config: HANA configuration dictionary.

    Returns:
        Dictionary with ``valid`` (bool), ``account`` (str), ``arn`` (str),
        ``region`` (str), and optionally ``error`` (str).
    """
    try:
        import boto3

        region = config.get("agent", {}).get("region", "us-east-1")
        session = boto3.Session(region_name=region)
        sts = session.client("sts")
        identity = sts.get_caller_identity()

        result = {
            "valid": True,
            "account": identity.get("Account", ""),
            "arn": identity.get("Arn", ""),
            "region": region,
        }
        logger.info(
            "AWS credentials valid — account=%s, region=%s",
            result["account"],
            result["region"],
        )
        return result

    except ImportError:
        msg = "boto3 is not installed — run: pip install boto3"
        logger.error(msg)
        return {"valid": False, "error": msg}
    except Exception as exc:
        msg = f"AWS credential validation failed: {exc}"
        logger.error(msg)
        return {"valid": False, "error": msg}


def check_bedrock_access(config: dict[str, Any]) -> dict[str, Any]:
    """Quick check that Bedrock Converse API is reachable.

    Sends a minimal converse request to verify model access.

    Args:
        config: HANA configuration dictionary.

    Returns:
        Dictionary with ``accessible`` (bool) and optionally ``error`` (str).
    """
    try:
        import boto3

        region = config.get("agent", {}).get("region", "us-east-1")
        model_id = config.get("agent", {}).get(
            "model_id", "us.anthropic.claude-sonnet-4-20250514"
        )

        session = boto3.Session(region_name=region)
        client = session.client("bedrock-runtime", region_name=region)

        # Minimal converse call to verify access
        response = client.converse(
            modelId=model_id,
            messages=[
                {"role": "user", "content": [{"text": "hi"}]},
            ],
            inferenceConfig={"maxTokens": 10},
        )
        return {"accessible": True, "model_id": model_id}

    except Exception as exc:
        msg = f"Bedrock access check failed: {exc}"
        logger.warning(msg)
        return {"accessible": False, "error": msg}
