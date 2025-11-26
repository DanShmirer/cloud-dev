# Claude Task Wrapper

A Dockerized application that wraps Claude Code CLI and allows injecting multiple tasks via a REST API with queue-based processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Docker Compose                          │
├─────────────┬─────────────┬─────────────┬─────────────────────┤
│   API       │   Worker    │   Redis     │   Claude Code       │
│   Gateway   │   Service   │   Queue     │   (in Worker)       │
│   :8000     │             │   :6379     │                     │
└─────────────┴─────────────┴─────────────┴─────────────────────┘
```

### SOLID Principles Applied

- **Single Responsibility**: Each class handles one concern (Task, TaskResult, Handler, Queue)
- **Open/Closed**: New handlers can be added without modifying existing code
- **Liskov Substitution**: All handlers implement `ITaskHandler` and are interchangeable
- **Interface Segregation**: Separate interfaces for Queue, Store, and Session management
- **Dependency Inversion**: Components depend on abstractions (interfaces), not concrete implementations

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose
- Anthropic API Key

### 2. Setup

```bash
# Clone and navigate to project
cd claude-task-wrapper

# Copy environment file
cp .env.example .env

# Add your Anthropic API key
echo "ANTHROPIC_API_KEY=your-key-here" >> .env

# Start services
docker-compose up -d
```

### 3. Submit Tasks

```bash
# Submit a single task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "List the files in the current directory",
    "task_type": "single",
    "config": {
      "model": "sonnet",
      "allowed_tools": ["Bash", "Read", "Glob"],
      "timeout_seconds": 60
    }
  }'

# Response: {"task_id": "uuid", "status": "queued", "message": "..."}
```

### 4. Check Status

```bash
# Get task status/result
curl http://localhost:8000/tasks/{task_id}
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/tasks` | Submit a new task |
| `GET` | `/tasks/{id}` | Get task status/result |
| `DELETE` | `/tasks/{id}` | Cancel a pending task |
| `GET` | `/tasks` | List all tasks |
| `GET` | `/queue/stats` | Get queue statistics |
| `POST` | `/queue/clear` | Clear pending tasks |
| `POST` | `/sessions/{id}/continue` | Continue a session |
| `GET` | `/health` | Health check |

## Task Types

### Single Task
One-shot Claude Code execution:

```json
{
  "prompt": "Fix the bug in auth.py",
  "task_type": "single",
  "config": {
    "model": "sonnet",
    "allowed_tools": ["Read", "Edit", "Bash"],
    "timeout_seconds": 300
  },
  "priority": 5
}
```

### Session Task
Multi-turn conversation with resume capability:

```json
{
  "prompt": "Help me refactor this module",
  "task_type": "session",
  "config": {
    "model": "opus"
  }
}
```

Continue session:
```bash
curl -X POST http://localhost:8000/sessions/{task_id}/continue \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Now add unit tests"}'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | - | Required: Your Anthropic API key |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `CLAUDE_BINARY` | `claude` | Path to Claude CLI |
| `WORKSPACE_ROOT` | `/workspace` | Default working directory |
| `MAX_CONCURRENT_TASKS` | `1` | Concurrent task limit |
| `LOG_LEVEL` | `INFO` | Logging level |

### Task Config Options

| Option | Default | Description |
|--------|---------|-------------|
| `model` | `sonnet` | `sonnet`, `opus`, or `haiku` |
| `allowed_tools` | `["Read", "Glob", "Grep"]` | Whitelisted tools |
| `working_dir` | `/workspace` | Execution directory |
| `timeout_seconds` | `300` | Max execution time |
| `max_turns` | `50` | Max conversation turns |
| `verbose` | `false` | Enable verbose output |

### Priority Levels

| Priority | Value | Use Case |
|----------|-------|----------|
| LOW | 1 | Background tasks |
| NORMAL | 5 | Default |
| HIGH | 10 | Important tasks |
| CRITICAL | 20 | Urgent tasks |

## Scaling

Scale workers for parallel processing:

```bash
docker-compose up -d --scale worker=3
```

## Development

### Project Structure

```
claude-task-wrapper/
├── docker-compose.yml
├── api/
│   ├── Dockerfile
│   ├── main.py          # FastAPI application
│   └── requirements.txt
├── worker/
│   ├── Dockerfile
│   ├── main.py          # Worker entry point
│   ├── handlers/
│   │   ├── base.py      # ITaskHandler interface
│   │   └── claude.py    # Claude Code handlers
│   └── requirements.txt
├── shared/
│   ├── models/
│   │   └── task.py      # Task, TaskResult DTOs
│   └── queue/
│       ├── base.py      # Queue interfaces
│       └── redis_impl.py # Redis implementation
└── workspace/           # Mounted workspace
```

### Adding Custom Handlers

1. Create handler class implementing `ITaskHandler`:

```python
from worker.handlers.base import ITaskHandler, ValidationResult
from shared.models import Task, TaskResult, TaskType

class MyCustomHandler(ITaskHandler):
    @property
    def name(self) -> str:
        return "my-custom-handler"

    def supports(self, task: Task) -> bool:
        return task.task_type == TaskType.SINGLE

    def validate(self, task: Task) -> ValidationResult:
        return ValidationResult.valid()

    async def execute(self, task: Task) -> TaskResult:
        # Your implementation
        pass
```

2. Register in `worker/main.py`:

```python
self._registry.register(MyCustomHandler())
```

## Webhooks

Configure callback URL for async notifications:

```json
{
  "prompt": "Long running task",
  "callback_url": "https://your-server.com/webhook"
}
```

Webhook payload:
```json
{
  "task_id": "uuid",
  "status": "completed",
  "output": "...",
  "cost_usd": 0.05,
  "duration_seconds": 45.2
}
```

## Debugging

Enable Redis Commander UI:

```bash
docker-compose --profile debug up -d
# Access at http://localhost:8081
```

View logs:
```bash
docker-compose logs -f worker
docker-compose logs -f api
```

## License

MIT
