"""Tests for HANA file operations tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from hana.local_tools.file_ops import configure, edit_file, read_file, write_file


@pytest.fixture(autouse=True)
def _setup_config() -> None:
    """Configure file tool with test settings."""
    configure({
        "enabled": True,
        "max_read_size": 51200,
        "max_read_lines": 2000,
    })


class TestReadFile:
    """Tests for read_file tool."""

    def test_read_existing_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3\n")

        result = read_file(file_path=str(test_file))
        assert "line 1" in result["content"]
        assert result["lines"] == 3

    def test_read_nonexistent_file(self) -> None:
        result = read_file(file_path="/nonexistent/file.txt")
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_read_with_offset(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 0\nline 1\nline 2\n")

        result = read_file(file_path=str(test_file), offset=1)
        assert "line 0" not in result["content"]
        assert "line 1" in result["content"]

    def test_read_with_limit(self, tmp_path: Path) -> None:
        lines = "\n".join(f"line {i}" for i in range(100))
        test_file = tmp_path / "test.txt"
        test_file.write_text(lines)

        result = read_file(file_path=str(test_file), limit=5)
        assert result["truncated"] is True

    def test_read_binary_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03")

        result = read_file(file_path=str(test_file))
        assert "Binary file" in result["content"]


class TestWriteFile:
    """Tests for write_file tool."""

    def test_write_new_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "new_file.txt"
        result = write_file(file_path=str(file_path), content="hello world")

        assert result["bytes_written"] > 0
        assert file_path.read_text() == "hello world"

    def test_write_creates_dirs(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a" / "b" / "c" / "file.txt"
        result = write_file(file_path=str(file_path), content="nested")

        assert result["bytes_written"] > 0
        assert file_path.read_text() == "nested"

    def test_write_overwrites(self, tmp_path: Path) -> None:
        file_path = tmp_path / "existing.txt"
        file_path.write_text("old content")

        write_file(file_path=str(file_path), content="new content")
        assert file_path.read_text() == "new content"


class TestEditFile:
    """Tests for edit_file tool."""

    def test_simple_edit(self, tmp_path: Path) -> None:
        file_path = tmp_path / "edit.txt"
        file_path.write_text("hello world")

        result = edit_file(file_path=str(file_path), old_text="world", new_text="HANA")
        assert result["replacements"] == 1
        assert file_path.read_text() == "hello HANA"

    def test_edit_multiple_occurrences(self, tmp_path: Path) -> None:
        file_path = tmp_path / "edit.txt"
        file_path.write_text("foo bar foo baz foo")

        result = edit_file(file_path=str(file_path), old_text="foo", new_text="qux")
        assert result["replacements"] == 3

    def test_edit_text_not_found(self, tmp_path: Path) -> None:
        file_path = tmp_path / "edit.txt"
        file_path.write_text("hello world")

        result = edit_file(file_path=str(file_path), old_text="xyz", new_text="abc")
        assert result["replacements"] == 0
        assert "not found" in result.get("error", "").lower()

    def test_edit_nonexistent_file(self) -> None:
        result = edit_file(file_path="/nonexistent/file.txt", old_text="a", new_text="b")
        assert "error" in result
