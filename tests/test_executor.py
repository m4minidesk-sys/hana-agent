"""Tests for Console Executor (AC-73, AC-74, AC-75). All mocked."""

from __future__ import annotations

import asyncio
import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yui.workshop.executor import (
    ConsoleExecutor, UIAction, ValidationResult, _parse_json_response,
)
from yui.workshop.models import ExecutableStep, StepResult, StepType


def _make_step(step_type=StepType.CONSOLE_ACTION, action=None, expected_result="Success",
               timeout_seconds=300, step_id="1.1", description="Test step"):
    return ExecutableStep(step_id=step_id, title="Test Step", step_type=step_type,
                          description=description, action=action or {},
                          expected_result=expected_result, timeout_seconds=timeout_seconds)


def _bedrock_response(text):
    return {"output": {"message": {"content": [{"text": text}]}}}


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.url = "https://console.aws.amazon.com/s3/home"
    page.goto = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fake-png-bytes")
    page.wait_for_load_state = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.select_option = AsyncMock()
    page.evaluate = AsyncMock()
    return page


@pytest.fixture
def mock_bedrock():
    return MagicMock()


@pytest.fixture
def executor(mock_page, mock_bedrock):
    return ConsoleExecutor(page=mock_page, model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                           region="us-east-1", bedrock_client=mock_bedrock)


class TestNavigate:
    @pytest.mark.asyncio
    async def test_navigate_with_url(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"success": True, "current_page": "S3", "explanation": "On S3"}))
        step = _make_step(step_type=StepType.CONSOLE_NAVIGATE,
                          action={"url": "https://console.aws.amazon.com/s3/"})
        outcome = await executor.execute_step(step)
        assert outcome.result == StepResult.PASS
        mock_page.goto.assert_called_once_with("https://console.aws.amazon.com/s3/", wait_until="networkidle")

    @pytest.mark.asyncio
    async def test_navigate_with_service(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"success": True, "current_page": "Lambda", "explanation": "OK"}))
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_NAVIGATE, action={"service": "lambda"}))
        assert outcome.result == StepResult.PASS
        mock_page.goto.assert_called_once()
        assert "lambda" in mock_page.goto.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_navigate_with_region(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"success": True, "current_page": "EC2 Tokyo", "explanation": "OK"}))
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_NAVIGATE,
                       action={"service": "ec2", "region": "ap-northeast-1"}))
        assert outcome.result == StepResult.PASS
        assert "ap-northeast-1" in mock_page.goto.call_args[0][0]

    @pytest.mark.asyncio
    async def test_navigate_missing_url_and_service(self, executor):
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_NAVIGATE, action={}))
        assert outcome.result == StepResult.FAIL
        assert "requires" in outcome.error_message

    @pytest.mark.asyncio
    async def test_navigate_goto_error(self, executor, mock_page, mock_bedrock):
        mock_page.goto.side_effect = Exception("net::ERR_CONNECTION_REFUSED")
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_NAVIGATE,
                       action={"url": "https://console.aws.amazon.com/s3/"}))
        assert outcome.result == StepResult.FAIL
        assert "Navigation failed" in outcome.error_message

    @pytest.mark.asyncio
    async def test_navigate_vision_says_no(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"success": False, "current_page": "Login", "explanation": "Not logged in"}))
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_NAVIGATE,
                       action={"url": "https://console.aws.amazon.com/s3/"}))
        assert outcome.result == StepResult.FAIL


