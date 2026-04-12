# Prompt Organization Design

**Date:** 2026-04-12

## Context

The harness has four places where prompts can live: agent YAMLs, skills, workflow step prompts, and job/CLI input. Without clear rules for what belongs where, it is hard to know where to add new guidance. The root cause is that agent prompts currently mix role identity with process guidance and sometimes workflow-specific context.

## The Four Layers

Each layer answers exactly one question. If guidance answers a different question, it belongs in a different layer.

```
┌──────────────────────────────────────────────────────┐
│  CLI / job prompt  →  "What is my task?"             │
│  Step prompt       →  "What matters in this pipeline?"│
│  Agent prompt      →  "Who am I, always?"            │
│  Skill             →  "How do I do X?"               │
└──────────────────────────────────────────────────────┘
```

### Agent prompt (`agents/*.yaml` — `prompt:` field)

**Question:** "Who am I, always?"

- 2–4 sentences of identity: role, output format, constraints
- Stable; almost never changes
- True regardless of which workflow or task is running

**Example:**
> "You are a code reviewer. You are thorough and critical. You respond with either APPROVED or CHANGES REQUESTED followed by a concise explanation."

### Skill (`skills/*/SKILL.md`)

**Question:** "How do I do X?"

- Detailed, prescriptive process guidance
- Reusable across agents and workflows
- Loaded on-demand; agents read the full file before using

**Example:**
> "When reviewing: first read all changed files, run tests, check linting, then give your verdict."

### Step prompt (`workflows/*.yaml` — `steps[].prompt:`)

**Question:** "What matters in this pipeline?"

- 1–2 sentences of workflow context
- Prepended before the previous step's output (context first, then content)
- Specific to this workflow and position; would not apply universally

**Example:**
> "Focus on the security implications of these changes."

### Job / CLI input (`jobs/*.yaml` — `prompt:` field, or CLI argument)

**Question:** "What is my task?"

- The actual work to be done, right now
- Ephemeral and run-specific
- Passed as the initial `current_input` into the pipeline

**Example:**
> "Review the changes in `auth.py`."

## The Decision Rule

> **"Would this guidance change if I used this agent in a different workflow?"**
> - No → agent prompt
> - Yes, it's workflow-specific → step prompt
> - Yes, it's a reusable process → skill
> - It's the actual task → job / CLI

## Impact on Existing Agents

Agent prompts should be trimmed to identity only. Process guidance moves to skills; workflow-specific guidance moves to step prompts.

| Agent | Keep in prompt | Move |
|---|---|---|
| reviewer | "thorough, return APPROVED/CHANGES REQUESTED" | "run tests and linting" → skill |
| implementer | "execute coding tasks cleanly" | "avoid over-engineering, report changes" → skill or step |
| planner | "produce a step-by-step plan" | process already handled by brainstorming skill |
| coordinator | "max 3 revision cycle" (always true) | delegation logic → skill |
| brainstormer | already thin | minimal change |
| linear | already thin | minimal change |

## What This Is Not

This design does not prescribe which agents exist, which skills to create, or what the content of any prompt should be. It only defines where each type of guidance lives and why.
