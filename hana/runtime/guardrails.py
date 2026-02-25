"""HANA Bedrock Guardrails integration — input/output content filtering."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GuardrailsFilter:
    """Bedrock Guardrails wrapper for content filtering.

    Applies input and output filtering using Amazon Bedrock Guardrails
    to prevent harmful, toxic, or policy-violating content.

    Args:
        config: HANA configuration dictionary.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        gr_config = config.get("guardrails", {})
        self.enabled = gr_config.get("enabled", False)
        self.guardrail_id = gr_config.get("guardrail_id", "")
        self.guardrail_version = gr_config.get("guardrail_version", "DRAFT")
        self.region = config.get("agent", {}).get("region", "us-east-1")

        self._client: Any = None

        if self.enabled and self.guardrail_id:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize the Bedrock Runtime client for guardrails."""
        try:
            import boto3

            session = boto3.Session(region_name=self.region)
            self._client = session.client("bedrock-runtime", region_name=self.region)
            logger.info(
                "Guardrails initialized: id=%s, version=%s",
                self.guardrail_id,
                self.guardrail_version,
            )
        except Exception as exc:
            logger.error("Failed to initialize guardrails client: %s", exc)
            self.enabled = False

    def filter_input(self, text: str, source: str = "INPUT") -> dict[str, Any]:
        """Apply guardrail to input text.

        Args:
            text: Input text to filter.
            source: Source identifier (for logging).

        Returns:
            Dictionary with ``allowed`` (bool), ``text`` (filtered or original),
            and optionally ``action`` and ``outputs``.
        """
        if not self.enabled or not self._client:
            return {"allowed": True, "text": text}

        try:
            response = self._client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.guardrail_version,
                source=source,
                content=[{"text": {"text": text}}],
            )

            action = response.get("action", "NONE")
            allowed = action != "GUARDRAIL_INTERVENED"

            result: dict[str, Any] = {
                "allowed": allowed,
                "action": action,
            }

            if allowed:
                result["text"] = text
            else:
                # Extract guardrail output (filtered/replacement text)
                outputs = response.get("outputs", [])
                if outputs:
                    result["text"] = outputs[0].get("text", "")
                else:
                    result["text"] = "[Content blocked by guardrails]"

                assessments = response.get("assessments", [])
                if assessments:
                    result["assessments"] = assessments

                logger.warning(
                    "Guardrail blocked %s: action=%s",
                    source,
                    action,
                )

            return result

        except Exception as exc:
            logger.error("Guardrail filter failed: %s", exc)
            # Fail-open: allow the content if guardrails are unavailable
            return {"allowed": True, "text": text, "error": str(exc)}

    def filter_output(self, text: str) -> dict[str, Any]:
        """Apply guardrail to output text.

        Args:
            text: Output text to filter.

        Returns:
            Same format as filter_input.
        """
        return self.filter_input(text, source="OUTPUT")

    @property
    def is_active(self) -> bool:
        """Check if guardrails are configured and active."""
        return self.enabled and self._client is not None and bool(self.guardrail_id)
