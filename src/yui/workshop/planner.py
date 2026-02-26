"""Step Planner — convert scraped workshop pages into executable steps (AC-71).

Uses Amazon Bedrock Converse API to analyse workshop content and produce
structured :class:`ExecutableStep` objects.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from yui.workshop.models import ExecutableStep, StepType, WorkshopPage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

DEFAULT_STEP_TIMEOUT_SECONDS = 300

STEP_TYPE_VALUES = [t.value for t in StepType]

# ---------------------------------------------------------------------------
# JSON schema for LLM output validation
# ---------------------------------------------------------------------------

_STEP_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "step_id": {"type": "string"},
        "title": {"type": "string"},
        "step_type": {"type": "string", "enum": STEP_TYPE_VALUES},
        "description": {"type": "string"},
        "action": {"type": "object"},
        "expected_result": {"type": "string"},
        "timeout_seconds": {"type": "integer"},
        "depends_on": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["step_id", "title", "step_type", "description", "action", "expected_result"],
}

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a workshop-step planner.  Given the text of a single AWS Workshop Studio page, \
produce a JSON array of executable steps.

Each step MUST have these fields:
- step_id: hierarchical id like "1.3.2"
- title: short human-readable title
- step_type: one of {step_types}
- description: what the user/automation should do
- action: a dict with type-specific keys:
    * console_navigate / console_action / console_verify → {{"url": "...", "description": "..."}}
    * cli_command / cli_check → {{"command": "..."}}
    * cfn_deploy → {{"template": "...", "stack_name": "..."}}
    * http_test → {{"method": "GET", "url": "..."}}
    * code_run → {{"language": "python", "code": "..."}}
    * wait → {{"seconds": 60, "reason": "..."}}
    * manual_step → {{"instruction": "..."}}
- expected_result: string describing the success condition
- timeout_seconds: integer (default 300)
- depends_on: list of step_ids this step depends on (empty list if none)

Rules:
1. If you see a shell/CLI command (e.g. in a code block starting with $ or aws ...) → cli_command.
2. If you see "Navigate to …" or a console URL → console_navigate.
3. If you see "Click …" / "Select …" / "Enter …" in the console → console_action.
4. If you see "Verify …" / "Confirm …" / "You should see …" → console_verify or cli_check.
5. If a CloudFormation/SAM template is deployed → cfn_deploy.
6. If you see curl/httpie or "test the endpoint" → http_test.
7. If you see code to run (python, node, etc.) → code_run.
8. If you see "Wait for …" → wait.
9. Anything else → manual_step.

Return ONLY a JSON array (no markdown fences, no commentary).
"""


def _build_user_message(page: WorkshopPage) -> str:
    """Build the user message for a single page."""
    parts = [
        f"## Page: {page.title}",
        f"URL: {page.url}",
        f"Module {page.module_index}, Step {page.step_index}",
        "",
        page.content,
    ]
    if page.code_blocks:
        parts.append("\n### Code blocks found on this page:")
        for i, block in enumerate(page.code_blocks, 1):
            parts.append(f"\n```\n{block}\n```")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM response parsing / validation
# ---------------------------------------------------------------------------


