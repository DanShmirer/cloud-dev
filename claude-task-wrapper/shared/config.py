"""
Configuration Management - Centralized configuration with validation
Following Single Responsibility - only handles configuration concerns
"""
import os
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class WorkerMode(Enum):
    """Worker mode options"""
    ALL = "all"
    REGULAR = "regular"
    ENVIRONMENT = "environment"


@dataclass(frozen=True)
class RedisConfig:
    """Redis connection configuration"""
    url: str = "redis://localhost:6379"
    result_ttl_days: int = 7
    session_ttl_hours: int = 24

    @classmethod
    def from_env(cls) -> "RedisConfig":
        return cls(
            url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            result_ttl_days=int(os.getenv("RESULT_TTL_DAYS", "7")),
            session_ttl_hours=int(os.getenv("SESSION_TTL_HOURS", "24")),
        )


@dataclass(frozen=True)
class ClaudeConfig:
    """Claude Code CLI configuration"""
    binary_path: str = "claude"
    default_model: str = "sonnet"
    default_max_turns: int = 50
    default_timeout_seconds: int = 300
    default_allowed_tools: List[str] = field(default_factory=lambda: [
        "Read", "Glob", "Grep", "Bash", "Edit", "Write"
    ])

    @classmethod
    def from_env(cls) -> "ClaudeConfig":
        return cls(
            binary_path=os.getenv("CLAUDE_BINARY", "claude"),
            default_model=os.getenv("CLAUDE_DEFAULT_MODEL", "sonnet"),
            default_max_turns=int(os.getenv("CLAUDE_MAX_TURNS", "50")),
            default_timeout_seconds=int(os.getenv("CLAUDE_TIMEOUT", "300")),
        )


@dataclass(frozen=True)
class WorkerConfig:
    """Worker service configuration"""
    mode: WorkerMode = WorkerMode.ALL
    max_concurrent_tasks: int = 1
    poll_timeout_seconds: int = 5
    workspace_root: str = "/workspace"
    workspaces_root: str = "/workspaces"
    cleanup_after_hours: int = 24

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        mode_str = os.getenv("WORKER_MODE", "all")
        try:
            mode = WorkerMode(mode_str)
        except ValueError:
            mode = WorkerMode.ALL

        return cls(
            mode=mode,
            max_concurrent_tasks=int(os.getenv("MAX_CONCURRENT_TASKS", "1")),
            poll_timeout_seconds=int(os.getenv("POLL_TIMEOUT", "5")),
            workspace_root=os.getenv("WORKSPACE_ROOT", "/workspace"),
            workspaces_root=os.getenv("WORKSPACES_ROOT", "/workspaces"),
            cleanup_after_hours=int(os.getenv("CLEANUP_AFTER_HOURS", "24")),
        )


@dataclass(frozen=True)
class ApiConfig:
    """API Gateway configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: List[str] = field(default_factory=lambda: ["*"])

    @classmethod
    def from_env(cls) -> "ApiConfig":
        return cls(
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


@dataclass(frozen=True)
class AppConfig:
    """
    Root application configuration
    Aggregates all sub-configurations
    """
    redis: RedisConfig = field(default_factory=RedisConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables"""
        return cls(
            redis=RedisConfig.from_env(),
            claude=ClaudeConfig.from_env(),
            worker=WorkerConfig.from_env(),
            api=ApiConfig.from_env(),
        )

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []

        if self.worker.max_concurrent_tasks < 1:
            errors.append("MAX_CONCURRENT_TASKS must be at least 1")

        if self.worker.poll_timeout_seconds < 1:
            errors.append("POLL_TIMEOUT must be at least 1 second")

        if self.claude.default_timeout_seconds < 1:
            errors.append("CLAUDE_TIMEOUT must be at least 1 second")

        if self.redis.result_ttl_days < 1:
            errors.append("RESULT_TTL_DAYS must be at least 1")

        return errors


# Singleton for global access (with DI override capability)
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get or create the application configuration"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def set_config(config: AppConfig) -> None:
    """Override configuration (for testing)"""
    global _config
    _config = config
