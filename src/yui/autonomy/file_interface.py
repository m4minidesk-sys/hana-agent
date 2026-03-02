"""File interface for L2 task management.

Manages tasks/{task-id}/ directories, meta.json, and summary.md generation.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Union


class FileInterface:
    """Manages task directory structure and metadata."""

    def __init__(self, workspace_root: Union[Path, str] = "~/.yui/workspace"):
        self.workspace_root = Path(workspace_root).expanduser()
        self.tasks_dir = self.workspace_root / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def create_task_dir(self, task_id: str) -> Path:
        """Create tasks/{task-id}/ directory."""
        task_path = self.tasks_dir / task_id
        task_path.mkdir(parents=True, exist_ok=True)
        return task_path

    def write_meta(self, task_id: str, meta: dict[str, Any]) -> None:
        """Write meta.json to tasks/{task-id}/meta.json."""
        task_path = self.tasks_dir / task_id
        meta_path = task_path / "meta.json"
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def read_meta(self, task_id: str) -> dict[str, Any]:
        """Read meta.json from tasks/{task-id}/meta.json."""
        meta_path = self.tasks_dir / task_id / "meta.json"
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def write_summary(self, task_id: str, content: str, max_chars: int = 2000) -> Path:
        """Write summary.md (truncated to max_chars)."""
        task_path = self.tasks_dir / task_id
        summary_path = task_path / "summary.md"
        truncated = content[:max_chars]
        with summary_path.open("w", encoding="utf-8") as f:
            f.write(truncated)
        return summary_path

    def create_initial_meta(self, task_id: str) -> dict[str, Any]:
        """Create initial meta.json structure."""
        meta = {
            "task_id": task_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "status": "running",
            "l3_pids": {},
            "l3_results": {},
            "summary_path": f"tasks/{task_id}/summary.md",
            "total_elapsed_sec": 0,
        }
        self.write_meta(task_id, meta)
        return meta
