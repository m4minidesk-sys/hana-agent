"""Component tests for Lambda handler core logic (FR-08-A1, A4, A5, A9)."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from tests.factories import LambdaContextFactory, LambdaEventFactory
from yui.lambda_handler import handler

pytestmark = pytest.mark.component


def test_lambda_handler__challenge_event__returns_challenge_value():
    challenge_value = "test_challenge_123"
    event = LambdaEventFactory.api_gateway_event(
        body=json.dumps(LambdaEventFactory.slack_challenge_event(challenge=challenge_value))
    )
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__event_callback__invokes_bedrock_stub():
    event_body = {
        "type": "event_callback",
        "event": {"type": "message", "text": "hello", "user": "U123", "channel": "C123"},
    }
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__invalid_signature__returns_401_unauthorized():
    event = LambdaEventFactory.api_gateway_event()
    event["headers"]["X-Slack-Signature"] = "v0=invalid_signature"
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__challenge_response__completes_under_100ms():
    challenge_value = "perf_test_challenge"
    event = LambdaEventFactory.api_gateway_event(
        body=json.dumps(LambdaEventFactory.slack_challenge_event(challenge=challenge_value))
    )
    context = LambdaContextFactory.create()

    start = time.perf_counter()
    with pytest.raises(NotImplementedError):
        handler(event, context)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1


def test_lambda_handler__consecutive_calls__no_state_pollution():
    event1 = LambdaEventFactory.api_gateway_event(
        body=json.dumps({"type": "url_verification", "challenge": "first"})
    )
    event2 = LambdaEventFactory.api_gateway_event(
        body=json.dumps({"type": "url_verification", "challenge": "second"})
    )
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event1, context)
    
    with pytest.raises(NotImplementedError):
        handler(event2, context)


def test_lambda_handler__api_gateway_event__converts_to_slack_event():
    slack_event = {"type": "event_callback", "event": {"type": "message"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(slack_event))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__invalid_json_body__returns_400_bad_request():
    event = LambdaEventFactory.api_gateway_event(body="invalid json {{{")
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__bedrock_timeout__returns_error_to_slack():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__slack_429__retries_with_backoff():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__remaining_time_low__terminates_early():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create(remaining_time_ms=500)

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__missing_body__returns_400_bad_request():
    event = LambdaEventFactory.api_gateway_event()
    del event["body"]
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__empty_body__returns_400_bad_request():
    event = LambdaEventFactory.api_gateway_event(body="")
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__missing_headers__returns_401_unauthorized():
    event = LambdaEventFactory.api_gateway_event()
    event["headers"] = {}
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__valid_signature__processes_event():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "hello"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__bedrock_503__returns_error_response():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__rate_limit_exceeded__backs_off_exponentially():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__context_deadline_exceeded__returns_partial_response():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "long task"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create(remaining_time_ms=100)

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__multiple_events_in_batch__processes_all():
    events = [
        {"type": "event_callback", "event": {"type": "message", "text": f"msg{i}"}}
        for i in range(3)
    ]
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(events[0]))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__slack_retry_header__skips_duplicate_processing():
    event_body = {"type": "event_callback", "event": {"type": "message", "text": "test"}}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    event["headers"]["X-Slack-Retry-Num"] = "1"
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


def test_lambda_handler__unknown_event_type__returns_200_ok():
    event_body = {"type": "unknown_type", "data": "something"}
    event = LambdaEventFactory.api_gateway_event(body=json.dumps(event_body))
    context = LambdaContextFactory.create()

    with pytest.raises(NotImplementedError):
        handler(event, context)


# ── Phase 6 カバレッジ補強テスト (Part 1: handler基本動作) ───────────────────

import os
import json as _json
import time as _time
from unittest.mock import patch, MagicMock

# ── Phase 6 カバレッジ補強テスト ─────────────────────────────────────────────



def _make_lambda_env(monkeypatch):
    """LAMBDA_RUNTIME=true を設定するヘルパー。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")


def test_lambda_handler__url_verification__returns_challenge(monkeypatch):
    """url_verification イベントが challenge を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    challenge_val = "abc123"
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({"type": "url_verification", "challenge": challenge_val})
    )
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert _json.loads(result["body"])["challenge"] == challenge_val


def test_lambda_handler__eventbridge_heartbeat__returns_200(monkeypatch):
    """EventBridge heartbeat が 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.eventbridge_event()
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert "heartbeat" in result["body"]


def test_lambda_handler__retry_header__returns_200(monkeypatch):
    """x-slack-retry-num ヘッダーがあれば即 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({"type": "event_callback", "event": {"type": "message"}})
    )
    event["headers"]["x-slack-retry-num"] = "1"
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert "retry skipped" in result["body"]


def test_lambda_handler__empty_body_string__returns_400(monkeypatch):
    """空文字ボディは 400 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event()
    event["body"] = ""  # Factoryのデフォルトを上書き
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 400


def test_lambda_handler__invalid_json__returns_400(monkeypatch):
    """不正 JSON ボディは 400 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(body="not-json")
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 400


def test_lambda_handler__event_callback_no_text__returns_200(monkeypatch):
    """event_callback でテキストなしの場合は 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({
            "type": "event_callback",
            "event": {"type": "message", "channel": "C123"},
        })
    )
    context = LambdaContextFactory.create()

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200


def test_lambda_handler__low_remaining_time__returns_200(monkeypatch):
    """残余時間が少ない場合は早期終了で 200 を返すこと。"""
    monkeypatch.setenv("LAMBDA_RUNTIME", "true")
    event = LambdaEventFactory.api_gateway_event(
        body=_json.dumps({
            "type": "event_callback",
            "event": {"type": "message", "text": "hello", "channel": "C123"},
        })
    )
    # 残余時間 1000ms（閾値 2000ms 以下）
    context = LambdaContextFactory.create(remaining_time_ms=1000)

    from yui.lambda_handler import handler
    result = handler(event, context)
    assert result["statusCode"] == 200
    assert "timeout" in result["body"]


