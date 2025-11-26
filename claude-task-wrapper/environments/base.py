"""
Base Environment Interface - Following Interface Segregation & Open/Closed Principles
New environments can be added by implementing IEnvironment without modifying existing code
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

from shared.models import (
    EnvironmentConfig,
    EnvironmentTask,
    EnvironmentTaskResult,
    EnvironmentType,
    WorkflowStep,
    WorkflowStepResult,
    WorkflowStepStatus,
)
from shared.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class IEnvironment(ABC):
    """
    Abstract interface for task execution environments
    Each environment defines its own workflow, prompts, hooks, and CLAUDE.md
    """

    @property
    @abstractmethod
    def env_type(self) -> EnvironmentType:
        """Environment type identifier"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable environment name"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Environment description"""
        pass

    @property
    @abstractmethod
    def required_inputs(self) -> List[str]:
        """List of required input fields"""
        pass

    @abstractmethod
    def get_config(self) -> EnvironmentConfig:
        """Get full environment configuration"""
        pass

    @abstractmethod
    def get_claude_md(self, inputs: Dict[str, Any]) -> str:
        """
        Generate CLAUDE.md content for this environment
        Can use inputs to customize the context
        """
        pass

    @abstractmethod
    def get_commands(self) -> Dict[str, str]:
        """
        Get custom slash commands for this environment
        Returns dict of {command_name: markdown_content}
        """
        pass

    @abstractmethod
    def get_workflow_steps(self, inputs: Dict[str, Any]) -> List[WorkflowStep]:
        """
        Get workflow steps for this task
        Steps can be customized based on inputs
        """
        pass

    @abstractmethod
    def get_final_prompt(self, inputs: Dict[str, Any]) -> str:
        """
        Get the main analysis prompt for Claude
        This is the prompt used in the final Claude execution step
        """
        pass

    def validate_inputs(self, inputs: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate that all required inputs are provided"""
        errors = []
        for field in self.required_inputs:
            if field not in inputs or not inputs[field]:
                errors.append(f"Missing required input: {field}")
        return len(errors) == 0, errors

    def get_subagent_prompts(self) -> Dict[str, str]:
        """
        Get sub-agent prompt templates
        Override in subclasses to define sub-agents
        """
        return {}


class EnvironmentRegistry:
    """
    Registry for managing available environments
    Follows Open/Closed - new environments can be registered without modification
    """

    def __init__(self):
        self._environments: Dict[EnvironmentType, IEnvironment] = {}

    def register(self, environment: IEnvironment) -> None:
        """Register an environment"""
        self._environments[environment.env_type] = environment
        logger.info(f"Registered environment: {environment.name}")

    def unregister(self, env_type: EnvironmentType) -> None:
        """Unregister an environment"""
        if env_type in self._environments:
            del self._environments[env_type]

    def get(self, env_type: EnvironmentType) -> Optional[IEnvironment]:
        """Get environment by type"""
        return self._environments.get(env_type)

    def list_environments(self) -> List[Dict[str, Any]]:
        """List all registered environments"""
        return [
            {
                "type": env.env_type.value,
                "name": env.name,
                "description": env.description,
                "required_inputs": env.required_inputs,
            }
            for env in self._environments.values()
        ]

    def get_all_types(self) -> List[EnvironmentType]:
        """Get all registered environment types"""
        return list(self._environments.keys())


