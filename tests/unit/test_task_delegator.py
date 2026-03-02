"""Unit tests for task_delegator.py."""

import uuid
from pathlib import Path

import pytest

from yui.autonomy.task_delegator import TaskDelegator


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace."""
    return tmp_path / "workspace"


@pytest.fixture
def task_delegator(temp_workspace):
    """Create TaskDelegator instance."""
    return TaskDelegator(temp_workspace)


def test_create_task_generates_uuid(task_delegator):
    """T-YUI-H-01: TaskDelegator can generate task_id and create tasks/ directory."""
    task_id, task_path = task_delegator.create_task()
    
    # Verify UUID format
    uuid.UUID(task_id)  # Raises ValueError if invalid
    
    # Verify directory created
    assert task_path.exists()
    assert task_path.is_dir()
    
    # Verify meta.json created
    meta_path = task_path / "meta.json"
    assert meta_path.exists()


def test_create_task_with_type(task_delegator):
    """Test task creation with specific type."""
    task_id, task_path = task_delegator.create_task(task_type="workshop")
    
    meta = task_delegator.file_interface.read_meta(task_id)
    assert meta["task_type"] == "workshop"
    assert meta["status"] == "running"


def test_classify_task_workshop(task_delegator):
    """Test workshop task classification."""
    assert task_delegator.classify_task("run workshop on testing") == "workshop"
    assert task_delegator.classify_task("ワークショップを実行") == "workshop"
    assert task_delegator.classify_task("ws execution") == "workshop"


def test_classify_task_code(task_delegator):
    """Test code task classification."""
    assert task_delegator.classify_task("implement new feature") == "code"
    assert task_delegator.classify_task("write code for API") == "code"
    assert task_delegator.classify_task("コードを実装してください") == "code"


def test_classify_task_general(task_delegator):
    """Test general task classification."""
    assert task_delegator.classify_task("analyze the data") == "general"
    assert task_delegator.classify_task("create a report") == "general"
    assert task_delegator.classify_task("random instruction") == "general"


def test_multiple_tasks_unique_ids(task_delegator):
    """Test that multiple tasks get unique IDs."""
    task_id1, _ = task_delegator.create_task()
    task_id2, _ = task_delegator.create_task()
    
    assert task_id1 != task_id2
    
    # Both should be valid UUIDs
    uuid.UUID(task_id1)
    uuid.UUID(task_id2)
