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

### Regular Tasks

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

### Environment Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/environments` | List available environments |
| `GET` | `/environments/{type}` | Get environment details |
| `POST` | `/environments/{type}/tasks` | Submit environment task |
| `GET` | `/environments/{type}/tasks/{id}` | Get environment task status |
| `GET` | `/environments/{type}/tasks` | List environment tasks |
| `POST` | `/environments/crash_analysis/tasks` | Submit crash analysis (convenience) |

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

## Execution Environments

Environments provide specialized, pre-configured contexts for specific tasks. Each environment includes:
- **CLAUDE.md**: Context and instructions for Claude
- **Workflow Steps**: Multi-step execution pipeline
- **Custom Commands**: Slash commands for the environment
- **Sub-agents**: Specialized agents for sub-tasks
- **Hooks**: Pre/post execution scripts

### Available Environments

| Environment | Type | Description |
|-------------|------|-------------|
| Crash Analysis | `crash_analysis` | Analyze crash reports with backtrace correlation |

### Crash Analysis Environment

Analyzes crash reports by cloning the repository at the crash commit and correlating backtraces with source code.

**Required Inputs:**
- `repo_url`: Git repository URL
- `backtrace`: The crash backtrace/stack trace

**Optional Inputs:**
- `commit_hash`: Git commit where crash occurred
- `branch`: Git branch (if no commit_hash)
- `logs`: Application logs around crash time

**Example:**
```bash
curl -X POST http://localhost:8000/environments/crash_analysis/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/user/project.git",
    "backtrace": "Traceback (most recent call last):\n  File \"app.py\", line 42...",
    "commit_hash": "abc123def",
    "additional_context": "Crash happens under high load"
  }'
```

**Workflow:**
1. Clone repository at specified commit
2. Validate repository structure
3. Parse and structure the backtrace
4. Analyze source files from stack frames
5. Generate comprehensive crash report

**Output Structure:**
```
/workspace/{task_id}/
├── repo/                    # Cloned repository
├── inputs/
│   ├── backtrace.txt       # Original backtrace
│   └── logs.txt            # Application logs
├── analysis/
│   ├── parsed_backtrace.json
│   ├── file_analysis.md
│   └── CRASH_REPORT.md     # Final analysis
└── CLAUDE.md               # Environment context
```

### Creating Custom Environments

1. Create environment directory:
```
environments/my_env/
├── __init__.py
├── environment.py
├── CLAUDE.md
└── .claude/commands/
    └── my-command.md
```

2. Implement `IEnvironment`:
```python
from environments.base import IEnvironment
from shared.models import EnvironmentType, EnvironmentConfig

class MyEnvironment(IEnvironment):
    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.CUSTOM

    @property
    def required_inputs(self) -> List[str]:
        return ["input1", "input2"]

    def get_claude_md(self, inputs: Dict) -> str:
        return "# My Environment\n..."

    def get_workflow_steps(self, inputs: Dict) -> List[WorkflowStep]:
        return [...]

    def get_final_prompt(self, inputs: Dict) -> str:
        return "Analyze the results..."
```

3. Register in `environments/__init__.py`:
```python
registry.register(MyEnvironment())
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | - | Required: Your Anthropic API key |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `CLAUDE_BINARY` | `claude` | Path to Claude CLI |
| `WORKSPACE_ROOT` | `/workspace` | Default working directory |
| `WORKSPACES_ROOT` | `/workspaces` | Root for environment workspaces |
| `MAX_CONCURRENT_TASKS` | `1` | Concurrent task limit |
| `WORKER_MODE` | `all` | Worker mode: `all`, `regular`, `environment` |
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
│   ├── main.py              # FastAPI application
│   └── requirements.txt
├── worker/
│   ├── Dockerfile
│   ├── main.py              # Worker entry point (regular + env)
│   └── handlers/
│       ├── base.py          # ITaskHandler interface
│       └── claude.py        # Claude Code handlers
├── shared/
│   ├── models/
│   │   ├── task.py          # Task, TaskResult DTOs
│   │   └── environment.py   # Environment models
│   ├── queue/
│   │   ├── base.py          # Queue interfaces
│   │   └── redis_impl.py    # Redis implementation
│   └── workspace/
│       └── manager.py       # Workspace manager
├── environments/
│   ├── base.py              # IEnvironment interface
│   └── crash_analysis/
│       ├── environment.py   # CrashAnalysisEnvironment
│       ├── CLAUDE.md        # Context template
│       └── .claude/commands/
└── workspace/               # Mounted workspace
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
