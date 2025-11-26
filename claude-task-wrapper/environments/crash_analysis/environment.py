"""
Crash Analysis Environment
Specialized environment for analyzing crash reports with backtrace, git context, and source code
"""
from typing import Dict, Any, List

from shared.models import (
    EnvironmentType,
    EnvironmentConfig,
    WorkflowStep,
    HookConfig,
    SubAgentConfig,
)
from environments.base import IEnvironment


class CrashAnalysisEnvironment(IEnvironment):
    """
    Environment for crash/error analysis

    Workflow:
    1. Clone repository at specified commit
    2. Parse and analyze backtrace
    3. Correlate stack frames with source code
    4. Identify root cause
    5. Suggest fixes
    """

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.CRASH_ANALYSIS

    @property
    def name(self) -> str:
        return "Crash Analysis"

    @property
    def description(self) -> str:
        return (
            "Analyzes crash reports by correlating backtraces with source code. "
            "Clones the repository at the crash commit, parses stack frames, "
            "and provides root cause analysis with fix suggestions."
        )

    @property
    def required_inputs(self) -> List[str]:
        return ["repo_url", "backtrace"]

    def get_config(self) -> EnvironmentConfig:
        return EnvironmentConfig(
            env_type=self.env_type,
            name=self.name,
            description=self.description,
            claude_md_path="environments/crash_analysis/CLAUDE.md",
            workflow_steps=self.get_workflow_steps({}),
            hooks=HookConfig(
                post_clone="echo 'Repository cloned successfully'",
                pre_analysis="ls -la repo/",
            ),
            subagents=[
                SubAgentConfig(
                    name="stack_parser",
                    prompt_template="Parse this stack trace and identify key frames: {backtrace}",
                    model="haiku",
                    allowed_tools=["Read"],
                    max_turns=5,
                ),
                SubAgentConfig(
                    name="code_analyzer",
                    prompt_template="Analyze the code at {file_path}:{line_number} for potential issues",
                    model="sonnet",
                    allowed_tools=["Read", "Grep", "Glob"],
                    max_turns=10,
                ),
            ],
            default_model="sonnet",
            default_allowed_tools=[
                "Read", "Glob", "Grep", "Bash", "Task"
            ],
            required_inputs=self.required_inputs,
        )

    def get_claude_md(self, inputs: Dict[str, Any]) -> str:
        """Generate CLAUDE.md content for crash analysis"""
        repo_url = inputs.get("repo_url", "unknown")
        commit_hash = inputs.get("commit_hash", "HEAD")

        return f'''# Crash Analysis Environment

## Context
You are analyzing a crash report for the repository: `{repo_url}`
The crash occurred at commit: `{commit_hash}`

## Workspace Structure
```
/workspace/
├── repo/                    # Cloned repository at crash commit
├── inputs/
│   ├── backtrace.txt       # The crash backtrace
│   ├── logs.txt            # Application logs (if provided)
│   └── context.json        # Additional context data
├── analysis/               # Your analysis outputs
└── CLAUDE.md              # This file
```

## Your Task
1. **Parse the Backtrace**: Read `/workspace/inputs/backtrace.txt` and identify:
   - The crash type (segfault, assertion, exception, etc.)
   - The failing function and its call chain
   - Relevant source file paths and line numbers

2. **Analyze Source Code**: For each relevant stack frame:
   - Navigate to the source file in `/workspace/repo/`
   - Understand the code context around the crash point
   - Look for common bug patterns (null pointers, buffer overflows, race conditions)

3. **Identify Root Cause**: Determine:
   - What triggered the crash
   - Why the crash occurred at this specific code path
   - Any contributing factors (data corruption, invalid state, etc.)

4. **Suggest Fixes**: Provide:
   - Specific code changes to fix the issue
   - Any additional defensive measures needed
   - Test cases to prevent regression

## Available Commands
Use `/analyze-frame` to deep-dive into a specific stack frame.
Use `/find-similar` to search for similar patterns in the codebase.
Use `/generate-fix` to create a patch for the identified issue.

## Output Format
Structure your analysis as:

### Summary
Brief description of the crash and its cause.

### Stack Analysis
Detailed breakdown of relevant stack frames.

### Root Cause
Explanation of why the crash occurred.

### Recommended Fix
Code changes and preventive measures.

### Confidence Level
Your confidence in the analysis (High/Medium/Low) with reasoning.
'''

    def get_commands(self) -> Dict[str, str]:
        """Get custom slash commands for crash analysis"""
        return {
            "analyze-frame": '''Analyze a specific stack frame in detail.

Arguments: $ARGUMENTS

Steps:
1. Extract the file path and line number from the frame
2. Read the source file around the specified line
3. Analyze the function for potential issues
4. Check for related code patterns
5. Report findings with severity assessment

Focus on:
- Null pointer dereferences
- Buffer overflows
- Use-after-free
- Race conditions
- Integer overflows
- Assertion failures
''',

            "find-similar": '''Search for similar code patterns that might have the same vulnerability.

Arguments: $ARGUMENTS

Use Grep and Glob to:
1. Find functions with similar signatures
2. Search for similar variable usage patterns
3. Look for matching error handling patterns
4. Identify code that was copy-pasted from the crash location
''',

            "generate-fix": '''Generate a code fix for the identified crash.

Based on the analysis, create:
1. A minimal patch that fixes the immediate issue
2. Any necessary null checks or validation
3. Updated error handling
4. A simple test case to verify the fix

Output the fix as a unified diff format.
''',

            "summarize": '''Create an executive summary of the crash analysis.

Include:
- One-line summary of the crash
- Impact assessment
- Root cause in non-technical terms
- Fix status and timeline recommendation
- Risk of recurrence
''',
        }

    def get_workflow_steps(self, inputs: Dict[str, Any]) -> List[WorkflowStep]:
        """Define the crash analysis workflow"""
        commit_hash = inputs.get("commit_hash")

        steps = [
            WorkflowStep(
                name="clone_repository",
                description="Clone the repository at the crash commit",
                step_type="shell",
                command=self._build_clone_command(inputs),
                timeout_seconds=300,
            ),
            WorkflowStep(
                name="validate_structure",
                description="Verify repository structure and find relevant files",
                step_type="shell",
                command="cd repo && find . -type f -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.go' -o -name '*.rs' -o -name '*.cpp' -o -name '*.c' -o -name '*.h' | head -100",
                timeout_seconds=30,
            ),
            WorkflowStep(
                name="parse_backtrace",
                description="Parse and structure the backtrace for analysis",
                step_type="claude",
                prompt_template='''Read the backtrace from /workspace/inputs/backtrace.txt and parse it.

Create a structured analysis file at /workspace/analysis/parsed_backtrace.json with:
- crash_type: The type of crash/error
- frames: Array of stack frames with file, function, line number
- key_frame: The most relevant frame to investigate
- language: Detected programming language

Also create /workspace/analysis/files_to_analyze.txt with a list of source files mentioned in the backtrace that exist in the repo.''',
                timeout_seconds=120,
            ),
            WorkflowStep(
                name="analyze_key_files",
                description="Analyze the source files from the backtrace",
                step_type="claude",
                prompt_template='''Using the parsed backtrace, analyze the key source files.

For each file in /workspace/analysis/files_to_analyze.txt:
1. Read the file from /workspace/repo/
2. Find the specific line mentioned in the backtrace
3. Analyze the surrounding code (50 lines before and after)
4. Document any suspicious patterns

Save your file-by-file analysis to /workspace/analysis/file_analysis.md''',
                timeout_seconds=300,
            ),
        ]

        return steps

    def _build_clone_command(self, inputs: Dict[str, Any]) -> str:
        """Build the git clone command"""
        repo_url = inputs.get("repo_url", "")
        commit_hash = inputs.get("commit_hash")
        branch = inputs.get("branch")

        if commit_hash:
            # Need full clone for specific commit
            return f'''
git clone {repo_url} repo && \
cd repo && \
git checkout {commit_hash}
'''
        elif branch:
            return f'''
git clone --depth 1 --branch {branch} {repo_url} repo
'''
        else:
            return f'''
git clone --depth 1 {repo_url} repo
'''

    def get_final_prompt(self, inputs: Dict[str, Any]) -> str:
        """Get the final analysis prompt"""
        return '''Perform a complete crash analysis based on all the preparatory work done.

## Instructions

1. Review all analysis files in /workspace/analysis/
2. Read the original backtrace from /workspace/inputs/backtrace.txt
3. Synthesize findings from file_analysis.md and parsed_backtrace.json

## Create Final Report

Write a comprehensive crash report to /workspace/analysis/CRASH_REPORT.md with:

### Executive Summary
- One paragraph summary suitable for non-technical stakeholders
- Severity rating (Critical/High/Medium/Low)
- Estimated fix complexity

### Technical Analysis
- Detailed breakdown of what caused the crash
- Full call chain analysis
- Memory/state analysis if relevant

### Root Cause
- Primary cause with evidence
- Contributing factors
- Why existing safeguards failed

### Recommended Fix
- Specific code changes (with file paths and line numbers)
- Include actual code snippets showing before/after
- Any necessary infrastructure changes

### Prevention Measures
- How to prevent similar crashes
- Suggested test cases
- Code review checklist items

### Confidence Assessment
- Confidence level in the analysis
- What additional information would help
- Known uncertainties

After writing the report, output a brief summary for the user.
'''

    def get_subagent_prompts(self) -> Dict[str, str]:
        """Sub-agent prompts for specialized analysis"""
        return {
            "memory_analyzer": '''Analyze potential memory-related issues at the crash location.

Look for:
- Buffer overflows/underflows
- Use-after-free
- Double-free
- Memory leaks that could cause resource exhaustion
- Stack overflow risks

Provide specific line numbers and code patterns.
''',

            "concurrency_analyzer": '''Analyze potential concurrency issues at the crash location.

Look for:
- Race conditions
- Deadlocks
- Lock ordering violations
- Missing synchronization
- Thread-safety violations

Identify shared resources and synchronization mechanisms.
''',

            "input_validator": '''Analyze input validation at the crash location.

Look for:
- Missing null checks
- Unchecked array/string bounds
- Integer overflow possibilities
- Format string vulnerabilities
- Injection possibilities

Trace data flow from input to crash point.
''',
        }
