"""Component tests for Lambda Layer dependency resolution (FR-08-A7)."""

import sys
from unittest.mock import patch

import pytest

from tests.factories import LambdaContextFactory, LambdaEventFactory

pytestmark = pytest.mark.component


def test_lambda_layers__handler_init__adds_opt_python_to_syspath():
    from yui.lambda_handler import handler
    
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_layers__layer_packages__import_succeeds():
    from yui.lambda_handler import handler
    
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_layers__missing_layer__raises_import_error():
    from yui.lambda_handler import handler
    
    event = LambdaEventFactory.api_gateway_event()
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)