class EnvironmentExecutor:
    """
    Executes environment workflows
    Coordinates workspace setup, hooks, and Claude execution
    """

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        claude_binary: str = "claude",
    ):
        self._workspace_manager = workspace_manager
        self._claude_binary = claude_binary

    async def execute(
        self,
        environment: IEnvironment,
        task: EnvironmentTask,
    ) -> EnvironmentTaskResult:
        """Execute an environment task through its workflow"""
        import time
        import asyncio

        start_time = time.time()
        step_results: List[WorkflowStepResult] = []
        workspace: Optional[Path] = None
        final_analysis: Optional[str] = None
        error: Optional[str] = None

        try:
            # Validate inputs
            valid, errors = environment.validate_inputs(task.inputs)
            if not valid:
                return EnvironmentTaskResult(
                    task_id=task.task_id,
                    env_type=task.env_type,
                    status="failed",
                    workspace_path="",
                    error=f"Input validation failed: {'; '.join(errors)}",
                    total_duration_seconds=time.time() - start_time,
                )

            # Create workspace
            workspace = await self._workspace_manager.create_workspace(
                task.task_id,
                environment.env_type.value,
            )

            # Setup Claude configuration
            claude_md = environment.get_claude_md(task.inputs)
            commands = environment.get_commands()

            await self._workspace_manager.setup_claude_config(
                workspace=workspace,
                claude_md_content=claude_md,
                commands=commands,
            )

            # Write input files
            await self._workspace_manager.write_input_files(
                workspace=workspace,
                inputs=task.inputs,
            )

            # Get and execute workflow steps
            steps = environment.get_workflow_steps(task.inputs)
            config = environment.get_config()

            for step in steps:
                step_start = time.time()
                step_result = await self._execute_step(
                    step=step,
                    workspace=workspace,
                    inputs=task.inputs,
                    config=config,
                )
                step_result.duration_seconds = time.time() - step_start
                step_results.append(step_result)

                # Check if we should continue
                if step_result.status == WorkflowStepStatus.FAILED:
                    if not step.continue_on_error:
                        error = f"Step '{step.name}' failed: {step_result.error}"
                        break

            # Execute final Claude analysis if all steps passed
            if not error:
                final_prompt = environment.get_final_prompt(task.inputs)
                if task.additional_prompt:
                    final_prompt += f"\n\nAdditional context:\n{task.additional_prompt}"

                analysis_result = await self._run_claude(
                    workspace=workspace,
                    prompt=final_prompt,
                    model=config.default_model,
                    allowed_tools=config.default_allowed_tools,
                )
                final_analysis = analysis_result.get("output")
                if analysis_result.get("error"):
                    error = analysis_result["error"]

            status = "completed" if not error else "failed"
            if error and any(r.status == WorkflowStepStatus.COMPLETED for r in step_results):
                status = "partial"

            return EnvironmentTaskResult(
                task_id=task.task_id,
                env_type=task.env_type,
                status=status,
                workspace_path=str(workspace) if workspace else "",
                step_results=step_results,
                final_analysis=final_analysis,
                error=error,
                total_duration_seconds=time.time() - start_time,
            )

        except Exception as e:
            logger.exception(f"Environment execution failed: {e}")
            return EnvironmentTaskResult(
                task_id=task.task_id,
                env_type=task.env_type,
                status="failed",
                workspace_path=str(workspace) if workspace else "",
                step_results=step_results,
                error=str(e),
                total_duration_seconds=time.time() - start_time,
            )

    async def _execute_step(
        self,
        step: WorkflowStep,
        workspace: Path,
        inputs: Dict[str, Any],
        config: EnvironmentConfig,
    ) -> WorkflowStepResult:
        """Execute a single workflow step"""
        import asyncio

        logger.info(f"Executing step: {step.name}")

        try:
            if step.step_type == "shell":
                # Execute shell command
                success, output = await self._workspace_manager.run_hook(
                    workspace=workspace,
                    hook_script=step.command or "",
                    timeout=step.timeout_seconds,
                )
                return WorkflowStepResult(
                    step_name=step.name,
                    status=WorkflowStepStatus.COMPLETED if success else WorkflowStepStatus.FAILED,
                    output=output if success else None,
                    error=output if not success else None,
                )

            elif step.step_type == "claude":
                # Execute Claude prompt
                prompt = step.prompt_template or ""
                # Substitute input variables
                for key, value in inputs.items():
                    prompt = prompt.replace(f"{{{key}}}", str(value))

                result = await self._run_claude(
                    workspace=workspace,
                    prompt=prompt,
                    model=config.default_model,
                    allowed_tools=config.default_allowed_tools,
                    timeout=step.timeout_seconds,
                )

                if result.get("error"):
                    return WorkflowStepResult(
                        step_name=step.name,
                        status=WorkflowStepStatus.FAILED,
                        error=result["error"],
                    )

                return WorkflowStepResult(
                    step_name=step.name,
                    status=WorkflowStepStatus.COMPLETED,
                    output=result.get("output"),
                )

            elif step.step_type == "subagent":
                # Execute sub-agent (future implementation)
                return WorkflowStepResult(
                    step_name=step.name,
                    status=WorkflowStepStatus.SKIPPED,
                    output="Sub-agents not yet implemented",
                )

            else:
                return WorkflowStepResult(
                    step_name=step.name,
                    status=WorkflowStepStatus.FAILED,
                    error=f"Unknown step type: {step.step_type}",
                )

        except asyncio.TimeoutError:
            return WorkflowStepResult(
                step_name=step.name,
                status=WorkflowStepStatus.FAILED,
                error=f"Step timed out after {step.timeout_seconds}s",
            )
        except Exception as e:
            return WorkflowStepResult(
                step_name=step.name,
                status=WorkflowStepStatus.FAILED,
                error=str(e),
            )

    async def _run_claude(
        self,
        workspace: Path,
        prompt: str,
        model: str = "sonnet",
        allowed_tools: List[str] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Run Claude CLI in the workspace"""
        import asyncio
        import json

        cmd = [
            self._claude_binary,
            "-p", prompt,
            "--output-format", "json",
            "--model", model,
        ]

        if allowed_tools:
            cmd.extend(["--allowed-tools", ",".join(allowed_tools)])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            if process.returncode != 0:
                return {"error": stderr.decode()}

            output = stdout.decode()
            try:
                parsed = json.loads(output)
                return {"output": parsed.get("result", output), "raw": parsed}
            except json.JSONDecodeError:
                return {"output": output}

        except asyncio.TimeoutError:
            return {"error": f"Claude execution timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}
