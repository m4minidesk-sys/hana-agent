"""Console Authenticator — automated AWS Console login (AC-72).

Supports three authentication methods:

1. **IAM User** — account ID + username + password (from env ``YUI_CONSOLE_PASSWORD``).
2. **Federation** — STS ``GetFederationToken`` → Console sign-in URL.
3. **SSO** — IAM Identity Center portal URL → browser flow.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AWS_CONSOLE_SIGNIN_URL = "https://signin.aws.amazon.com/console"
AWS_FEDERATION_URL = "https://signin.aws.amazon.com/federation"
AWS_CONSOLE_HOME = "https://console.aws.amazon.com/"

IAM_LOGIN_URL_TEMPLATE = "https://{account_id}.signin.aws.amazon.com/console"

DEFAULT_LOGIN_TIMEOUT_MS = 60_000
DEFAULT_NAVIGATION_TIMEOUT_MS = 30_000

_SELECTORS = {
    "account_id_input": "#account",
    "username_input": "#username",
    "password_input": "#password",
    "signin_button": "#signin_button",
    "next_button": "#next_button",
    "alt_account_input": "input[name='account']",
    "alt_username_input": "input[name='username']",
    "alt_password_input": "input[name='password']",
    "alt_signin_button": "button[type='submit']",
    "sso_email_input": "#awsui-input-0",
    "sso_next_button": "button[data-testid='submit-button']",
}


class ConsoleAuthMethod(Enum):
    """Supported AWS Console authentication methods."""

    IAM_USER = "iam_user"
    FEDERATION = "federation"
    SSO = "sso"


class ConsoleAuthError(Exception):
    """Raised when Console authentication fails."""


class ConsoleAuthenticator:
    """Automate AWS Console login via Playwright."""

    def __init__(
        self,
        login_timeout_ms: int = DEFAULT_LOGIN_TIMEOUT_MS,
        navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
    ) -> None:
        self.login_timeout_ms = login_timeout_ms
        self.navigation_timeout_ms = navigation_timeout_ms

    async def login(self, page: Any, config: dict) -> bool:
        """Authenticate to the AWS Console."""
        method_str = config.get("method", "iam_user")
        try:
            method = ConsoleAuthMethod(method_str)
        except ValueError:
            raise ValueError(
                f"Unsupported auth method: {method_str!r}. "
                f"Must be one of: {[m.value for m in ConsoleAuthMethod]}"
            )

        logger.info("Attempting Console login via %s", method.value)

        if method == ConsoleAuthMethod.IAM_USER:
            return await self._login_iam_user(page, config)
        elif method == ConsoleAuthMethod.FEDERATION:
            return await self._login_federation(page, config)
        elif method == ConsoleAuthMethod.SSO:
            return await self._login_sso(page, config)

        raise ConsoleAuthError(f"Unhandled auth method: {method}")  # pragma: no cover

    async def _login_iam_user(self, page: Any, config: dict) -> bool:
        """Login with IAM user credentials."""
        account_id = config.get("account_id")
        username = config.get("username")
        password = config.get("password") or os.environ.get("YUI_CONSOLE_PASSWORD")

        if not account_id:
            raise ValueError("account_id is required for IAM user login")
        if not username:
            raise ValueError("username is required for IAM user login")
        if not password:
            raise ValueError(
                "password is required for IAM user login. "
                "Set via config or YUI_CONSOLE_PASSWORD environment variable."
            )

        login_url = IAM_LOGIN_URL_TEMPLATE.format(account_id=account_id)

        try:
            await page.goto(login_url, wait_until="networkidle",
                            timeout=self.navigation_timeout_ms)

            account_input = await page.query_selector(_SELECTORS["account_id_input"])
            if account_input is None:
                account_input = await page.query_selector(_SELECTORS["alt_account_input"])
            if account_input:
                await account_input.fill(account_id)
                next_btn = await page.query_selector(_SELECTORS["next_button"])
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle",
                                                   timeout=self.navigation_timeout_ms)

            username_input = await page.query_selector(_SELECTORS["username_input"])
            if username_input is None:
                username_input = await page.query_selector(_SELECTORS["alt_username_input"])
            if username_input is None:
                raise ConsoleAuthError("Cannot find username input field")
            await username_input.fill(username)

            password_input = await page.query_selector(_SELECTORS["password_input"])
            if password_input is None:
                password_input = await page.query_selector(_SELECTORS["alt_password_input"])
            if password_input is None:
                raise ConsoleAuthError("Cannot find password input field")
            await password_input.fill(password)

            signin_btn = await page.query_selector(_SELECTORS["signin_button"])
            if signin_btn is None:
                signin_btn = await page.query_selector(_SELECTORS["alt_signin_button"])
            if signin_btn is None:
                raise ConsoleAuthError("Cannot find sign-in button")
            await signin_btn.click()

            await page.wait_for_load_state("networkidle",
                                           timeout=self.login_timeout_ms)

            if await self._is_console_page(page):
                logger.info("IAM user login successful for %s", username)
                return True

            error_msg = await self._get_login_error(page)
            raise ConsoleAuthError(
                f"IAM user login failed: {error_msg or 'unknown error'}"
            )

        except ConsoleAuthError:
            raise
        except Exception as exc:
            raise ConsoleAuthError(f"IAM user login failed: {exc}") from exc

    async def _login_federation(self, page: Any, config: dict) -> bool:
        """Login via STS GetFederationToken → Console sign-in URL."""
        sts_client = config.get("sts_client")
        if sts_client is None:
            raise ValueError("sts_client is required for federation login")

        federation_name = config.get("federation_name", "yui-workshop")
        federation_policy = config.get("federation_policy")
        duration_seconds = config.get("duration_seconds", 3600)

        try:
            kwargs: dict[str, Any] = {
                "Name": federation_name,
                "DurationSeconds": duration_seconds,
            }
            if federation_policy:
                if isinstance(federation_policy, dict):
                    kwargs["Policy"] = json.dumps(federation_policy)
                else:
                    kwargs["Policy"] = str(federation_policy)

            response = sts_client.get_federation_token(**kwargs)
            credentials = response["Credentials"]

            signin_url = self._build_federation_url(credentials)

            await page.goto(signin_url, wait_until="networkidle",
                            timeout=self.login_timeout_ms)

            if await self._is_console_page(page):
                logger.info("Federation login successful")
                return True

            raise ConsoleAuthError("Federation login did not reach Console")

        except ConsoleAuthError:
            raise
        except Exception as exc:
            raise ConsoleAuthError(f"Federation login failed: {exc}") from exc

    def _build_federation_url(self, credentials: dict) -> str:
        """Build the AWS Console federation sign-in URL from STS credentials."""
        session_json = json.dumps({
            "sessionId": credentials["AccessKeyId"],
            "sessionKey": credentials["SecretAccessKey"],
            "sessionToken": credentials["SessionToken"],
        })

        params = urllib.parse.urlencode({
            "Action": "getSigninToken",
            "SessionDuration": "3600",
            "Session": session_json,
        })

        return f"{AWS_FEDERATION_URL}?{params}"

    def build_federation_login_url(self, signin_token: str) -> str:
        """Build the Console login URL from a sign-in token."""
        params = urllib.parse.urlencode({
            "Action": "login",
            "Issuer": "yui-agent",
            "Destination": AWS_CONSOLE_HOME,
            "SigninToken": signin_token,
        })
        return f"{AWS_FEDERATION_URL}?{params}"

    async def _login_sso(self, page: Any, config: dict) -> bool:
        """Login via IAM Identity Center (SSO) portal."""
        portal_url = config.get("portal_url")
        if not portal_url:
            raise ValueError("portal_url is required for SSO login")

        try:
            await page.goto(portal_url, wait_until="networkidle",
                            timeout=self.navigation_timeout_ms)

            await page.wait_for_url(
                "**/console.aws.amazon.com/**",
                timeout=self.login_timeout_ms,
            )

            if await self._is_console_page(page):
                logger.info("SSO login successful")
                return True

            raise ConsoleAuthError("SSO login did not reach Console")

        except ConsoleAuthError:
            raise
        except Exception as exc:
            raise ConsoleAuthError(f"SSO login failed: {exc}") from exc

    async def _is_console_page(self, page: Any) -> bool:
        """Check whether the current page looks like the AWS Console."""
        url = page.url
        return "console.aws.amazon.com" in url or "console.amazonaws.com" in url

    async def _get_login_error(self, page: Any) -> str:
        """Try to extract an error message from the login page."""
        error_selectors = [
            "#error_message",
            ".error-message",
            "[class*='error']",
            "#alertMessage",
        ]
        for selector in error_selectors:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                if text.strip():
                    return text.strip()
        return ""
