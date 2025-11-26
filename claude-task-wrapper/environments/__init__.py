"""
Task Execution Environments
Each environment provides a specialized context for Claude Code execution
"""
from .base import (
    IEnvironment,
    EnvironmentRegistry,
    EnvironmentExecutor,
)
from .crash_analysis import CrashAnalysisEnvironment

# Create default registry with all environments
def create_default_registry() -> EnvironmentRegistry:
    """Create registry with all built-in environments"""
    registry = EnvironmentRegistry()
    registry.register(CrashAnalysisEnvironment())
    return registry

__all__ = [
    "IEnvironment",
    "EnvironmentRegistry",
    "EnvironmentExecutor",
    "CrashAnalysisEnvironment",
    "create_default_registry",
]
