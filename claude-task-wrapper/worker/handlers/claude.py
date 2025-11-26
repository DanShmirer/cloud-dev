"""
Claude Code CLI Handler Implementation
Follows Single Responsibility - only handles Claude CLI execution
Follows Open/Closed - can be extended via inheritance
Follows DRY - common logic extracted to base class
"""
import asyncio
import json
import time
import logging
from abc import abstractmethod
from typing import Optional, Dict, Any, List

from shared.models import Task, TaskResult, TaskType, TaskStatus
from .base import ITaskHandler, ValidationResult


logger = logging.getLogger(__name__)


class BaseClaudeHandler(ITaskHandler):
    """
    Abstract base class for Claude Code CLI handlers
    Contains common validation, execution, and parsing logic
    Follows Template Method pattern - subclasses override specific steps
    """

    def __init__(
        self,
        claude_binary: str = "claude",
        default_timeout: int = 300,
        workspace_root: str = "/workspace",
    ):
        self._claude_binary = claude_binary
        self._default_timeout = default_timeout
        self._workspace_root = workspace_root

    @property
    @abstractmethod
    def name(self) -> str:
        """Handler name - must be implemented by subclass"""
        pass

    @abstractmethod
    def supports(self, task: Task) -> bool:
        """Check if handler supports task type - must be implemented by subclass"""
        pass

    def validate(self, task: Task) -> ValidationResult:
        """
        Validate task parameters
        Subclasses can override and call super() for additional validation
        """
        errors = []

        if not task.prompt or not task.prompt.strip():
            errors.append("Prompt cannot be empty")

        if task.config.timeout_seconds <= 0:
            errors.append("Timeout must be positive")

        if task.config.timeout_seconds > 3600:
            errors.append("Timeout cannot exceed 1 hour")

        valid_models = ["sonnet", "opus", "haiku"]
        if task.config.model not in valid_models:
            errors.append(f"Invalid model. Must be one of: {valid_models}")

        if errors:
            return ValidationResult.invalid(*errors)
        return ValidationResult.valid()

    def _build_base_command(self, task: Task) -> List[str]:
        """
        Build base Claude CLI command arguments
        Common to all handlers
        """
        cmd = [
            self._claude_binary,
            "-p",  # Print/headless mode
            task.prompt,
            "--model", task.config.model,
            "--max-turns", str(task.config.max_turns),
        ]
        return cmd

    def _add_common_args(self, cmd: List[str], task: Task) -> None:
        """Add common arguments to command"""
        if task.config.allowed_tools:
            cmd.extend(["--allowed-tools", ",".join(task.config.allowed_tools)])

        if task.config.verbose:
            cmd.append("--verbose")

    @abstractmethod
    def _build_command(self, task: Task) -> List[str]:
        """
        Build complete CLI command
        Subclasses must implement to add their specific arguments
        """
        pass

    async def _run_process(
        self,
        cmd: List[str],
        working_dir: str,
        timeout: int,
    ) -> tuple[int, bytes, bytes]:
        """
        Execute subprocess and wait for completion
        Returns (return_code, stdout, stderr)
        Raises asyncio.TimeoutError if timed out
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        return process.returncode, stdout, stderr

    async def execute(self, task: Task) -> TaskResult:
        """
        Execute Claude CLI and capture output
        Template method - uses hooks that subclasses can customize
        """
        start_time = time.time()

        # Validate first
        validation = self.validate(task)
        if not validation.is_valid:
            return TaskResult.failure(
                task_id=task.task_id,
                error=f"Validation failed: {'; '.join(validation.errors)}",
            )

        cmd = self._build_command(task)
        self._log_execution_start(task, cmd)

        try:
            timeout = task.config.timeout_seconds or self._default_timeout
            working_dir = task.config.working_dir or self._workspace_root

            try:
                returncode, stdout, stderr = await self._run_process(
                    cmd, working_dir, timeout
                )
            except asyncio.TimeoutError:
                return TaskResult.failure(
                    task_id=task.task_id,
                    error=f"Task timed out after {timeout} seconds",
                    duration_seconds=time.time() - start_time,
                )

            duration = time.time() - start_time

            if returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"Task {task.task_id} failed: {error_msg}")
                return TaskResult.failure(
                    task_id=task.task_id,
                    error=error_msg,
                    duration_seconds=duration,
                )

            # Parse and create result
            output = stdout.decode("utf-8", errors="replace")
            return self._create_success_result(task, output, duration)

        except FileNotFoundError:
            return TaskResult.failure(
                task_id=task.task_id,
                error=f"Claude CLI not found at: {self._claude_binary}",
            )
        except Exception as e:
            logger.exception(f"Task {task.task_id} failed with exception")
            return TaskResult.failure(
                task_id=task.task_id,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    def _log_execution_start(self, task: Task, cmd: List[str]) -> None:
        """Log execution start - can be overridden for custom logging"""
        logger.info(f"Executing task {task.task_id}: {' '.join(cmd[:5])}...")

    @abstractmethod
    def _create_success_result(
        self,
        task: Task,
        output: str,
        duration: float,
    ) -> TaskResult:
        """
        Create success result from output
        Subclasses implement their own parsing logic
        """
        pass

    def _parse_json_output(self, output: str) -> Dict[str, Any]:
        """Parse JSON output, returning dict with result or parse_error"""
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"result": output, "parse_error": "Invalid JSON"}

    def _parse_stream_json_output(self, output: str) -> Dict[str, Any]:
        """Parse stream-json output, finding last result object"""
        lines = output.strip().split("\n")
        for line in reversed(lines):
            try:
                data = json.loads(line)
                if data.get("type") == "result":
                    return data
            except json.JSONDecodeError:
                continue
        return {"result": output}


class ClaudeCodeHandler(BaseClaudeHandler):
    """
    Handler for single-shot Claude Code CLI execution
    Uses headless mode with -p flag
    """

    @property
    def name(self) -> str:
        return "claude-code-single"

    def supports(self, task: Task) -> bool:
        """Supports single-shot tasks without session continuation"""
        return task.task_type == TaskType.SINGLE

    def _build_command(self, task: Task) -> List[str]:
        """Build Claude CLI command with all arguments"""
        cmd = self._build_base_command(task)
        cmd.extend(["--output-format", task.config.output_format])
        self._add_common_args(cmd, task)
        return cmd

    def _create_success_result(
        self,
        task: Task,
        output: str,
        duration: float,
    ) -> TaskResult:
        """Parse output based on format and create result"""
        format = task.config.output_format

        if format == "json":
            parsed = self._parse_json_output(output)
        elif format == "stream-json":
            parsed = self._parse_stream_json_output(output)
        else:
            parsed = {"result": output}

        return TaskResult.success(
            task_id=task.task_id,
            output=parsed.get("result", output),
            session_id=parsed.get("session_id"),
            cost_usd=parsed.get("cost_usd"),
            duration_seconds=duration,
            raw_response=parsed if format == "json" else None,
        )


class ClaudeSessionHandler(BaseClaudeHandler):
    """
    Handler for multi-turn Claude Code conversations
    Uses --resume flag for session continuation
    Follows Liskov Substitution - can be used anywhere ITaskHandler is expected
    """

    @property
    def name(self) -> str:
        return "claude-code-session"

    def supports(self, task: Task) -> bool:
        """Supports session/multi-turn tasks"""
        return task.task_type == TaskType.SESSION

    def _build_command(self, task: Task) -> List[str]:
        """Build Claude CLI command with session resume"""
        cmd = self._build_base_command(task)
        cmd.extend(["--output-format", "json"])  # Always JSON for session parsing

        # Add session resume if continuing conversation
        if task.session_id:
            cmd.extend(["--resume", task.session_id])

        self._add_common_args(cmd, task)
        return cmd

    def _log_execution_start(self, task: Task, cmd: List[str]) -> None:
        """Log with session info"""
        session_info = f" (resuming {task.session_id})" if task.session_id else " (new session)"
        logger.info(f"Executing session task {task.task_id}{session_info}")

    def _create_success_result(
        self,
        task: Task,
        output: str,
        duration: float,
    ) -> TaskResult:
        """Parse JSON output to extract session_id for continuation"""
        try:
            parsed = json.loads(output)
            session_id = parsed.get("session_id")
            result_text = parsed.get("result", output)
            cost = parsed.get("cost_usd")
        except json.JSONDecodeError:
            parsed = {"result": output}
            session_id = None
            result_text = output
            cost = None

        return TaskResult.success(
            task_id=task.task_id,
            output=result_text,
            session_id=session_id,  # Return for continuation
            cost_usd=cost,
            duration_seconds=duration,
            raw_response=parsed,
        )
