"""Tests for yui.workshop.planner (AC-71)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yui.workshop.models import ExecutableStep, StepType, WorkshopPage
from yui.workshop.planner import (
    _build_user_message,
    _parse_llm_response,
    detect_cli_steps_from_code_blocks,
    plan_steps,
    validate_steps,
)

pytestmark = pytest.mark.component



# =========================================================================
# Fixtures
# =========================================================================


def _make_page(
    title: str = "Setup",
    url: str = "https://catalog.workshops.aws/ws/setup",
    content: str = "Navigate to the S3 console and create a bucket.",
    module_index: int = 1,
    step_index: int = 0,
    code_blocks: list[str] | None = None,
    images: list[str] | None = None,
) -> WorkshopPage:
    return WorkshopPage(
        title=title,
        url=url,
        content=content,
        module_index=module_index,
        step_index=step_index,
        code_blocks=code_blocks or [],
        images=images or [],
    )


def _make_llm_step_dict(**overrides: object) -> dict:
    """Return a valid raw step dict, with optional overrides."""
    base: dict = {
        "step_id": "1.0.1",
        "title": "Navigate to S3",
        "step_type": "console_navigate",
        "description": "Open the S3 console",
        "action": {"url": "https://console.aws.amazon.com/s3"},
        "expected_result": "S3 console is displayed",
        "timeout_seconds": 300,
        "depends_on": [],
    }
    base.update(overrides)
    return base


def _mock_bedrock_response(steps: list[dict]) -> dict:
    """Build a Bedrock Converse API response dict."""
    return {
        "output": {
            "message": {
                "content": [{"text": json.dumps(steps)}],
            },
        },
    }


# =========================================================================
# _parse_llm_response
# =========================================================================


class TestParseLlmResponse:
    """JSON parsing tolerance."""

    def test_plain_array(self) -> None:
        raw = json.dumps([{"step_id": "1"}])
        assert _parse_llm_response(raw) == [{"step_id": "1"}]

    def test_markdown_fenced(self) -> None:
        raw = "```json\n[{\"step_id\": \"1\"}]\n```"
        assert _parse_llm_response(raw) == [{"step_id": "1"}]

    def test_dict_with_steps_key(self) -> None:
        raw = json.dumps({"steps": [{"step_id": "1"}]})
        assert _parse_llm_response(raw) == [{"step_id": "1"}]

    def test_dict_with_results_key(self) -> None:
        raw = json.dumps({"results": [{"step_id": "2"}]})
        assert _parse_llm_response(raw) == [{"step_id": "2"}]

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response("not json at all")

    def test_unexpected_dict_raises(self) -> None:
        raw = json.dumps({"foo": "bar"})
        with pytest.raises(ValueError, match="no recognised list key"):
            _parse_llm_response(raw)

    def test_non_list_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected a JSON array"):
            _parse_llm_response('"just a string"')


# =========================================================================
# validate_steps
# =========================================================================


class TestValidateSteps:
    """Step validation / conversion."""

    def test_valid_step(self) -> None:
        page = _make_page()
        raw = [_make_llm_step_dict()]
        steps = validate_steps(raw, page)
        assert len(steps) == 1
        assert isinstance(steps[0], ExecutableStep)
        assert steps[0].step_type == StepType.CONSOLE_NAVIGATE

    def test_missing_required_field(self) -> None:
        page = _make_page()
        raw = [{"step_id": "1"}]  # missing most fields
        steps = validate_steps(raw, page)
        assert len(steps) == 0  # skipped, not raised

    def test_invalid_step_type(self) -> None:
        page = _make_page()
        raw = [_make_llm_step_dict(step_type="nonexistent_type")]
        steps = validate_steps(raw, page)
        assert len(steps) == 0

    def test_action_must_be_dict(self) -> None:
        page = _make_page()
        raw = [_make_llm_step_dict(action="not-a-dict")]
        steps = validate_steps(raw, page)
        assert len(steps) == 0

    def test_all_step_types_accepted(self) -> None:
        page = _make_page()
        for st in StepType:
            raw = [_make_llm_step_dict(step_type=st.value, step_id=f"x.{st.value}")]
            steps = validate_steps(raw, page)
            assert len(steps) == 1
            assert steps[0].step_type == st

    def test_default_timeout(self) -> None:
        page = _make_page()
        d = _make_llm_step_dict()
        del d["timeout_seconds"]
        steps = validate_steps([d], page)
        assert steps[0].timeout_seconds == 300

    def test_depends_on_converted_to_strings(self) -> None:
        page = _make_page()
        raw = [_make_llm_step_dict(depends_on=[1, 2])]
        steps = validate_steps(raw, page)
        assert steps[0].depends_on == ["1", "2"]

    def test_module_field_from_page_title(self) -> None:
        page = _make_page(title="My Module")
        steps = validate_steps([_make_llm_step_dict()], page)
        assert steps[0].module == "My Module"

    def test_original_text_truncated(self) -> None:
        page = _make_page(content="x" * 1000)
        steps = validate_steps([_make_llm_step_dict()], page)
        assert len(steps[0].original_text) <= 500


# =========================================================================
# detect_cli_steps_from_code_blocks
# =========================================================================


class TestDetectCliSteps:
    """Heuristic CLI detection."""

    def test_aws_cli_detected(self) -> None:
        page = _make_page(code_blocks=["aws s3 ls"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert len(steps) == 1
        assert steps[0].step_type == StepType.CLI_COMMAND
        assert steps[0].action["command"] == "aws s3 ls"

    def test_dollar_prefix_stripped(self) -> None:
        page = _make_page(code_blocks=["$ echo hello"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert steps[0].action["command"] == "echo hello"

    def test_non_cli_block_ignored(self) -> None:
        page = _make_page(code_blocks=["function hello() { return 1; }"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert len(steps) == 0

    def test_multiple_cli_blocks(self) -> None:
        page = _make_page(code_blocks=["aws s3 ls", "npm install", "some python code"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert len(steps) == 2

    def test_empty_code_blocks(self) -> None:
        page = _make_page(code_blocks=[])
        assert detect_cli_steps_from_code_blocks(page) == []

    def test_sam_cli_detected(self) -> None:
        page = _make_page(code_blocks=["sam deploy --guided"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert len(steps) == 1
        assert "sam deploy" in steps[0].action["command"]

    def test_step_id_format(self) -> None:
        page = _make_page(module_index=2, step_index=3, code_blocks=["aws sts get-caller-identity"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert steps[0].step_id == "2.3.cb0"

    def test_docker_cli_detected(self) -> None:
        page = _make_page(code_blocks=["docker build -t myapp ."])
        steps = detect_cli_steps_from_code_blocks(page)
        assert len(steps) == 1

    def test_kubectl_detected(self) -> None:
        page = _make_page(code_blocks=["kubectl get pods"])
        steps = detect_cli_steps_from_code_blocks(page)
        assert len(steps) == 1


# =========================================================================
# _build_user_message
# =========================================================================


class TestBuildUserMessage:
    """Prompt construction."""

    def test_includes_page_title(self) -> None:
        page = _make_page(title="Deploy Lambda")
        msg = _build_user_message(page)
        assert "Deploy Lambda" in msg

    def test_includes_content(self) -> None:
        page = _make_page(content="Create an S3 bucket named workshop-xyz")
        msg = _build_user_message(page)
        assert "workshop-xyz" in msg

    def test_includes_code_blocks(self) -> None:
        page = _make_page(code_blocks=["aws s3 mb s3://test"])
        msg = _build_user_message(page)
        assert "aws s3 mb" in msg

    def test_empty_code_blocks_no_section(self) -> None:
        page = _make_page(code_blocks=[])
        msg = _build_user_message(page)
        assert "Code blocks" not in msg


# =========================================================================
# plan_steps — dry-run mode
# =========================================================================


class TestPlanStepsDryRun:
    """dry_run=True skips LLM calls."""

    async def test_dry_run_returns_cli_steps_only(self) -> None:
        pages = [_make_page(code_blocks=["aws s3 ls"])]
        steps = await plan_steps(pages, dry_run=True)
        assert len(steps) == 1
        assert steps[0].step_type == StepType.CLI_COMMAND

    async def test_dry_run_no_bedrock_call(self) -> None:
        pages = [_make_page(code_blocks=["aws s3 ls"])]
        mock_client = MagicMock()
        steps = await plan_steps(pages, dry_run=True, bedrock_client=mock_client)
        mock_client.converse.assert_not_called()

    async def test_dry_run_empty_pages(self) -> None:
        steps = await plan_steps([], dry_run=True)
        assert steps == []

    async def test_dry_run_no_code_blocks(self) -> None:
        pages = [_make_page(code_blocks=[])]
        steps = await plan_steps(pages, dry_run=True)
        assert steps == []


# =========================================================================
# plan_steps — with mocked Bedrock
# =========================================================================


class TestPlanStepsWithBedrock:
    """Full planning with mocked Bedrock Converse."""

    async def test_llm_steps_returned(self) -> None:
        page = _make_page()
        llm_steps = [_make_llm_step_dict()]
        mock_client = MagicMock()
        mock_client.converse = MagicMock(return_value=_mock_bedrock_response(llm_steps))

        steps = await plan_steps([page], bedrock_client=mock_client)
        assert len(steps) >= 1
        # Should contain the LLM-generated step
        types = {s.step_type for s in steps}
        assert StepType.CONSOLE_NAVIGATE in types

    async def test_bedrock_called_with_model_id(self) -> None:
        page = _make_page()
        mock_client = MagicMock()
        mock_client.converse = MagicMock(
            return_value=_mock_bedrock_response([_make_llm_step_dict()])
        )

        await plan_steps([page], model_id="custom-model", bedrock_client=mock_client)
        call_kwargs = mock_client.converse.call_args
        assert call_kwargs[1]["modelId"] == "custom-model"

    async def test_empty_llm_response_handled(self) -> None:
        page = _make_page()
        mock_client = MagicMock()
        mock_client.converse = MagicMock(
            return_value={"output": {"message": {"content": [{"text": ""}]}}}
        )

        # Should not raise, just return deterministic steps (if any)
        steps = await plan_steps([page], bedrock_client=mock_client)
        assert isinstance(steps, list)

    async def test_malformed_llm_json_handled(self) -> None:
        page = _make_page()
        mock_client = MagicMock()
        mock_client.converse = MagicMock(
            return_value={"output": {"message": {"content": [{"text": "not valid json!!!"}]}}}
        )

        steps = await plan_steps([page], bedrock_client=mock_client)
        assert isinstance(steps, list)  # graceful degradation

    async def test_multiple_pages_all_processed(self) -> None:
        pages = [
            _make_page(title="Page 1", module_index=0, step_index=0),
            _make_page(title="Page 2", module_index=0, step_index=1),
        ]
        llm_steps_1 = [_make_llm_step_dict(step_id="0.0.1")]
        llm_steps_2 = [_make_llm_step_dict(step_id="0.1.1")]

        call_count = 0

        def _converse(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_bedrock_response(llm_steps_1)
            return _mock_bedrock_response(llm_steps_2)

        mock_client = MagicMock()
        mock_client.converse = _converse

        steps = await plan_steps(pages, bedrock_client=mock_client)
        assert call_count == 2
        step_ids = {s.step_id for s in steps}
        assert "0.0.1" in step_ids
        assert "0.1.1" in step_ids

    async def test_steps_sorted_by_id(self) -> None:
        page = _make_page()
        llm_steps = [
            _make_llm_step_dict(step_id="2.0.1"),
            _make_llm_step_dict(step_id="1.0.1", title="Earlier"),
        ]
        mock_client = MagicMock()
        mock_client.converse = MagicMock(return_value=_mock_bedrock_response(llm_steps))

        steps = await plan_steps([page], bedrock_client=mock_client)
        ids = [s.step_id for s in steps]
        assert ids.index("1.0.1") < ids.index("2.0.1")

    async def test_deduplication_prefers_llm(self) -> None:
        """If a code-block step and LLM step share a step_id, LLM wins."""
        page = _make_page(code_blocks=["aws s3 ls"])
        # The heuristic creates "1.0.cb0"; make the LLM return the same id
        llm_steps = [_make_llm_step_dict(step_id="1.0.cb0", title="LLM version")]
        mock_client = MagicMock()
        mock_client.converse = MagicMock(return_value=_mock_bedrock_response(llm_steps))

        steps = await plan_steps([page], bedrock_client=mock_client)
        matching = [s for s in steps if s.step_id == "1.0.cb0"]
        assert len(matching) == 1
        assert matching[0].title == "LLM version"

    async def test_depends_on_preserved(self) -> None:
        page = _make_page()
        llm_steps = [
            _make_llm_step_dict(step_id="1.0.1"),
            _make_llm_step_dict(step_id="1.0.2", depends_on=["1.0.1"]),
        ]
        mock_client = MagicMock()
        mock_client.converse = MagicMock(return_value=_mock_bedrock_response(llm_steps))

        steps = await plan_steps([page], bedrock_client=mock_client)
        step_2 = [s for s in steps if s.step_id == "1.0.2"][0]
        assert "1.0.1" in step_2.depends_on

    async def test_default_model_id_used(self) -> None:
        from yui.workshop.planner import DEFAULT_MODEL_ID

        page = _make_page()
        mock_client = MagicMock()
        mock_client.converse = MagicMock(
            return_value=_mock_bedrock_response([_make_llm_step_dict()])
        )

        await plan_steps([page], bedrock_client=mock_client)
        call_kwargs = mock_client.converse.call_args
        assert call_kwargs[1]["modelId"] == DEFAULT_MODEL_ID

    async def test_empty_model_id_raises(self) -> None:
        page = _make_page()
        with pytest.raises(ValueError, match="model_id must not be empty"):
            await plan_steps([page], model_id="")

    async def test_bedrock_api_error_handled_gracefully(self) -> None:
        """If Bedrock raises an exception, it's caught and logged."""
        page = _make_page()
        mock_client = MagicMock()
        mock_client.converse = MagicMock(side_effect=RuntimeError("throttled"))

        steps = await plan_steps([page], bedrock_client=mock_client)
        assert isinstance(steps, list)  # no crash
