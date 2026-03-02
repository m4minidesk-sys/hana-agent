"""Unit tests for file_interface.py."""

import json
from pathlib import Path

import pytest

from yui.autonomy.file_interface import FileInterface


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace."""
    return tmp_path / "workspace"


@pytest.fixture
def file_interface(temp_workspace):
    """Create FileInterface instance."""
    return FileInterface(temp_workspace)


def test_create_task_dir(file_interface):
    """T-YUI-H-01: TaskDelegator can generate task_id and create tasks/ directory."""
    task_id = "test-task-123"
    task_path = file_interface.create_task_dir(task_id)
    
    assert task_path.exists()
    assert task_path.is_dir()
    assert task_path.name == task_id


def test_write_and_read_meta(file_interface):
    """T-YUI-H-03: FileInterface can read/write meta.json."""
    task_id = "test-task-456"
    file_interface.create_task_dir(task_id)
    
    meta = {
        "task_id": task_id,
        "status": "running",
        "l3_pids": {},
        "l3_results": {},
    }
    
    file_interface.write_meta(task_id, meta)
    read_meta = file_interface.read_meta(task_id)
    
    assert read_meta["task_id"] == task_id
    assert read_meta["status"] == "running"
    assert read_meta["l3_pids"] == {}


def test_write_summary_truncation(file_interface):
    """T-YUI-H-04: FileInterface can generate summary.md (within 2000 chars)."""
    task_id = "test-task-789"
    file_interface.create_task_dir(task_id)
    
    long_content = "x" * 3000
    summary_path = file_interface.write_summary(task_id, long_content, max_chars=2000)
    
    assert summary_path.exists()
    content = summary_path.read_text()
    assert len(content) == 2000
    assert content == "x" * 2000


def test_create_initial_meta(file_interface):
    """Test initial meta.json creation."""
    task_id = "test-task-initial"
    file_interface.create_task_dir(task_id)
    
    meta = file_interface.create_initial_meta(task_id)
    
    assert meta["task_id"] == task_id
    assert meta["status"] == "running"
    assert "created_at" in meta
    assert meta["summary_path"] == f"tasks/{task_id}/summary.md"
    assert meta["total_elapsed_sec"] == 0
    
    # Verify it was written to disk
    read_meta = file_interface.read_meta(task_id)
    assert read_meta == meta
