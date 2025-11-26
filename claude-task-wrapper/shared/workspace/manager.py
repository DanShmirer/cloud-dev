"""
Workspace Manager - Handles isolated workspace creation per task
Each environment task gets its own workspace with:
- Cloned repository
- CLAUDE.md file
- .claude/commands for custom prompts
- hooks configuration
"""
import json
import os
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from .base import IWorkspaceManager

logger = logging.getLogger(__name__)


class LocalWorkspaceManager(IWorkspaceManager):
    """
    Local filesystem implementation of workspace management
    Implements IWorkspaceManager for dependency inversion
    Following Single Responsibility - only handles workspace lifecycle
    """

    def __init__(
        self,
        base_path: str = "/workspaces",
        cleanup_after_hours: int = 24,
    ):
        self._base_path = Path(base_path)
        self._cleanup_after_hours = cleanup_after_hours
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _get_workspace_path(self, task_id: str) -> Path:
        """Get workspace path for a task"""
        return self._base_path / task_id

    async def create_workspace(
        self,
        task_id: str,
        env_type: str,
    ) -> Path:
        """Create an isolated workspace for a task"""
        workspace = self._get_workspace_path(task_id)

        if workspace.exists():
            logger.warning(f"Workspace {task_id} already exists, removing")
            shutil.rmtree(workspace)

        workspace.mkdir(parents=True)

        # Create .claude directory for commands
        claude_dir = workspace / ".claude" / "commands"
        claude_dir.mkdir(parents=True)

        # Create metadata file
        metadata = {
            "task_id": task_id,
            "env_type": env_type,
            "created_at": datetime.utcnow().isoformat(),
        }
        metadata_file = workspace / ".workspace_metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        logger.info(f"Created workspace at {workspace}")
        return workspace

    async def clone_repository(
        self,
        workspace: Path,
        repo_url: str,
        commit_hash: Optional[str] = None,
        branch: Optional[str] = None,
        depth: int = 1,
    ) -> bool:
        """Clone a git repository into the workspace"""
        repo_dir = workspace / "repo"

        # Build clone command
        clone_cmd = ["git", "clone"]

        if depth:
            clone_cmd.extend(["--depth", str(depth)])

        if branch:
            clone_cmd.extend(["--branch", branch])

        # For specific commits, we need full history
        if commit_hash:
            clone_cmd = ["git", "clone"]  # Remove depth for commit checkout

        clone_cmd.extend([repo_url, str(repo_dir)])

        try:
            # Clone repository
            process = await asyncio.create_subprocess_exec(
                *clone_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300,  # 5 min timeout for large repos
            )

            if process.returncode != 0:
                logger.error(f"Clone failed: {stderr.decode()}")
                return False

            logger.info(f"Cloned {repo_url} to {repo_dir}")

            # Checkout specific commit if provided
            if commit_hash:
                checkout_cmd = ["git", "checkout", commit_hash]
                process = await asyncio.create_subprocess_exec(
                    *checkout_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(repo_dir),
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=60,
                )

                if process.returncode != 0:
                    logger.error(f"Checkout failed: {stderr.decode()}")
                    return False

                logger.info(f"Checked out commit {commit_hash}")

            return True

        except asyncio.TimeoutError:
            logger.error("Repository clone timed out")
            return False
        except Exception as e:
            logger.exception(f"Clone error: {e}")
            return False

    async def setup_claude_config(
        self,
        workspace: Path,
        claude_md_content: str,
        commands: Optional[Dict[str, str]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Setup Claude Code configuration in workspace:
        - CLAUDE.md for context and instructions
        - .claude/commands/*.md for custom slash commands
        - .claude/settings.json for tool permissions
        """
        # Write CLAUDE.md
        claude_md_path = workspace / "CLAUDE.md"
        claude_md_path.write_text(claude_md_content)
        logger.info(f"Created CLAUDE.md at {claude_md_path}")

        # Write custom commands
        if commands:
            commands_dir = workspace / ".claude" / "commands"
            commands_dir.mkdir(parents=True, exist_ok=True)

            for name, content in commands.items():
                cmd_file = commands_dir / f"{name}.md"
                cmd_file.write_text(content)
                logger.info(f"Created command /{name}")

        # Write settings
        if settings:
            settings_file = workspace / ".claude" / "settings.json"
            settings_file.write_text(json.dumps(settings, indent=2))
            logger.info("Created .claude/settings.json")

    async def write_input_files(
        self,
        workspace: Path,
        inputs: Dict[str, Any],
    ) -> None:
        """Write input data to workspace files for Claude to reference"""
        inputs_dir = workspace / "inputs"
        inputs_dir.mkdir(exist_ok=True)

        for key, value in inputs.items():
            if key == "backtrace":
                # Write backtrace to a dedicated file
                (inputs_dir / "backtrace.txt").write_text(str(value))
            elif key == "logs":
                (inputs_dir / "logs.txt").write_text(str(value))
            elif isinstance(value, (dict, list)):
                (inputs_dir / f"{key}.json").write_text(json.dumps(value, indent=2))
            else:
                (inputs_dir / f"{key}.txt").write_text(str(value))

        logger.info(f"Wrote {len(inputs)} input files to {inputs_dir}")

    async def run_hook(
        self,
        workspace: Path,
        hook_script: str,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 60,
    ) -> tuple[bool, str]:
        """Run a hook script in the workspace"""
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        # Add workspace to PATH
        env["WORKSPACE"] = str(workspace)
        env["REPO_PATH"] = str(workspace / "repo")

        try:
            process = await asyncio.create_subprocess_shell(
                hook_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            output = stdout.decode() + stderr.decode()

            if process.returncode != 0:
                logger.warning(f"Hook failed: {output}")
                return False, output

            return True, output

        except asyncio.TimeoutError:
            return False, "Hook timed out"
        except Exception as e:
            return False, str(e)

    async def cleanup_workspace(self, task_id: str) -> bool:
        """Remove a workspace"""
        workspace = self._get_workspace_path(task_id)

        if not workspace.exists():
            return False

        try:
            shutil.rmtree(workspace)
            logger.info(f"Cleaned up workspace {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup workspace {task_id}: {e}")
            return False

    async def cleanup_old_workspaces(self) -> int:
        """Cleanup workspaces older than cleanup_after_hours"""
        cutoff = datetime.utcnow() - timedelta(hours=self._cleanup_after_hours)
        cleaned = 0

        for workspace in self._base_path.iterdir():
            if not workspace.is_dir():
                continue

            metadata_file = workspace / ".workspace_metadata.json"
            if not metadata_file.exists():
                continue

            try:
                metadata = json.loads(metadata_file.read_text())
                created_at = datetime.fromisoformat(metadata["created_at"])

                if created_at < cutoff:
                    shutil.rmtree(workspace)
                    cleaned += 1
                    logger.info(f"Cleaned old workspace {workspace.name}")
            except Exception as e:
                logger.warning(f"Error checking workspace {workspace}: {e}")

        return cleaned

    def get_workspace_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get workspace metadata"""
        workspace = self._get_workspace_path(task_id)
        metadata_file = workspace / ".workspace_metadata.json"

        if not metadata_file.exists():
            return None

        try:
            return json.loads(metadata_file.read_text())
        except Exception:
            return None
