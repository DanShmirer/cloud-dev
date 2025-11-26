"""
Claude Code CLI Handler Implementation
Follows Single Responsibility - only handles Claude CLI execution
Follows Open/Closed - can be extended via inheritance
"""
import asyncio
import json
import time
import logging
from typing import Optional, Dict, Any

from shared.models import Task, TaskResult, TaskType, TaskStatus
from .base import ITaskHandler, ValidationResult


logger = logging.getLogger(__name__)


class ClaudeCodeHandler(ITaskHandler):
    """
    Handler for single-shot Claude Code CLI execution
    Uses headless mode with -p flag
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
    def name(self) -> str:
        return "claude-code-single"

    def supports(self, task: Task) -> bool:
        """Supports single-shot tasks without session continuation"""
        return task.task_type == TaskType.SINGLE

    def validate(self, task: Task) -> ValidationResult:
        """Validate task parameters"""
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

    def _build_command(self, task: Task) -> list[str]:
        """Build Claude CLI command with all arguments"""
        cmd = [
            self._claude_binary,
            "-p",  # Print/headless mode
            task.prompt,
            "--output-format", task.config.output_format,
            "--model", task.config.model,
            "--max-turns", str(task.config.max_turns),
        ]

        if task.config.allowed_tools:
            cmd.extend(["--allowed-tools", ",".join(task.config.allowed_tools)])

        if task.config.verbose:
            cmd.append("--verbose")

        return cmd

    async def execute(self, task: Task) -> TaskResult:
        """
        Execute Claude CLI and capture output
        Returns TaskResult with parsed response or error
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
        logger.info(f"Executing task {task.task_id}: {' '.join(cmd[:5])}...")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=task.config.working_dir or self._workspace_root,
            )

            timeout = task.config.timeout_seconds or self._default_timeout

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return TaskResult.failure(
                    task_id=task.task_id,
                    error=f"Task timed out after {timeout} seconds",
                    duration_seconds=time.time() - start_time,
                )

            duration = time.time() - start_time

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"Task {task.task_id} failed: {error_msg}")
                return TaskResult.failure(
                    task_id=task.task_id,
                    error=error_msg,
                    duration_seconds=duration,
                )

            # Parse output
            output = stdout.decode("utf-8", errors="replace")
            parsed = self._parse_output(output, task.config.output_format)

            return TaskResult.success(
                task_id=task.task_id,
                output=parsed.get("result", output),
                session_id=parsed.get("session_id"),
                cost_usd=parsed.get("cost_usd"),
                duration_seconds=duration,
                raw_response=parsed if task.config.output_format == "json" else None,
            )

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

    def _parse_output(self, output: str, format: str) -> Dict[str, Any]:
        """Parse Claude CLI output based on format"""
        if format == "json":
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"result": output, "parse_error": "Invalid JSON"}
        elif format == "stream-json":
            # Parse last complete JSON object from stream
            lines = output.strip().split("\n")
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    if data.get("type") == "result":
                        return data
                except json.JSONDecodeError:
                    continue
            return {"result": output}
        else:
            return {"result": output}


class ClaudeSessionHandler(ITaskHandler):
    """
    Handler for multi-turn Claude Code conversations
    Uses --resume flag for session continuation
    Follows Liskov Substitution - can be used anywhere ITaskHandler is expected
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
        self._single_handler = ClaudeCodeHandler(
            claude_binary=claude_binary,
            default_timeout=default_timeout,
            workspace_root=workspace_root,
        )

    @property
    def name(self) -> str:
        return "claude-code-session"

    def supports(self, task: Task) -> bool:
        """Supports session/multi-turn tasks"""
        return task.task_type == TaskType.SESSION

    def validate(self, task: Task) -> ValidationResult:
        """Validate session task parameters"""
        # Reuse single handler validation
        base_validation = self._single_handler.validate(task)
        if not base_validation.is_valid:
            return base_validation

        # Additional session-specific validation
        # session_id is optional for first message
        return ValidationResult.valid()

    def _build_command(self, task: Task) -> list[str]:
        """Build Claude CLI command with session resume"""
        cmd = [
            self._claude_binary,
            "-p",  # Print/headless mode
            task.prompt,
            "--output-format", "json",  # Always JSON for session parsing
            "--model", task.config.model,
            "--max-turns", str(task.config.max_turns),
        ]

        # Add session resume if continuing conversation
        if task.session_id:
            cmd.extend(["--resume", task.session_id])

        if task.config.allowed_tools:
            cmd.extend(["--allowed-tools", ",".join(task.config.allowed_tools)])

        if task.config.verbose:
            cmd.append("--verbose")

        return cmd

    async def execute(self, task: Task) -> TaskResult:
        """
        Execute Claude CLI with session support
        Extracts session_id from response for continuation
        """
        start_time = time.time()

        validation = self.validate(task)
        if not validation.is_valid:
            return TaskResult.failure(
                task_id=task.task_id,
                error=f"Validation failed: {'; '.join(validation.errors)}",
            )

        cmd = self._build_command(task)
        session_info = f" (resuming {task.session_id})" if task.session_id else " (new session)"
        logger.info(f"Executing session task {task.task_id}{session_info}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=task.config.working_dir or self._workspace_root,
            )

            timeout = task.config.timeout_seconds or self._default_timeout

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return TaskResult.failure(
                    task_id=task.task_id,
                    error=f"Session task timed out after {timeout} seconds",
                    duration_seconds=time.time() - start_time,
                )

            duration = time.time() - start_time

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.error(f"Session task {task.task_id} failed: {error_msg}")
                return TaskResult.failure(
                    task_id=task.task_id,
                    error=error_msg,
                    duration_seconds=duration,
                )

            # Parse JSON output to extract session_id
            output = stdout.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(output)
                session_id = parsed.get("session_id")
                result_text = parsed.get("result", output)
                cost = parsed.get("cost_usd")
            except json.JSONDecodeError:
                session_id = None
                result_text = output
                cost = None
                parsed = {"result": output}

            return TaskResult.success(
                task_id=task.task_id,
                output=result_text,
                session_id=session_id,  # Return for continuation
                cost_usd=cost,
                duration_seconds=duration,
                raw_response=parsed,
            )

        except FileNotFoundError:
            return TaskResult.failure(
                task_id=task.task_id,
                error=f"Claude CLI not found at: {self._claude_binary}",
            )
        except Exception as e:
            logger.exception(f"Session task {task.task_id} failed with exception")
            return TaskResult.failure(
                task_id=task.task_id,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )
