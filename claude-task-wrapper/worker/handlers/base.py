"""
Task Handler Interface - Following Interface Segregation & Liskov Substitution Principles
Any handler implementing ITaskHandler can be substituted without breaking the system
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from shared.models import Task, TaskResult


@dataclass
class ValidationResult:
    """Result of task validation"""
    is_valid: bool
    errors: List[str]

    @classmethod
    def valid(cls) -> "ValidationResult":
        return cls(is_valid=True, errors=[])

    @classmethod
    def invalid(cls, *errors: str) -> "ValidationResult":
        return cls(is_valid=False, errors=list(errors))


class ITaskHandler(ABC):
    """
    Abstract interface for task handlers
    Follows Interface Segregation - focused only on task execution concerns
    Follows Liskov Substitution - any implementation can be used interchangeably
    """

    @abstractmethod
    async def execute(self, task: Task) -> TaskResult:
        """
        Execute the task and return result
        Must handle all exceptions internally and return appropriate TaskResult
        """
        pass

    @abstractmethod
    def validate(self, task: Task) -> ValidationResult:
        """
        Validate task before execution
        Returns validation result with any errors
        """
        pass

    @abstractmethod
    def supports(self, task: Task) -> bool:
        """
        Check if this handler supports the given task type
        Used by handler registry for dispatch
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Handler identifier for logging and metrics"""
        pass


class ITaskHandlerRegistry(ABC):
    """
    Registry interface for managing multiple task handlers
    Follows Open/Closed - new handlers can be added without modifying existing code
    """

    @abstractmethod
    def register(self, handler: ITaskHandler) -> None:
        """Register a handler"""
        pass

    @abstractmethod
    def unregister(self, handler_name: str) -> None:
        """Unregister a handler by name"""
        pass

    @abstractmethod
    def get_handler(self, task: Task) -> Optional[ITaskHandler]:
        """Get appropriate handler for task"""
        pass

    @abstractmethod
    def list_handlers(self) -> List[str]:
        """List all registered handler names"""
        pass


class TaskHandlerRegistry(ITaskHandlerRegistry):
    """
    Concrete implementation of handler registry
    Maintains ordered list of handlers, returns first matching handler
    """

    def __init__(self):
        self._handlers: Dict[str, ITaskHandler] = {}
        self._order: List[str] = []

    def register(self, handler: ITaskHandler) -> None:
        """Register handler (last registered takes priority)"""
        name = handler.name
        if name not in self._handlers:
            self._order.insert(0, name)  # Insert at front for priority
        self._handlers[name] = handler

    def unregister(self, handler_name: str) -> None:
        """Remove handler from registry"""
        if handler_name in self._handlers:
            del self._handlers[handler_name]
            self._order.remove(handler_name)

    def get_handler(self, task: Task) -> Optional[ITaskHandler]:
        """Find first handler that supports this task"""
        for name in self._order:
            handler = self._handlers[name]
            if handler.supports(task):
                return handler
        return None

    def list_handlers(self) -> List[str]:
        """List registered handler names in priority order"""
        return self._order.copy()
