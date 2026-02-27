"""Lambda handler for AWS deployment (Phase 6 implementation).

This module defines the entry point for Yui agent running on AWS Lambda.
Supports both API Gateway (Slack Events API) and EventBridge (scheduled heartbeat).

Phase 3a: Interface definition only (TDD Red phase)
Phase 6: Full implementation
"""

from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler entry point.
    
    Args:
        event: API Gateway proxy event or EventBridge schedule event
        context: Lambda context object
    
    Returns:
        dict: API Gateway proxy response format
    
    Raises:
        NotImplementedError: Phase 6で実装予定
    """
    raise NotImplementedError("Phase 6で実装予定")
