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
from .facts_extraction import FactsExtractionEnvironment


# Create default registry with all environments
def create_default_registry() -> EnvironmentRegistry:
    """Create registry with all built-in environments"""
    registry = EnvironmentRegistry()
    registry.register(CrashAnalysisEnvironment())
    registry.register(FactsExtractionEnvironment())
    return registry


__all__ = [
    "IEnvironment",
    "EnvironmentRegistry",
    "EnvironmentExecutor",
    "CrashAnalysisEnvironment",
    "FactsExtractionEnvironment",
    "create_default_registry",
]
