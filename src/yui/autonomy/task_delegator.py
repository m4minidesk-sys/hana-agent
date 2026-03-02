"""Task delegator for L1→L2 hierarchy.

L1 (YUI) delegates tasks to L2 (sessions_spawn sub-agent) which manages L3 (Kiro CLI).
"""

import uuid
from pathlib import Path
from typing import Tuple, Union

from yui.autonomy.file_interface import FileInterface


class TaskDelegator:
    """L1 task delegation logic."""

    def __init__(self, workspace_root: Union[Path, str] = "~/.yui/workspace"):
        self.file_interface = FileInterface(workspace_root)

    def create_task(self, task_type: str = "general") -> Tuple[str, Path]:
        """Create new task with unique ID and directory.
        
        Args:
            task_type: Type of task (workshop/code/general)
            
        Returns:
            Tuple of (task_id, task_path)
        """
        task_id = str(uuid.uuid4())
        task_path = self.file_interface.create_task_dir(task_id)
        
        # Initialize meta.json
        meta = self.file_interface.create_initial_meta(task_id)
        meta["task_type"] = task_type
        self.file_interface.write_meta(task_id, meta)
        
        return task_id, task_path

    def classify_task(self, instruction: str) -> str:
        """Classify task type from instruction text.
        
        Args:
            instruction: User instruction text
            
        Returns:
            Task type: "workshop", "code", or "general"
        """
        lower = instruction.lower()
        
        if any(kw in lower for kw in ["workshop", "ワークショップ", "ws"]):
            return "workshop"
        elif any(kw in lower for kw in ["code", "implement", "コード", "実装"]):
            return "code"
        else:
            return "general"