def _parse_llm_response(raw: str) -> list[dict]:
    """Parse the LLM's JSON response, tolerating markdown fences."""
    text = raw.strip()
    # Strip optional markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if isinstance(data, dict):
        # Sometimes the LLM wraps in {"steps": [...]}
        for key in ("steps", "executable_steps", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        raise ValueError("LLM returned a dict but no recognised list key")
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got {type(data).__name__}")
    return data


def _validate_step(raw: dict, page: WorkshopPage) -> ExecutableStep:
    """Convert and validate a single raw step dict into an :class:`ExecutableStep`."""
    required = {"step_id", "title", "step_type", "description", "action", "expected_result"}
    missing = required - set(raw.keys())
    if missing:
        raise ValueError(f"Step missing required fields: {missing}")

    step_type_str = raw["step_type"]
    if step_type_str not in STEP_TYPE_VALUES:
        raise ValueError(
            f"Invalid step_type {step_type_str!r}. Must be one of {STEP_TYPE_VALUES}"
        )

    action = raw.get("action", {})
    if not isinstance(action, dict):
        raise ValueError(f"action must be a dict, got {type(action).__name__}")

    return ExecutableStep(
        step_id=str(raw["step_id"]),
        title=str(raw["title"]),
        step_type=StepType(step_type_str),
        description=str(raw["description"]),
        action=action,
        expected_result=str(raw["expected_result"]),
        timeout_seconds=int(raw.get("timeout_seconds", DEFAULT_STEP_TIMEOUT_SECONDS)),
        depends_on=[str(d) for d in raw.get("depends_on", [])],
        module=page.title,
        original_text=page.content[:500],  # keep a snippet
    )


def validate_steps(raw_steps: list[dict], page: WorkshopPage) -> list[ExecutableStep]:
    """Validate a list of raw step dicts.  Returns valid steps, logs warnings for bad ones."""
    steps: list[ExecutableStep] = []
    for i, raw in enumerate(raw_steps):
        try:
            steps.append(_validate_step(raw, page))
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Skipping invalid step %d: %s", i, exc)
    return steps


# ---------------------------------------------------------------------------
# Code-block heuristic (pre-LLM enrichment)
# ---------------------------------------------------------------------------

_CLI_PREFIXES = ("$", "aws ", "sam ", "cdk ", "npm ", "pip ", "docker ", "kubectl ", "curl ")


def detect_cli_steps_from_code_blocks(page: WorkshopPage) -> list[ExecutableStep]:
    """Quick heuristic: code blocks that look like CLI commands → ExecutableStep.

    This supplements the LLM planner with deterministic extraction.
    """
    steps: list[ExecutableStep] = []
    for idx, block in enumerate(page.code_blocks):
        first_line = block.strip().splitlines()[0] if block.strip() else ""
        if any(first_line.lstrip().startswith(p) for p in _CLI_PREFIXES):
            command = block.strip()
            if command.startswith("$ "):
                command = command[2:]
            steps.append(
                ExecutableStep(
                    step_id=f"{page.module_index}.{page.step_index}.cb{idx}",
                    title=f"CLI command from code block #{idx + 1}",
                    step_type=StepType.CLI_COMMAND,
                    description=f"Execute CLI command from {page.title}",
                    action={"command": command},
                    expected_result="Command completes successfully (exit 0)",
                    module=page.title,
                    original_text=block[:500],
                )
            )
    return steps


# ---------------------------------------------------------------------------
# Bedrock Converse helper
# ---------------------------------------------------------------------------


async def _invoke_bedrock(
    pages_batch: list[WorkshopPage],
    model_id: str,
    bedrock_client: Any | None = None,
) -> list[dict]:
    """Call Bedrock Converse API for a batch of pages and return raw step dicts."""
    import asyncio

    if bedrock_client is None:
        try:
            import boto3
        except ImportError:
            raise RuntimeError(
                "boto3 is required for LLM planning but is not installed.\n"
                "Install it with:  pip install boto3"
            ) from None
        bedrock_client = boto3.client("bedrock-runtime")

    all_raw_steps: list[dict] = []

    for page in pages_batch:
        system_text = _SYSTEM_PROMPT.format(step_types=", ".join(STEP_TYPE_VALUES))
        user_text = _build_user_message(page)

        # Converse API (synchronous boto3, run in executor)
        def _call(sys_text: str = system_text, usr_text: str = user_text) -> dict:
            return bedrock_client.converse(
                modelId=model_id,
                system=[{"text": sys_text}],
                messages=[{"role": "user", "content": [{"text": usr_text}]}],
                inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
            )

        try:
            response = await asyncio.get_event_loop().run_in_executor(None, _call)
        except Exception as exc:
            logger.warning("Bedrock API call failed for page %s: %s", page.title, exc)
            continue

        # Extract text from response
        output_text = ""
        output_message = response.get("output", {}).get("message", {})
        for block in output_message.get("content", []):
            if "text" in block:
                output_text += block["text"]

        if not output_text.strip():
            logger.warning("Empty LLM response for page %s", page.title)
            continue

        try:
            raw_steps = _parse_llm_response(output_text)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse LLM response for %s: %s", page.title, exc)
            continue

        # Tag with page info for validation
        for step_dict in raw_steps:
            step_dict["_page"] = page
        all_raw_steps.extend(raw_steps)

    return all_raw_steps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def plan_steps(
    pages: list[WorkshopPage],
    model_id: str = DEFAULT_MODEL_ID,
    dry_run: bool = False,
    bedrock_client: Any | None = None,
) -> list[ExecutableStep]:
    """Convert scraped workshop pages into executable steps.

    Parameters
    ----------
    pages:
        Output of :func:`scraper.scrape_workshop`.
    model_id:
        Bedrock model / inference-profile ID.
    dry_run:
        If ``True``, only run the deterministic code-block detection (no LLM call).
    bedrock_client:
        Optional pre-configured ``boto3`` bedrock-runtime client (useful for testing).

    Returns
    -------
    list[ExecutableStep]
        Ordered steps ready for execution.
    """
    if not pages:
        return []

    if not model_id or not model_id.strip():
        raise ValueError("model_id must not be empty")

    all_steps: list[ExecutableStep] = []

    # 1) Deterministic: extract obvious CLI commands from code blocks
    for page in pages:
        cli_steps = detect_cli_steps_from_code_blocks(page)
        all_steps.extend(cli_steps)

    if dry_run:
        logger.info("Dry-run: returning %d deterministic steps (no LLM)", len(all_steps))
        return all_steps

    # 2) LLM-based planning
    raw_steps = await _invoke_bedrock(pages, model_id, bedrock_client=bedrock_client)

    for raw in raw_steps:
        page = raw.pop("_page", None)
        if page is None:
            continue
        try:
            step = _validate_step(raw, page)
            all_steps.append(step)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Skipping invalid LLM step: %s", exc)

    # 3) Deduplicate by step_id (prefer LLM version if duplicated)
    seen: dict[str, ExecutableStep] = {}
    for step in all_steps:
        seen[step.step_id] = step
    deduped = list(seen.values())

    # 4) Sort by step_id
    def _sort_key(s: ExecutableStep) -> list[int]:
        parts = re.split(r"[.\-]", re.sub(r"[^0-9.\-]", "", s.step_id) or "0")
        return [int(p) for p in parts if p.isdigit()] or [0]

    deduped.sort(key=_sort_key)

    logger.info("Planned %d executable steps from %d pages", len(deduped), len(pages))
    return deduped