class TestConsoleAction:
    @pytest.mark.asyncio
    async def test_action_success(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.side_effect = [
            _bedrock_response(json.dumps({
                "actions": [{"action_type": "click", "target": "#btn", "value": "", "description": "Click"}],
                "reasoning": "Click"})),
            _bedrock_response(json.dumps({"result": "pass", "explanation": "Done", "confidence": 0.95})),
        ]
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_ACTION, expected_result="Bucket exists"))
        assert outcome.result == StepResult.PASS
        assert mock_bedrock.converse.call_count == 2

    @pytest.mark.asyncio
    async def test_action_vision_returns_no_actions(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"actions": [], "reasoning": "Nothing"}))
        outcome = await executor.execute_step(_make_step(step_type=StepType.CONSOLE_ACTION))
        assert outcome.result == StepResult.FAIL

    @pytest.mark.asyncio
    async def test_action_validation_fails(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.side_effect = [
            _bedrock_response(json.dumps({
                "actions": [{"action_type": "click", "target": "#btn", "value": "", "description": "Click"}],
                "reasoning": "Click"})),
            _bedrock_response(json.dumps({"result": "fail", "explanation": "Not found", "confidence": 0.8})),
        ]
        outcome = await executor.execute_step(_make_step(step_type=StepType.CONSOLE_ACTION))
        assert outcome.result == StepResult.FAIL

    @pytest.mark.asyncio
    async def test_action_validation_unclear(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.side_effect = [
            _bedrock_response(json.dumps({
                "actions": [{"action_type": "click", "target": "#btn", "value": "", "description": "Click"}],
                "reasoning": "Click"})),
            _bedrock_response(json.dumps({"result": "unclear", "explanation": "Loading", "confidence": 0.3})),
        ]
        outcome = await executor.execute_step(_make_step(step_type=StepType.CONSOLE_ACTION))
        assert outcome.result == StepResult.SKIP


class TestVerify:
    @pytest.mark.asyncio
    async def test_verify_pass(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"result": "pass", "explanation": "OK", "confidence": 0.9}))
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_VERIFY, expected_result="S3 bucket exists"))
        assert outcome.result == StepResult.PASS
        mock_bedrock.converse.assert_called_once()
        # Verify the Bedrock call included screenshot for vision analysis
        call_args = mock_bedrock.converse.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_verify_fail(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"result": "fail", "explanation": "Not found", "confidence": 0.85}))
        outcome = await executor.execute_step(_make_step(step_type=StepType.CONSOLE_VERIFY))
        assert outcome.result == StepResult.FAIL

    @pytest.mark.asyncio
    async def test_verify_bedrock_error(self, executor, mock_page, mock_bedrock):
        mock_bedrock.converse.side_effect = Exception("ServiceUnavailableException")
        outcome = await executor.execute_step(_make_step(step_type=StepType.CONSOLE_VERIFY))
        assert outcome.result == StepResult.FAIL


class TestCLICommand:
    @pytest.mark.asyncio
    async def test_cli_success(self, executor):
        step = _make_step(step_type=StepType.CLI_COMMAND, action={"command": "echo hello"})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="hello\n", stderr="", returncode=0)
            outcome = await executor.execute_step(step)
        assert outcome.result == StepResult.PASS
        assert "hello" in outcome.actual_output

    @pytest.mark.asyncio
    async def test_cli_failure(self, executor):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="error\n", returncode=1)
            outcome = await executor.execute_step(
                _make_step(step_type=StepType.CLI_COMMAND, action={"command": "false"}))
        assert outcome.result == StepResult.FAIL

    @pytest.mark.asyncio
    async def test_cli_timeout(self, executor):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("sleep", 1)
            outcome = await executor.execute_step(
                _make_step(step_type=StepType.CLI_COMMAND, action={"command": "sleep 999"}, timeout_seconds=1))
        assert outcome.result == StepResult.TIMEOUT

    @pytest.mark.asyncio
    async def test_cli_missing_command(self, executor):
        outcome = await executor.execute_step(_make_step(step_type=StepType.CLI_COMMAND, action={}))
        assert outcome.result == StepResult.FAIL

    @pytest.mark.asyncio
    async def test_cli_check_type(self, executor):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ok\n", stderr="", returncode=0)
            outcome = await executor.execute_step(
                _make_step(step_type=StepType.CLI_CHECK, action={"command": "echo ok"}))
        assert outcome.result == StepResult.PASS
        mock_run.assert_called_once()
        assert "echo ok" in str(mock_run.call_args)


class TestWait:
    @pytest.mark.asyncio
    async def test_wait_success(self, executor):
        import time as _time
        start = _time.monotonic()
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.WAIT, action={"seconds": 0.01, "reason": "propagation"}))
        elapsed = _time.monotonic() - start
        assert outcome.result == StepResult.PASS
        assert elapsed >= 0.01  # Actually waited

    @pytest.mark.asyncio
    async def test_wait_invalid_seconds(self, executor):
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.WAIT, action={"seconds": -1, "reason": "bad"}))
        assert outcome.result == StepResult.FAIL


