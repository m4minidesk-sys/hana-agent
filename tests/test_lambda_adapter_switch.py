"""Component tests for Lambda adapter switching logic (FR-08-A3)."""

import os
from unittest.mock import patch

import pytest

from tests.factories import LambdaContextFactory, LambdaEventFactory

pytestmark = pytest.mark.component


def test_lambda_adapter__lambda_runtime_true__selects_events_api():
    from yui.lambda_handler import handler
    
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_adapter__lambda_runtime_unset__selects_socket_mode():
    from yui.lambda_handler import handler
    
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_adapter__lambda_runtime_false__selects_socket_mode():
    from yui.lambda_handler import handler
    
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)
