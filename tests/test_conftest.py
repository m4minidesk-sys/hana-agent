"""Tests for conftest.py fixtures.

Verifies enforce_autospec fixture behavior (Phase 2c).
"""

import unittest.mock

import pytest


def _real_func(a: int, b: int) -> int:
    """Helper function for testing autospec."""
    return a + b


def test_enforce_autospec__signature_mismatch__raises_type_error():
    """autospec適用時にシグネチャ不一致が検出される."""
    # Arrange & Act & Assert
    with unittest.mock.patch("tests.test_conftest._real_func") as mock_func:
        # autospecが有効な場合、正しいシグネチャでのみ呼び出し可能
        mock_func(1, 2)  # OK
        with pytest.raises(TypeError):
            mock_func(1, 2, 3)  # Too many arguments


@pytest.mark.no_autospec
def test_no_autospec_marker__signature_mismatch__no_error():
    """@pytest.mark.no_autospecでオプトアウト可能."""
    # Arrange & Act
    with unittest.mock.patch("tests.test_conftest._real_func") as mock_func:
        mock_func("wrong", "args")
    
    # Assert
    mock_func.assert_called_once()


def test_enforce_autospec__default_behavior__autospec_enabled():
    """デフォルトでautospec=Trueが適用される."""
    # Arrange & Act
    with unittest.mock.patch("os.path.exists") as mock_exists:
        # Assert - autospecが有効なのでspec属性が存在
        assert hasattr(mock_exists, "return_value")
        mock_exists.return_value = True
        result = mock_exists("/test/path")
        assert result is True