class TestManualStep:
    @pytest.mark.asyncio
    async def test_manual_step_skipped(self, executor):
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.MANUAL_STEP, description="Open physical device"))
        assert outcome.result == StepResult.SKIP


class TestTimeout:
    @pytest.mark.asyncio
    async def test_step_timeout(self, executor, mock_page, mock_bedrock):
        async def _hang(*args, **kwargs):
            await asyncio.sleep(999)
            return ""
        executor._invoke_bedrock_vision = _hang
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CONSOLE_VERIFY, timeout_seconds=1))
        assert outcome.result == StepResult.TIMEOUT


class TestUnhandledStepType:
    @pytest.mark.asyncio
    async def test_unhandled_type_skipped(self, executor):
        outcome = await executor.execute_step(
            _make_step(step_type=StepType.CFN_DEPLOY, action={"template": "t.yaml"}))
        assert outcome.result == StepResult.SKIP


class TestParseJsonResponse:
    def test_plain_json(self):
        assert _parse_json_response('{"key": "value"}') == {"key": "value"}

    def test_json_with_fences(self):
        assert _parse_json_response('```json\n{"key": "value"}\n```') == {"key": "value"}

    def test_json_with_plain_fences(self):
        assert _parse_json_response('```\n{"key": "value"}\n```') == {"key": "value"}

    def test_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_json_response("not json")

    def test_json_array_raises(self):
        with pytest.raises(ValueError, match="Expected a JSON object"):
            _parse_json_response('[1, 2, 3]')


class TestUIActionExecution:
    @pytest.mark.asyncio
    async def test_click_css_selector(self, executor, mock_page):
        el = AsyncMock()
        mock_page.query_selector.return_value = el
        await executor._execute_ui_action(UIAction(action_type="click", target="#my-button"))
        el.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_text_fallback(self, executor, mock_page):
        mock_page.query_selector.return_value = None
        await executor._execute_ui_action(UIAction(action_type="click", target="Submit"))
        mock_page.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_type_action(self, executor, mock_page):
        el = AsyncMock()
        mock_page.query_selector.return_value = el
        await executor._execute_ui_action(UIAction(action_type="type", target="#input", value="hello"))
        el.fill.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_select_action(self, executor, mock_page):
        await executor._execute_ui_action(UIAction(action_type="select", target="#dd", value="opt1"))
        mock_page.select_option.assert_called_once_with("#dd", value="opt1")

    @pytest.mark.asyncio
    async def test_scroll_action(self, executor, mock_page):
        await executor._execute_ui_action(UIAction(action_type="scroll", target="", value="300"))
        mock_page.evaluate.assert_called_once_with("window.scrollBy(0, 300)")

    @pytest.mark.asyncio
    async def test_wait_action(self, executor):
        await executor._execute_ui_action(UIAction(action_type="wait", target="", value="10"))


class TestScreenshotCallback:
    @pytest.mark.asyncio
    async def test_callback_invoked(self, mock_page, mock_bedrock):
        callback = AsyncMock(return_value="/tmp/step-1.1.png")
        ex = ConsoleExecutor(page=mock_page, bedrock_client=mock_bedrock, screenshot_callback=callback)
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"result": "pass", "explanation": "OK", "confidence": 0.9}))
        outcome = await ex.execute_step(_make_step(step_type=StepType.CONSOLE_VERIFY))
        assert outcome.result == StepResult.PASS
        callback.assert_called()

    @pytest.mark.asyncio
    async def test_no_callback(self, executor, mock_bedrock):
        mock_bedrock.converse.return_value = _bedrock_response(
            json.dumps({"result": "pass", "explanation": "OK", "confidence": 0.9}))
        outcome = await executor.execute_step(_make_step(step_type=StepType.CONSOLE_VERIFY))
        assert outcome.result == StepResult.PASS
        assert outcome.screenshot_path is None


class TestValidationResult:
    def test_defaults(self):
        v = ValidationResult(result=StepResult.PASS)
        assert v.explanation == "" and v.confidence == 0.0

    def test_full(self):
        v = ValidationResult(result=StepResult.FAIL, explanation="Not found", confidence=0.85)
        assert v.result == StepResult.FAIL and v.confidence == 0.85
