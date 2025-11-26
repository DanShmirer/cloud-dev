"""
Configuration Management - Centralized configuration with validation
Following Single Responsibility - only handles configuration concerns

Security principles:
- Secrets are separated from regular config
- Environment-specific overrides supported
- Validation ensures no default/example credentials in production
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class Environment(Enum):
    """Deployment environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class WorkerMode(Enum):
    """Worker mode options"""
    ALL = "all"
    REGULAR = "regular"
    ENVIRONMENT = "environment"


@dataclass(frozen=True)
class SecretConfig:
    """
    Sensitive credentials configuration.
    These should NEVER be logged or exposed.
    """
    anthropic_api_key: str = ""
    redis_password: Optional[str] = None
    webhook_secret: Optional[str] = None

    @classmethod
    def from_env(cls) -> "SecretConfig":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            redis_password=os.getenv("REDIS_PASSWORD"),
            webhook_secret=os.getenv("WEBHOOK_SECRET"),
        )

    def validate(self, environment: Environment) -> List[str]:
        """Validate secrets, stricter for production"""
        errors = []

        # Check for missing or example API key
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required")
        elif self.anthropic_api_key in ("your-api-key-here", "sk-ant-xxx"):
            errors.append("ANTHROPIC_API_KEY contains example/placeholder value")

        # Production-specific validations
        if environment == Environment.PRODUCTION:
            if self.anthropic_api_key and len(self.anthropic_api_key) < 20:
                errors.append("ANTHROPIC_API_KEY appears invalid for production")

        return errors

    def __repr__(self) -> str:
        """Prevent accidental secret exposure in logs"""
        return "SecretConfig(***REDACTED***)"


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
    cors_origins: List[str] = field(default_factory=list)
    rate_limit_requests: int = 100
    rate_limit_period_seconds: int = 60

    @classmethod
    def from_env(cls, environment: Environment = Environment.DEVELOPMENT) -> "ApiConfig":
        # Parse CORS origins from comma-separated string
        cors_str = os.getenv("CORS_ORIGINS", "")
        if cors_str:
            cors_origins = [origin.strip() for origin in cors_str.split(",")]
        elif environment == Environment.DEVELOPMENT:
            cors_origins = ["*"]  # Allow all in dev only
        else:
            cors_origins = []  # Explicit origins required in staging/prod

        return cls(
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            cors_origins=cors_origins,
            rate_limit_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "100")),
            rate_limit_period_seconds=int(os.getenv("RATE_LIMIT_PERIOD", "60")),
        )

    def validate(self, environment: Environment) -> List[str]:
        """Validate API config"""
        errors = []

        if environment == Environment.PRODUCTION:
            if "*" in self.cors_origins:
                errors.append("CORS_ORIGINS cannot be '*' in production")
            if not self.cors_origins:
                errors.append("CORS_ORIGINS must be explicitly set in production")

        return errors


@dataclass(frozen=True)
class AppConfig:
    """
    Root application configuration
    Aggregates all sub-configurations including secrets
    """
    environment: Environment = Environment.DEVELOPMENT
    secrets: SecretConfig = field(default_factory=SecretConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables"""
        # Determine environment first
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        try:
            environment = Environment(env_str)
        except ValueError:
            logger.warning(f"Unknown environment '{env_str}', defaulting to development")
            environment = Environment.DEVELOPMENT

        return cls(
            environment=environment,
            secrets=SecretConfig.from_env(),
            redis=RedisConfig.from_env(),
            claude=ClaudeConfig.from_env(),
            worker=WorkerConfig.from_env(),
            api=ApiConfig.from_env(environment),
        )

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []

        # Validate secrets
        errors.extend(self.secrets.validate(self.environment))

        # Validate API config
        errors.extend(self.api.validate(self.environment))

        # Validate worker config
        if self.worker.max_concurrent_tasks < 1:
            errors.append("MAX_CONCURRENT_TASKS must be at least 1")

        if self.worker.poll_timeout_seconds < 1:
            errors.append("POLL_TIMEOUT must be at least 1 second")

        if self.claude.default_timeout_seconds < 1:
            errors.append("CLAUDE_TIMEOUT must be at least 1 second")

        if self.redis.result_ttl_days < 1:
            errors.append("RESULT_TTL_DAYS must be at least 1")

        return errors

    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == Environment.DEVELOPMENT


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


def validate_config_or_exit() -> AppConfig:
    """
    Load and validate configuration, exit if invalid.
    Use this at application startup.
    """
    config = get_config()
    errors = config.validate()

    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        raise SystemExit(1)

    logger.info(f"Configuration loaded for environment: {config.environment.value}")
    return config
