# Crash Analysis Environment

This is the template CLAUDE.md for crash analysis tasks.
The actual CLAUDE.md is generated dynamically with task-specific context.

## Environment Purpose
Analyze crash reports by correlating backtraces with source code.

## Standard Workflow
1. Clone repository at crash commit
2. Parse and structure backtrace
3. Locate and analyze relevant source files
4. Identify root cause
5. Generate fix recommendations

## Available Commands
- `/analyze-frame` - Deep-dive into a specific stack frame
- `/find-similar` - Search for similar vulnerable patterns
- `/generate-fix` - Create a patch for the issue
- `/summarize` - Executive summary of findings

## File Structure
```
/workspace/
├── repo/           # Source code at crash commit
├── inputs/         # Crash data (backtrace, logs)
├── analysis/       # Your outputs go here
└── CLAUDE.md       # This context file
```
