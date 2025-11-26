"""
Workspace Manager Interface - Following Dependency Inversion Principle
Allows different storage backends (filesystem, cloud, etc.)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any


class IWorkspaceManager(ABC):
    """
    Abstract interface for workspace management
    Enables swapping filesystem with cloud storage or other backends
    """

    @abstractmethod
    async def create_workspace(
        self,
        task_id: str,
        env_type: str,
    ) -> Path:
        """Create an isolated workspace for a task"""
        pass

    @abstractmethod
    async def clone_repository(
        self,
        workspace: Path,
        repo_url: str,
        commit_hash: Optional[str] = None,
        branch: Optional[str] = None,
        depth: int = 1,
    ) -> bool:
        """Clone a git repository into the workspace"""
        pass

    @abstractmethod
    async def setup_claude_config(
        self,
        workspace: Path,
        claude_md_content: str,
        commands: Optional[Dict[str, str]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Setup Claude Code configuration in workspace"""
        pass

    @abstractmethod
    async def write_input_files(
        self,
        workspace: Path,
        inputs: Dict[str, Any],
    ) -> None:
        """Write input data to workspace files"""
        pass

    @abstractmethod
    async def run_hook(
        self,
        workspace: Path,
        hook_script: str,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 60,
    ) -> tuple[bool, str]:
        """Run a hook script in the workspace"""
        pass

    @abstractmethod
    async def cleanup_workspace(self, task_id: str) -> bool:
        """Remove a workspace"""
        pass

    @abstractmethod
    async def cleanup_old_workspaces(self) -> int:
        """Cleanup workspaces older than configured time"""
        pass

    @abstractmethod
    def get_workspace_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get workspace metadata"""
        pass
