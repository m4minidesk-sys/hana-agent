"""Data models for Workshop Testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StepType(Enum):
    """Classification of an executable workshop step."""

    CONSOLE_NAVIGATE = "console_navigate"
    CONSOLE_ACTION = "console_action"
    CONSOLE_VERIFY = "console_verify"
    CLI_COMMAND = "cli_command"
    CLI_CHECK = "cli_check"
    CFN_DEPLOY = "cfn_deploy"
    HTTP_TEST = "http_test"
    CODE_RUN = "code_run"
    WAIT = "wait"
    MANUAL_STEP = "manual_step"


class StepResult(Enum):
    """Outcome of executing a single step."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    TIMEOUT = "timeout"
    NOT_RUN = "not_run"


@dataclass
class WorkshopPage:
    """A single page scraped from a Workshop Studio workshop."""

    title: str
    url: str
    content: str  # full text content
    module_index: int
    step_index: int
    code_blocks: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # image URLs


@dataclass
class ExecutableStep:
    """An actionable step derived from workshop content via LLM planning."""

    step_id: str  # e.g., "1.3.2"
    title: str
    step_type: StepType
    description: str  # human-readable
    action: dict  # type-specific payload
    expected_result: str  # for validation
    timeout_seconds: int = 300
    depends_on: list[str] = field(default_factory=list)
    module: str = ""
    original_text: str = ""  # raw text from workshop


@dataclass
class StepOutcome:
    """Result of executing a single step."""

    step: ExecutableStep
    result: StepResult
    actual_output: str = ""
    screenshot_path: Optional[str] = None
    video_path: Optional[str] = None
    error_message: str = ""
    duration_seconds: float = 0.0
    timestamp: str = ""


@dataclass
class TestRun:
    """A complete test run across an entire workshop."""

    test_id: str
    workshop_url: str
    workshop_title: str
    steps: list[ExecutableStep] = field(default_factory=list)
    outcomes: list[StepOutcome] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    total_duration_seconds: float = 0.0
    output_dir: str = ""
