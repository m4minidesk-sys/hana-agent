"""Tests for Console Authenticator (AC-72). All mocked."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yui.workshop.console_auth import (
    AWS_FEDERATION_URL, ConsoleAuthError, ConsoleAuthenticator,
    ConsoleAuthMethod, IAM_LOGIN_URL_TEMPLATE,
)


@pytest.fixture
def authenticator():
    return ConsoleAuthenticator(login_timeout_ms=5000, navigation_timeout_ms=3000)


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.url = "https://console.aws.amazon.com/console/home"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    return page


@pytest.fixture
def mock_page_with_form(mock_page):
    account_input = AsyncMock()
    username_input = AsyncMock()
    password_input = AsyncMock()
    signin_button = AsyncMock()

    async def _query_selector(selector):
        mapping = {
            "#account": account_input, "#username": username_input,
            "#password": password_input, "#signin_button": signin_button,
            "#next_button": None, "#error_message": None,
            ".error-message": None, "[class*='error']": None,
            "#alertMessage": None, "input[name='account']": None,
            "input[name='username']": None, "input[name='password']": None,
            "button[type='submit']": None,
        }
        return mapping.get(selector)

    mock_page.query_selector = AsyncMock(side_effect=_query_selector)
    mock_page._account_input = account_input
    mock_page._username_input = username_input
    mock_page._password_input = password_input
    mock_page._signin_button = signin_button
    return mock_page


class TestConsoleAuthMethod:
    def test_iam_user_value(self):
        assert ConsoleAuthMethod.IAM_USER.value == "iam_user"

    def test_federation_value(self):
        assert ConsoleAuthMethod.FEDERATION.value == "federation"

    def test_sso_value(self):
        assert ConsoleAuthMethod.SSO.value == "sso"

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError):
            ConsoleAuthMethod("invalid")


class TestIAMUserLogin:
    @pytest.mark.asyncio
    async def test_iam_login_success(self, authenticator, mock_page_with_form):
        config = {"method": "iam_user", "account_id": "123456789012",
                  "username": "testuser", "password": "s3cr3t!"}
        result = await authenticator.login(mock_page_with_form, config)
        assert result is True
        mock_page_with_form.goto.assert_called_once()
        mock_page_with_form._username_input.fill.assert_called_once_with("testuser")
        mock_page_with_form._password_input.fill.assert_called_once_with("s3cr3t!")
        mock_page_with_form._signin_button.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_iam_login_uses_env_password(self, authenticator, mock_page_with_form):
        with patch.dict(os.environ, {"YUI_CONSOLE_PASSWORD": "env_password"}):
            config = {"method": "iam_user", "account_id": "123456789012", "username": "testuser"}
            result = await authenticator.login(mock_page_with_form, config)
            assert result is True
            mock_page_with_form._password_input.fill.assert_called_once_with("env_password")

    @pytest.mark.asyncio
    async def test_iam_login_missing_account_id(self, authenticator, mock_page):
        with pytest.raises(ValueError, match="account_id"):
            await authenticator.login(mock_page, {"method": "iam_user", "username": "t", "password": "t"})

    @pytest.mark.asyncio
    async def test_iam_login_missing_username(self, authenticator, mock_page):
        with pytest.raises(ValueError, match="username"):
            await authenticator.login(mock_page, {"method": "iam_user", "account_id": "123", "password": "t"})

    @pytest.mark.asyncio
    async def test_iam_login_missing_password(self, authenticator, mock_page):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("YUI_CONSOLE_PASSWORD", None)
            with pytest.raises(ValueError, match="password"):
                await authenticator.login(mock_page,
                    {"method": "iam_user", "account_id": "123456789012", "username": "testuser"})

    @pytest.mark.asyncio
    async def test_iam_login_navigation_failure(self, authenticator, mock_page_with_form):
        mock_page_with_form.goto.side_effect = Exception("Connection refused")
        with pytest.raises(ConsoleAuthError, match="Connection refused"):
            await authenticator.login(mock_page_with_form,
                {"method": "iam_user", "account_id": "123", "username": "t", "password": "t"})

    @pytest.mark.asyncio
    async def test_iam_login_auth_failure(self, authenticator, mock_page_with_form):
        mock_page_with_form.url = "https://signin.aws.amazon.com/error"
        error_el = AsyncMock()
        error_el.inner_text = AsyncMock(return_value="Invalid username or password")
        original_qs = mock_page_with_form.query_selector.side_effect

        async def _with_error(selector):
            if selector == "#error_message":
                return error_el
            return await original_qs(selector) if callable(original_qs) else None

        mock_page_with_form.query_selector = AsyncMock(side_effect=_with_error)
        with pytest.raises(ConsoleAuthError, match="Invalid username or password"):
            await authenticator.login(mock_page_with_form,
                {"method": "iam_user", "account_id": "123", "username": "t", "password": "wrong"})

    @pytest.mark.asyncio
    async def test_iam_login_url_format(self, authenticator, mock_page_with_form):
        config = {"method": "iam_user", "account_id": "111222333444",
                  "username": "testuser", "password": "s3cr3t!"}
        await authenticator.login(mock_page_with_form, config)
        expected_url = IAM_LOGIN_URL_TEMPLATE.format(account_id="111222333444")
        mock_page_with_form.goto.assert_called_once_with(
            expected_url, wait_until="networkidle", timeout=3000)


class TestFederationLogin:
    @pytest.mark.asyncio
    async def test_federation_login_success(self, authenticator, mock_page):
        mock_sts = MagicMock()
        mock_sts.get_federation_token.return_value = {
            "Credentials": {"AccessKeyId": "AKIA", "SecretAccessKey": "secret",
                            "SessionToken": "token", "Expiration": "2026-02-27T00:00:00Z"}}
        result = await authenticator.login(mock_page,
            {"method": "federation", "sts_client": mock_sts, "federation_name": "yui-test"})
        assert result is True
        mock_sts.get_federation_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_federation_login_with_policy(self, authenticator, mock_page):
        mock_sts = MagicMock()
        mock_sts.get_federation_token.return_value = {
            "Credentials": {"AccessKeyId": "AKIA", "SecretAccessKey": "s",
                            "SessionToken": "t", "Expiration": "2026-02-27T00:00:00Z"}}
        policy = {"Version": "2012-10-17", "Statement": []}
        await authenticator.login(mock_page,
            {"method": "federation", "sts_client": mock_sts, "federation_policy": policy})
        assert "Policy" in mock_sts.get_federation_token.call_args[1]

    @pytest.mark.asyncio
    async def test_federation_login_missing_sts_client(self, authenticator, mock_page):
        with pytest.raises(ValueError, match="sts_client"):
            await authenticator.login(mock_page, {"method": "federation"})

    @pytest.mark.asyncio
    async def test_federation_login_sts_error(self, authenticator, mock_page):
        mock_sts = MagicMock()
        mock_sts.get_federation_token.side_effect = Exception("AccessDenied")
        with pytest.raises(ConsoleAuthError, match="AccessDenied"):
            await authenticator.login(mock_page, {"method": "federation", "sts_client": mock_sts})

    @pytest.mark.asyncio
    async def test_federation_not_reaching_console(self, authenticator, mock_page):
        mock_page.url = "https://signin.aws.amazon.com/error"
        mock_sts = MagicMock()
        mock_sts.get_federation_token.return_value = {
            "Credentials": {"AccessKeyId": "AKIA", "SecretAccessKey": "s",
                            "SessionToken": "t", "Expiration": "2026-02-27T00:00:00Z"}}
        with pytest.raises(ConsoleAuthError, match="did not reach Console"):
            await authenticator.login(mock_page, {"method": "federation", "sts_client": mock_sts})

    def test_build_federation_login_url(self, authenticator):
        url = authenticator.build_federation_login_url("my-signin-token")
        assert AWS_FEDERATION_URL in url
        assert "Action=login" in url
        assert "SigninToken=my-signin-token" in url


class TestSSOLogin:
    @pytest.mark.asyncio
    async def test_sso_login_success(self, authenticator, mock_page):
        result = await authenticator.login(mock_page,
            {"method": "sso", "portal_url": "https://my-org.awsapps.com/start"})
        assert result is True

    @pytest.mark.asyncio
    async def test_sso_login_missing_portal_url(self, authenticator, mock_page):
        with pytest.raises(ValueError, match="portal_url"):
            await authenticator.login(mock_page, {"method": "sso"})

    @pytest.mark.asyncio
    async def test_sso_login_timeout(self, authenticator, mock_page):
        mock_page.wait_for_url.side_effect = Exception("Timeout 5000ms exceeded")
        with pytest.raises(ConsoleAuthError, match="Timeout"):
            await authenticator.login(mock_page,
                {"method": "sso", "portal_url": "https://my-org.awsapps.com/start"})


class TestAuthDispatch:
    @pytest.mark.asyncio
    async def test_invalid_method_raises(self, authenticator, mock_page):
        with pytest.raises(ValueError, match="Unsupported auth method"):
            await authenticator.login(mock_page, {"method": "kerberos"})

    @pytest.mark.asyncio
    async def test_default_method_is_iam_user(self, authenticator, mock_page_with_form):
        result = await authenticator.login(mock_page_with_form,
            {"account_id": "123456789012", "username": "testuser", "password": "s3cr3t!"})
        assert result is True

    def test_authenticator_default_timeouts(self):
        auth = ConsoleAuthenticator()
        assert auth.login_timeout_ms == 60_000
        assert auth.navigation_timeout_ms == 30_000

    def test_authenticator_custom_timeouts(self):
        auth = ConsoleAuthenticator(login_timeout_ms=10_000, navigation_timeout_ms=5_000)
        assert auth.login_timeout_ms == 10_000
        assert auth.navigation_timeout_ms == 5_000
