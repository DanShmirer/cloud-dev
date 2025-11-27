"""
Facts & Preferences Extraction Environment
Specialized environment for extracting important information from AI conversation messages
Following SOLID principles - Single Responsibility for extraction logic
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


class FactsExtractionEnvironment(IEnvironment):
    """
    Environment for extracting facts, preferences, and important information
    from AI conversation message history.

    Workflow:
    1. Parse and structure conversation messages
    2. Identify factual statements
    3. Extract user preferences and constraints
    4. Build user profile summary
    5. Generate structured output
    """

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.FACTS_EXTRACTION

    @property
    def name(self) -> str:
        return "Facts & Preferences Extraction"

    @property
    def description(self) -> str:
        return (
            "Analyzes AI conversation messages to extract facts, preferences, "
            "constraints, goals, and user profile information. Produces structured "
            "output suitable for personalization and context retention."
        )

    @property
    def required_inputs(self) -> List[str]:
        return ["messages"]

    def get_config(self) -> EnvironmentConfig:
        return EnvironmentConfig(
            env_type=self.env_type,
            name=self.name,
            description=self.description,
            claude_md_path="environments/facts_extraction/CLAUDE.md",
            workflow_steps=self.get_workflow_steps({}),
            hooks=HookConfig(
                pre_analysis="echo 'Starting facts extraction...'",
                post_analysis="echo 'Extraction complete'",
            ),
            subagents=[
                SubAgentConfig(
                    name="fact_classifier",
                    prompt_template="Classify this statement: {statement}",
                    model="haiku",
                    allowed_tools=["Read"],
                    max_turns=3,
                ),
                SubAgentConfig(
                    name="preference_analyzer",
                    prompt_template="Analyze user preferences from: {text}",
                    model="sonnet",
                    allowed_tools=["Read"],
                    max_turns=5,
                ),
            ],
            default_model="sonnet",
            default_allowed_tools=["Read", "Write", "Glob"],
            required_inputs=self.required_inputs,
        )

    def get_claude_md(self, inputs: Dict[str, Any]) -> str:
        """Generate CLAUDE.md content for facts extraction"""
        message_count = len(inputs.get("messages", []))
        context_name = inputs.get("context_name", "conversation")
        extraction_focus = inputs.get("extraction_focus", "general")

        return f'''# Facts & Preferences Extraction Environment

## Context
You are analyzing a conversation with {message_count} messages.
Context identifier: `{context_name}`
Extraction focus: `{extraction_focus}`

## Workspace Structure
```
/workspace/
├── inputs/
│   ├── messages.json       # The conversation messages to analyze
│   └── config.json         # Extraction configuration
├── extraction/             # Your extraction outputs
│   ├── facts.json          # Extracted facts
│   ├── preferences.json    # Extracted preferences
│   ├── profile.json        # User profile summary
│   └── topics.json         # Key topics identified
└── CLAUDE.md               # This file
```

## Your Task

### Phase 1: Message Analysis
1. **Read the Messages**: Load `/workspace/inputs/messages.json`
2. **Understand the Flow**: Note conversation topic transitions
3. **Identify Speakers**: Distinguish user vs assistant messages

### Phase 2: Fact Extraction
For each message, extract **facts** - objective, verifiable statements:
- Personal facts (name, location, profession, etc.)
- Technical facts (systems used, configurations, requirements)
- Business facts (company, role, projects)
- Temporal facts (dates, timelines, schedules)

### Phase 3: Preference Extraction
Extract **preferences** - subjective likes, dislikes, and tendencies:
- Communication preferences (formal/casual, detailed/brief)
- Technical preferences (languages, tools, frameworks)
- Work style preferences (collaboration, deadlines, approach)
- Content preferences (examples, explanations, visuals)

### Phase 4: Constraint Identification
Extract **constraints** - limitations, requirements, or boundaries:
- Technical constraints (platform, language, dependencies)
- Resource constraints (time, budget, team size)
- Policy constraints (security, compliance, standards)

### Phase 5: Goal Recognition
Extract **goals** - what the user is trying to achieve:
- Immediate goals (current task/question)
- Project goals (larger objectives)
- Learning goals (skills to develop)

## Output Format

### facts.json
```json
{{
  "facts": [
    {{
      "category": "personal|technical|business|temporal",
      "content": "The extracted fact",
      "confidence": 0.95,
      "source_message_index": 3,
      "tags": ["relevant", "tags"]
    }}
  ]
}}
```

### preferences.json
```json
{{
  "preferences": [
    {{
      "category": "communication|technical|work_style|content",
      "content": "Description of the preference",
      "confidence": 0.8,
      "evidence": "Quote or reference from conversation",
      "tags": ["tag1", "tag2"]
    }}
  ]
}}
```

### profile.json
```json
{{
  "user_profile": {{
    "identity": {{ "name": null, "role": null, "expertise_level": null }},
    "context": {{ "domain": null, "project": null, "team_size": null }},
    "communication_style": {{ "formality": null, "detail_level": null }},
    "technical_stack": [],
    "key_interests": [],
    "working_patterns": []
  }},
  "summary": "One paragraph profile summary"
}}
```

### topics.json
```json
{{
  "key_topics": ["topic1", "topic2"],
  "topic_transitions": [
    {{ "from": "topic1", "to": "topic2", "message_index": 5 }}
  ],
  "primary_focus": "main topic"
}}
```

## Guidelines

1. **Be Conservative**: Only extract information explicitly stated or strongly implied
2. **Track Confidence**: Rate each extraction 0.0-1.0 based on certainty
3. **Cite Sources**: Reference the message index for traceability
4. **Handle Contradictions**: Note when user corrects or changes information
5. **Respect Privacy**: Flag but don't over-interpret sensitive information
6. **Context Matters**: Consider conversation flow, not just individual messages

## Available Commands
Use `/extract-facts` to run targeted fact extraction on specific messages.
Use `/build-profile` to generate the user profile from extracted data.
Use `/summarize` to create a brief summary of findings.
'''

    def get_commands(self) -> Dict[str, str]:
        """Get custom slash commands for facts extraction"""
        return {
            "extract-facts": '''Extract facts from specific messages.

Arguments: $ARGUMENTS (message indices or "all")

Steps:
1. Read specified messages from /workspace/inputs/messages.json
2. For each message, identify factual statements
3. Classify each fact by category
4. Assign confidence scores
5. Save to /workspace/extraction/facts.json

Focus on:
- Explicit statements ("I am...", "We use...", "Our project...")
- Implicit facts from context
- Corrected information (prefer latest)
''',

            "extract-preferences": '''Extract preferences from the conversation.

Arguments: $ARGUMENTS (preference type or "all")

Steps:
1. Analyze user messages for expressed preferences
2. Look for patterns in how they ask questions
3. Note tool/technology preferences
4. Identify communication style preferences
5. Save to /workspace/extraction/preferences.json

Look for:
- Explicit preferences ("I prefer...", "I like...")
- Implicit preferences (what they ask for, how they react)
- Anti-preferences ("I don't want...", "avoid...")
''',

            "build-profile": '''Build a comprehensive user profile.

Synthesize all extracted facts and preferences into:
1. Identity summary
2. Technical context
3. Communication preferences
4. Key interests and goals

Save to /workspace/extraction/profile.json
''',

            "summarize": '''Create an executive summary of all extractions.

Generate a brief, readable summary that includes:
- Key facts about the user
- Primary preferences
- Main goals and constraints
- Recommended interaction approach

Output both JSON and human-readable formats.
''',

            "validate": '''Validate extracted information for consistency.

Check for:
- Contradictions between facts
- Preference conflicts
- Temporal inconsistencies
- Low-confidence items that need review

Report any issues found.
''',
        }

    def get_workflow_steps(self, inputs: Dict[str, Any]) -> List[WorkflowStep]:
        """Define the facts extraction workflow"""
        return [
            WorkflowStep(
                name="parse_messages",
                description="Parse and validate the input messages",
                step_type="claude",
                prompt_template='''Read /workspace/inputs/messages.json and validate the message structure.

Create /workspace/extraction/message_summary.json with:
- total_messages: count of messages
- user_messages: count of user messages
- assistant_messages: count of assistant messages
- conversation_length: rough word count
- detected_language: primary language used
- time_span: if timestamps available

Also identify any formatting issues or incomplete messages.''',
                timeout_seconds=60,
            ),
            WorkflowStep(
                name="extract_facts",
                description="Extract factual information from messages",
                step_type="claude",
                prompt_template='''Analyze all messages in /workspace/inputs/messages.json to extract facts.

For each user message, identify:
1. Personal facts (name, location, role, etc.)
2. Technical facts (tools, languages, systems)
3. Business context (company, project, team)
4. Temporal facts (dates, deadlines, schedules)

Save structured output to /workspace/extraction/facts.json following the schema in CLAUDE.md.

Be thorough but conservative - only extract clearly stated information.''',
                timeout_seconds=180,
            ),
            WorkflowStep(
                name="extract_preferences",
                description="Extract user preferences and tendencies",
                step_type="claude",
                prompt_template='''Analyze all messages to extract preferences.

Look for:
1. Communication preferences (how they like to receive info)
2. Technical preferences (tools, languages, approaches)
3. Work style preferences (detailed vs brief, examples vs theory)
4. Explicit likes and dislikes

Also analyze:
- Question patterns (what details they ask for)
- Response preferences (what they engage with positively)
- Anti-patterns (what they reject or redirect)

Save to /workspace/extraction/preferences.json following the schema.''',
                timeout_seconds=180,
            ),
            WorkflowStep(
                name="identify_goals_constraints",
                description="Identify user goals and constraints",
                step_type="claude",
                prompt_template='''Analyze the conversation for goals and constraints.

Goals to identify:
- Immediate goal: What they're trying to accomplish now
- Project goals: Larger objectives mentioned
- Learning goals: Skills they want to develop
- Outcome goals: What success looks like for them

Constraints to identify:
- Technical: Platform, language, dependency limits
- Resource: Time, budget, team constraints
- Policy: Security, compliance, standards

Save findings appended to facts.json with category "goal" or "constraint".''',
                timeout_seconds=120,
            ),
            WorkflowStep(
                name="extract_topics",
                description="Identify key topics and conversation flow",
                step_type="claude",
                prompt_template='''Analyze the conversation for topic structure.

Identify:
1. Key topics discussed (5-10 main topics)
2. Topic transitions (when conversation shifted)
3. Primary focus (main theme)
4. Subtopics and their relationship to main topic

Save to /workspace/extraction/topics.json with:
- key_topics: array of topic strings
- topic_transitions: array of {from, to, message_index}
- primary_focus: string
- topic_hierarchy: nested structure if applicable''',
                timeout_seconds=90,
            ),
            WorkflowStep(
                name="build_profile",
                description="Synthesize extracted data into user profile",
                step_type="claude",
                prompt_template='''Read all extraction files and build a comprehensive user profile.

Synthesize:
- /workspace/extraction/facts.json
- /workspace/extraction/preferences.json
- /workspace/extraction/topics.json

Create /workspace/extraction/profile.json with:
- identity: Who they are (role, expertise, context)
- preferences: How they like to work
- goals: What they're trying to achieve
- constraints: Limitations they're working within
- communication_style: How to best interact with them
- summary: 2-3 paragraph profile narrative

Make the profile actionable for future interactions.''',
                timeout_seconds=120,
            ),
        ]

    def get_final_prompt(self, inputs: Dict[str, Any]) -> str:
        """Get the final synthesis prompt"""
        additional_prompt = inputs.get("additional_prompt", "")
        focus_areas = inputs.get("focus_areas", [])

        focus_section = ""
        if focus_areas:
            focus_section = f"\n\nPay special attention to: {', '.join(focus_areas)}"

        return f'''Complete the facts and preferences extraction.

## Instructions

1. Review all extraction files in /workspace/extraction/
2. Verify consistency across extracted data
3. Resolve any contradictions (prefer more recent information)
4. Create final comprehensive output

## Create Final Report

Write to /workspace/extraction/EXTRACTION_REPORT.md:

### Summary
- Total facts extracted with breakdown by category
- Total preferences identified
- Confidence distribution (high/medium/low counts)
- Key insights

### User Profile
- Copy the narrative summary from profile.json
- Highlight most important/useful information

### Extracted Facts (High Confidence)
- List facts with confidence >= 0.8
- Group by category

### Extracted Preferences
- Communication preferences
- Technical preferences
- Work style preferences

### Goals & Constraints
- Active goals identified
- Key constraints to consider

### Recommendations
- How to use this information
- What to verify or clarify
- Suggested follow-up topics

### Data Quality Assessment
- Coverage: How much was extractable
- Confidence: Overall certainty level
- Gaps: What information is missing
{focus_section}

{additional_prompt}

After writing the report, output a JSON summary to stdout with:
- fact_count
- preference_count
- profile_completeness (0-100%)
- key_insights (array of 3-5 strings)
'''

    def get_subagent_prompts(self) -> Dict[str, str]:
        """Sub-agent prompts for specialized extraction"""
        return {
            "fact_verifier": '''Verify the consistency of extracted facts.

Compare facts for:
- Contradictions (same topic, different values)
- Temporal conflicts (timeline issues)
- Logical inconsistencies

Return a list of potential issues to review.
''',

            "preference_inferrer": '''Infer implicit preferences from behavior patterns.

Analyze:
- Types of questions asked
- Level of detail in responses
- Topics that get follow-up questions
- Communication patterns

Generate inferred preferences with lower confidence scores.
''',

            "profile_validator": '''Validate the user profile for completeness and accuracy.

Check:
- All sections populated appropriately
- No contradictory information
- Confidence levels are reasonable
- Summary accurately reflects data

Suggest improvements if needed.
''',

            "sensitivity_scanner": '''Scan extracted data for sensitive information.

Flag:
- Personal identifiers (email, phone, etc.)
- Financial information
- Health information
- Credentials or secrets

Recommend handling for flagged items.
''',
        }

    def validate_inputs(self, inputs: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate inputs for facts extraction"""
        errors = []

        # Check required field
        if "messages" not in inputs:
            errors.append("'messages' field is required")
            return False, errors

        messages = inputs.get("messages", [])

        # Validate messages is a list
        if not isinstance(messages, list):
            errors.append("'messages' must be a list")
            return False, errors

        # Validate message count
        if len(messages) == 0:
            errors.append("'messages' list cannot be empty")
            return False, errors

        if len(messages) > 10000:
            errors.append("'messages' list exceeds maximum of 10000 messages")
            return False, errors

        # Validate each message structure
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                errors.append(f"Message at index {i} must be an object")
                continue

            if "role" not in msg:
                errors.append(f"Message at index {i} missing 'role' field")

            if "content" not in msg:
                errors.append(f"Message at index {i} missing 'content' field")
            elif not isinstance(msg.get("content"), str):
                errors.append(f"Message at index {i} 'content' must be a string")

            # Validate role if present
            if "role" in msg and msg["role"] not in ["user", "assistant", "system"]:
                errors.append(f"Message at index {i} has invalid role: {msg['role']}")

        if errors:
            return False, errors

        return True, []
