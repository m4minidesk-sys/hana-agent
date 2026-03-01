"""Console Executor — execute workshop steps via Playwright + Bedrock Vision (AC-73, AC-74, AC-75).

Takes :class:`ExecutableStep` objects from the planner and drives the AWS
Management Console using a vision-guided approach:

1. Navigate to the correct Console page (AC-73).
2. Execute CRUD operations by asking Bedrock Vision for UI actions (AC-74).
3. Validate step results via screenshot analysis (AC-75).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from yui.workshop.models import ExecutableStep, StepOutcome, StepResult, StepType

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-3-20250307-v1:0"
DEFAULT_REGION = "us-east-1"
DEFAULT_STEP_TIMEOUT = 300

AWS_CONSOLE_SERVICE_URL = "https://{region}.console.aws.amazon.com/{service}/home?region={region}"


@dataclass
class UIAction:
    """A single UI action derived from Bedrock Vision analysis."""
    action_type: str
    target: str
    value: str = ""
    description: str = ""


@dataclass
class ValidationResult:
    """Result of Bedrock Vision validation of a screenshot."""
    result: StepResult
    explanation: str = ""
    confidence: float = 0.0


_ACTION_PROMPT = """\
You are operating the AWS Management Console via browser automation.

Current task: {task_description}

Analyse the screenshot and describe the exact UI actions needed to accomplish \
this task. Return a JSON object with this structure:

{{
    "actions": [
        {{
            "action_type": "click" | "type" | "select" | "scroll" | "wait",
            "target": "CSS selector or description of the element",
            "value": "text to type or option to select (if applicable)",
            "description": "what this action does"
        }}
    ],
    "reasoning": "brief explanation of your plan"
}}

Rules:
- Be specific about element targets (use visible text, ARIA labels, or data attributes).
- For typing, include the exact text in "value".
- For clicking, describe the button/link clearly.
- Keep actions in the correct order.
- Return ONLY valid JSON, no markdown fences.
"""

_VALIDATION_PROMPT = """\
You are validating the result of an AWS Console operation.

Expected result: {expected_result}

Analyse the screenshot and determine whether the expected result is visible.

Return ONLY a JSON object (no markdown fences):
{{
    "result": "pass" | "fail" | "unclear",
    "explanation": "brief explanation of what you see",
    "confidence": 0.0 to 1.0
}}
"""

_NAVIGATE_PROMPT = """\
You are navigating the AWS Management Console.

Target: {target_description}

