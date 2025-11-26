"""Workspace management for environment tasks"""
from .base import IWorkspaceManager
from .manager import LocalWorkspaceManager

# Backward-compatible alias
WorkspaceManager = LocalWorkspaceManager

__all__ = [
    "IWorkspaceManager",
    "LocalWorkspaceManager",
    "WorkspaceManager",  # Alias for backward compatibility
]