Analyse the screenshot and determine if navigation was successful. \
Return ONLY a JSON object (no markdown fences):
{{
    "success": true | false,
    "current_page": "description of what page we're on",
    "explanation": "brief explanation"
}}
"""


class ConsoleExecutor:
    """Execute workshop steps against the AWS Console via Playwright."""

    def __init__(
        self,
        page: Any,
        model_id: str = DEFAULT_MODEL_ID,
        region: str = DEFAULT_REGION,
        bedrock_client: Any | None = None,
        screenshot_callback: Any | None = None,
    ) -> None:
        self.page = page
        self.model_id = model_id
        self.region = region
        self.screenshot_callback = screenshot_callback

        if bedrock_client is not None:
            self.bedrock = bedrock_client
        else:
            try:
                import boto3
            except ImportError:
                raise RuntimeError(
                    "boto3 is required for ConsoleExecutor but is not installed.\n"
                    "Install it with:  pip install boto3"
                ) from None
            self.bedrock = boto3.client("bedrock-runtime", region_name=region)

    async def execute_step(self, step: ExecutableStep) -> StepOutcome:
        """Execute a single workshop step."""
        start_time = time.monotonic()
        logger.info("Executing step %s: %s [%s]", step.step_id, step.title, step.step_type.value)

        try:
            outcome = await asyncio.wait_for(
                self._dispatch(step),
                timeout=step.timeout_seconds or DEFAULT_STEP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            duration = time.monotonic() - start_time
            outcome = StepOutcome(
                step=step, result=StepResult.TIMEOUT,
                error_message=f"Step timed out after {step.timeout_seconds}s",
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = time.monotonic() - start_time
            logger.error("Step %s failed: %s", step.step_id, exc, exc_info=True)
            screenshot_path = await self._capture_screenshot(step.step_id, on_failure=True)
            outcome = StepOutcome(
                step=step, result=StepResult.FAIL,
                error_message=str(exc), screenshot_path=screenshot_path,
                duration_seconds=duration,
            )

        outcome.duration_seconds = time.monotonic() - start_time
        logger.info("Step %s completed: %s (%.1fs)", step.step_id, outcome.result.value, outcome.duration_seconds)
        return outcome

    async def _dispatch(self, step: ExecutableStep) -> StepOutcome:
        handlers = {
            StepType.CONSOLE_NAVIGATE: self._navigate,
            StepType.CONSOLE_ACTION: self._console_action,
            StepType.CONSOLE_VERIFY: self._verify,
            StepType.CLI_COMMAND: self._cli_command,
            StepType.CLI_CHECK: self._cli_command,
            StepType.WAIT: self._wait,
            StepType.MANUAL_STEP: self._manual_step,
        }
        handler = handlers.get(step.step_type)
        if handler is None:
            return StepOutcome(step=step, result=StepResult.SKIP,
                               error_message=f"No handler for step type: {step.step_type.value}")
        return await handler(step)

    async def _navigate(self, step: ExecutableStep) -> StepOutcome:
        url = step.action.get("url", "")
        service = step.action.get("service", "")
        target_region = step.action.get("region", self.region)

        if url:
            nav_url = url
        elif service:
            nav_url = AWS_CONSOLE_SERVICE_URL.format(region=target_region, service=service)
        else:
            return StepOutcome(step=step, result=StepResult.FAIL,
                               error_message="Navigate step requires 'url' or 'service' in action")

        try:
            await self.page.goto(nav_url, wait_until="networkidle")
        except Exception as exc:
            return StepOutcome(step=step, result=StepResult.FAIL,
                               error_message=f"Navigation failed: {exc}")

        screenshot = await self.page.screenshot()
        screenshot_path = await self._capture_screenshot(step.step_id)
        nav_result = await self._ask_vision_navigate(screenshot, step.description)
        result = StepResult.PASS if nav_result else StepResult.FAIL
        return StepOutcome(step=step, result=result, screenshot_path=screenshot_path,
                           actual_output=f"Navigated to: {self.page.url}")

    async def _console_action(self, step: ExecutableStep) -> StepOutcome:
        screenshot = await self.page.screenshot()
        actions = await self._ask_vision_action(screenshot, step.description)
        if not actions:
            return StepOutcome(step=step, result=StepResult.FAIL,
                               error_message="Vision returned no actions")

        for action in actions:
            await self._execute_ui_action(action)

        try:
            await self.page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        result_screenshot = await self.page.screenshot()
        screenshot_path = await self._capture_screenshot(step.step_id)
        validation = await self._validate_result(result_screenshot, step.expected_result)
        return StepOutcome(step=step, result=validation.result,
                           screenshot_path=screenshot_path, actual_output=validation.explanation)

    async def _verify(self, step: ExecutableStep) -> StepOutcome:
        screenshot = await self.page.screenshot()
        screenshot_path = await self._capture_screenshot(step.step_id)
        validation = await self._validate_result(screenshot, step.expected_result)
        return StepOutcome(step=step, result=validation.result,
                           screenshot_path=screenshot_path, actual_output=validation.explanation)

    async def _cli_command(self, step: ExecutableStep) -> StepOutcome:
        import subprocess

        command = step.action.get("command", "")
        if not command:
            return StepOutcome(step=step, result=StepResult.FAIL,
                               error_message="CLI step requires 'command' in action")

        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(command, shell=True, capture_output=True,
                                       text=True, timeout=step.timeout_seconds or DEFAULT_STEP_TIMEOUT),
            )
            output = proc.stdout
            if proc.stderr:
                output += f"\nSTDERR: {proc.stderr}"
            result = StepResult.PASS if proc.returncode == 0 else StepResult.FAIL
            return StepOutcome(step=step, result=result, actual_output=output.strip(),
                               error_message="" if result == StepResult.PASS else f"Exit code: {proc.returncode}")
        except subprocess.TimeoutExpired:
            return StepOutcome(step=step, result=StepResult.TIMEOUT,
                               error_message=f"CLI command timed out after {step.timeout_seconds}s")
        except Exception as exc:
            return StepOutcome(step=step, result=StepResult.FAIL,
                               error_message=f"CLI execution failed: {exc}")

    async def _wait(self, step: ExecutableStep) -> StepOutcome:
        seconds = step.action.get("seconds", 0)
        reason = step.action.get("reason", "")
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            return StepOutcome(step=step, result=StepResult.FAIL,
                               error_message="Wait step requires positive 'seconds' in action")
        logger.info("Waiting %ds: %s", seconds, reason)
        await asyncio.sleep(seconds)
        return StepOutcome(step=step, result=StepResult.PASS,
                           actual_output=f"Waited {seconds}s: {reason}")

    async def _manual_step(self, step: ExecutableStep) -> StepOutcome:
        return StepOutcome(step=step, result=StepResult.SKIP,
                           actual_output=f"Manual step skipped: {step.description}")

    # -- Bedrock Vision helpers --

    async def _ask_vision_action(self, screenshot: bytes, task_description: str) -> list[UIAction]:
        prompt = _ACTION_PROMPT.format(task_description=task_description)
        response_text = await self._invoke_bedrock_vision(screenshot, prompt)
        if not response_text:
            return []
        try:
            data = _parse_json_response(response_text)
            return [
                UIAction(action_type=a.get("action_type", "click"), target=a.get("target", ""),
                         value=a.get("value", ""), description=a.get("description", ""))
                for a in data.get("actions", []) if isinstance(a, dict)
            ]
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse vision action response: %s", exc)
            return []

    async def _ask_vision_navigate(self, screenshot: bytes, target_description: str) -> bool:
        prompt = _NAVIGATE_PROMPT.format(target_description=target_description)
        response_text = await self._invoke_bedrock_vision(screenshot, prompt)
        if not response_text:
            return False
        try:
            data = _parse_json_response(response_text)
            return bool(data.get("success", False))
        except (json.JSONDecodeError, ValueError):
            return False

    async def _validate_result(self, screenshot: bytes, expected_result: str) -> ValidationResult:
        prompt = _VALIDATION_PROMPT.format(expected_result=expected_result)
        response_text = await self._invoke_bedrock_vision(screenshot, prompt)
        if not response_text:
            return ValidationResult(result=StepResult.FAIL, explanation="No response from Bedrock Vision")
        try:
            data = _parse_json_response(response_text)
            result_str = data.get("result", "fail")
            result_map = {"pass": StepResult.PASS, "fail": StepResult.FAIL, "unclear": StepResult.SKIP}
            return ValidationResult(
                result=result_map.get(result_str, StepResult.FAIL),
                explanation=data.get("explanation", ""),
                confidence=float(data.get("confidence", 0.0)),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse validation response: %s", exc)
            return ValidationResult(result=StepResult.FAIL, explanation=f"Failed to parse vision response: {exc}")

    async def _invoke_bedrock_vision(self, screenshot: bytes, prompt: str) -> str:
        def _call() -> dict:
            return self.bedrock.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [
                    {"image": {"format": "png", "source": {"bytes": screenshot}}},
                    {"text": prompt},
                ]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.1},
            )
        try:
            response = await asyncio.get_event_loop().run_in_executor(None, _call)
        except Exception as exc:
            logger.warning("Bedrock Vision call failed: %s", exc)
            return ""
        output_message = response.get("output", {}).get("message", {})
        for block in output_message.get("content", []):
            if "text" in block:
                return block["text"]
        return ""

    # -- UI action execution --

    async def _execute_ui_action(self, action: UIAction) -> None:
        logger.debug("Executing UI action: %s on %s", action.action_type, action.target)
        if action.action_type == "click":
            await self._action_click(action)
        elif action.action_type == "type":
            await self._action_type(action)
        elif action.action_type == "select":
            await self._action_select(action)
        elif action.action_type == "scroll":
            await self._action_scroll(action)
        elif action.action_type == "wait":
            wait_ms = 2000
            try:
                wait_ms = int(action.value) if action.value else 2000
            except ValueError:
                pass
            await asyncio.sleep(wait_ms / 1000)
        else:
            logger.warning("Unknown action type: %s", action.action_type)

    async def _action_click(self, action: UIAction) -> None:
        try:
            el = await self.page.query_selector(action.target)
            if el:
                await el.click()
                return
        except Exception:
            pass
        try:
            await self.page.click(f"text={action.target}", timeout=5000)
        except Exception as exc:
            logger.warning("Click failed for target %s: %s", action.target, exc)

    async def _action_type(self, action: UIAction) -> None:
        try:
            el = await self.page.query_selector(action.target)
            if el:
                await el.fill(action.value)
                return
        except Exception:
            pass
        try:
            await self.page.fill(action.target, action.value)
        except Exception as exc:
            logger.warning("Type failed for target %s: %s", action.target, exc)

    async def _action_select(self, action: UIAction) -> None:
        try:
            await self.page.select_option(action.target, value=action.value)
        except Exception as exc:
            logger.warning("Select failed for target %s: %s", action.target, exc)

    async def _action_scroll(self, action: UIAction) -> None:
        try:
            pixels = int(action.value) if action.value else 500
        except ValueError:
            pixels = 500
        await self.page.evaluate(f"window.scrollBy(0, {pixels})")

    async def _capture_screenshot(self, step_id: str, on_failure: bool = False) -> str | None:
        if self.screenshot_callback is None:
            return None
        try:
            screenshot = await self.page.screenshot()
            return await self.screenshot_callback(screenshot, step_id, on_failure)
        except Exception as exc:
            logger.warning("Screenshot capture failed: %s", exc)
            return None


def _parse_json_response(text: str) -> dict:
    """Parse a JSON response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
    return data
