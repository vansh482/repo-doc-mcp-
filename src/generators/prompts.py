"""
Prompt Templates for Documentation Generation.

Architecture: section-by-section generation. Each section gets its own focused
prompt with only the context it needs. This produces complete, detailed content
instead of one giant LLM call that truncates mid-way.

Each section template receives a `context` dict with these possible keys:
  - repo_name, branch, commit, languages, total_files, total_lines
  - project_purpose, architecture_summary, tech_stack
  - key_components, entry_points, file_details
  - dependencies, directory_tree
"""

# ──────────────────────────────────────────────────────────────────────
# System Prompts
# ──────────────────────────────────────────────────────────────────────

TECHNICAL_SYSTEM_PROMPT = """You are an expert technical writer creating internal engineering documentation.

Your audience is software engineers who need to understand, maintain, and extend this codebase.

Rules:
- Be precise — use actual class names, function names, and file paths from the provided context
- Explain WHY decisions were made, not just WHAT exists
- Include code-level details: important functions, data flow, error handling
- Use Mermaid diagrams where they add clarity (```mermaid blocks)
- Write enough detail that a new engineer could get productive within a day
- Do NOT include section headings — just write the content directly
- Do NOT repeat the section title in your response
- Write in Markdown format"""

NON_TECHNICAL_SYSTEM_PROMPT = """You are a skilled communicator translating technical systems into plain language.

Your audience is non-technical team members: product managers, designers, executives, and support teams.

Rules:
- NO code snippets, NO jargon without explanation
- Use everyday analogies (restaurants, libraries, post offices, etc.)
- Focus on WHAT the system does and WHY it matters for the business
- Keep paragraphs short (3-4 sentences max)
- Write in a warm, conversational tone
- Do NOT include section headings — just write the content directly
- Do NOT repeat the section title in your response"""


# ──────────────────────────────────────────────────────────────────────
# Technical Documentation — Per-Section Prompts
# ──────────────────────────────────────────────────────────────────────

TECH_SECTIONS = [
    {
        "title": "Executive Summary",
        "prompt": """Write a 2-3 paragraph executive summary for this codebase.

Repository: {repo_name}
Branch: {branch} | Commit: {commit}
Languages: {languages} | Files: {total_files} | Lines: {total_lines}

What the project does:
{project_purpose}

How it's built:
{architecture_summary}

Technologies:
{tech_stack}

Cover: what problem it solves, who it's for, and the high-level approach. Be specific to THIS project.""",
    },
    {
        "title": "System Architecture",
        "prompt": """Describe the system architecture in detail.

Architecture overview:
{architecture_summary}

Key components:
{key_components}

Internal dependencies:
{dependencies}

Directory structure:
{directory_tree}

Include:
1. A Mermaid diagram (```mermaid block) showing how major components connect
2. How components communicate (function calls, events, HTTP, subprocess, etc.)
3. Key design patterns used and WHY they were chosen
4. Data flow between components

Be specific — reference actual file paths and module names.""",
    },
    {
        "title": "Tech Stack & Dependencies",
        "prompt": """Document the technology stack and dependencies.

Technologies used:
{tech_stack}

Languages: {languages}

Key file details (showing imports and frameworks):
{file_details}

For each technology/framework:
- What role it plays in the system
- Why it was likely chosen (trade-offs)
- Version constraints or compatibility notes if visible

Group by: languages, frameworks, external services, dev tools.""",
    },
    {
        "title": "Core Components",
        "prompt": """Document each major module/component in detail.

Key components:
{key_components}

File-level details:
{file_details}

Internal dependencies:
{dependencies}

For each component, cover:
- **Purpose**: What it does and why it exists
- **Key classes/functions**: Most important interfaces with brief descriptions
- **How it connects**: Which other components it depends on or serves
- **Important data structures**: Key models or types it defines/uses

Be thorough — this is the section engineers will reference most. Use actual class names, function signatures, and file paths.""",
    },
    {
        "title": "Data Flow",
        "prompt": """Describe how data moves through the system.

Entry points:
{entry_points}

Architecture:
{architecture_summary}

Dependencies:
{dependencies}

Key components:
{key_components}

Include:
1. The main request/data flow from input to output (use a Mermaid sequence or flow diagram)
2. Any data transformation steps
3. Where state is stored or persisted
4. Error handling and fallback paths

Trace at least one complete flow from user action to final output.""",
    },
    {
        "title": "API Reference",
        "prompt": """Document the key public interfaces of this codebase.

File details (classes, functions, imports):
{file_details}

Entry points:
{entry_points}

Focus on:
- Public functions and their parameters/return types
- Important classes and their key methods
- Configuration interfaces
- CLI arguments or commands (if applicable)

Format as a reference — engineers will look things up here. Use code formatting for function signatures.""",
    },
    {
        "title": "Configuration",
        "prompt": """Document how this application is configured.

Tech stack:
{tech_stack}

File details:
{file_details}

Entry points:
{entry_points}

Directory structure:
{directory_tree}

Cover:
- Config files and their format (YAML, JSON, env vars, etc.)
- Environment variables
- Required vs optional settings
- Default values and what they mean
- How to override config for different environments (dev, staging, prod)""",
    },
    {
        "title": "Development Guide",
        "prompt": """Write a practical development guide for new contributors.

Tech stack:
{tech_stack}

Entry points:
{entry_points}

Directory structure:
{directory_tree}

Languages: {languages}

Cover:
1. Prerequisites (language versions, tools needed)
2. How to set up the development environment step-by-step
3. How to run the application locally
4. How to run the test suite
5. How to build for production
6. Key development workflows (hot reload, debugging, etc.)

Be specific enough that someone could follow these steps verbatim.""",
    },
    {
        "title": "Known Limitations & Technical Debt",
        "prompt": """Identify limitations and potential technical debt based on the codebase.

Project purpose:
{project_purpose}

Architecture:
{architecture_summary}

Tech stack:
{tech_stack}

Key components:
{key_components}

File details:
{file_details}

Be honest and constructive. Cover:
- Architectural limitations (scalability, coupling, etc.)
- Missing features or incomplete implementations visible in the code
- Dependencies that may need updating
- Areas where the code is complex or fragile
- Potential security considerations

Frame as "things to be aware of" rather than criticism.""",
    },
]


# ──────────────────────────────────────────────────────────────────────
# Non-Technical Documentation — Per-Section Prompts
# ──────────────────────────────────────────────────────────────────────

NON_TECH_SECTIONS = [
    {
        "title": "What Is This Project?",
        "prompt": """Explain what this software project does in 2-3 paragraphs, as if explaining to a smart friend who has never seen code.

Project name: {repo_name}
What it does: {project_purpose}
How it's built: {architecture_summary}

Cover: What problem does it solve? Who is it for? Use a real-world analogy to make it concrete. Avoid ALL technical jargon.""",
    },
    {
        "title": "How It Works (The Big Picture)",
        "prompt": """Explain how this system works using an everyday analogy.

Architecture: {architecture_summary}
Key components: {key_components}
Technologies: {tech_stack}

Pick ONE strong analogy (restaurant, library, post office, factory, etc.) and map each major component to something in that analogy. Make it vivid and memorable. The reader should walk away understanding the overall structure even if they forget the details.""",
    },
    {
        "title": "What Can It Do? (Features)",
        "prompt": """List and explain the main features/capabilities in plain language.

Project purpose: {project_purpose}
Key components: {key_components}
Entry points: {entry_points}

For each feature:
- What the user experiences (what they see or get)
- What happens behind the scenes (in simple terms, no jargon)
- Why it matters (business value)

Write 4-7 features. Use sub-headings (### Feature Name) for each one.""",
    },
    {
        "title": "The Building Blocks",
        "prompt": """Explain each major component of the system in simple terms.

Key components: {key_components}
How they connect: {dependencies}
Architecture: {architecture_summary}

For each component:
- Give it a friendly name alongside its technical name
- Explain what it does using an analogy
- Explain how it connects to the other parts

Keep it conversational. Use "Think of it as..." or "It's like..." liberally.""",
    },
    {
        "title": "How Users Interact With It",
        "prompt": """Walk through a typical user journey step by step.

Entry points: {entry_points}
Key components: {key_components}
Project purpose: {project_purpose}

Describe 1-2 complete scenarios:
- What does the user do first?
- What happens at each step (from their perspective)?
- What's the end result they get?

NO technical details. Write it like directions to a store — simple, sequential, clear.""",
    },
    {
        "title": "What Technologies Are Used (And Why)",
        "prompt": """Explain the technologies used in plain English.

Technologies: {tech_stack}
Languages: {languages}

For each major technology:
- What it does in ONE sentence (plain English)
- A real-world analogy for what it does
- Why this particular one was chosen (in business terms)

Don't list every dependency — focus on the 5-8 most important ones that a non-technical person might hear mentioned in meetings.""",
    },
    {
        "title": "Frequently Asked Questions",
        "prompt": """Write a FAQ section for non-technical team members.

Project: {repo_name}
Purpose: {project_purpose}
Tech stack: {tech_stack}
Architecture: {architecture_summary}

Write 6-8 questions and answers covering:
- "How long does [the main operation] take?"
- "Is our data safe / private?"
- "What happens if something goes wrong?"
- "Can it handle [scaling concern]?"
- "What are the limitations?"
- "What's planned for the future?"
- Any other questions a PM, designer, or executive would ask

Format as ### Question followed by a 2-3 sentence answer.""",
    },
    {
        "title": "Glossary",
        "prompt": """Create a glossary of technical terms that appear in this documentation.

Technologies: {tech_stack}
Key components: {key_components}
Architecture: {architecture_summary}

For each term:
- **Term**: Plain English definition (one sentence) followed by an analogy.

Include 15-20 terms. Focus on terms that non-technical team members might encounter in meetings, Slack conversations, or this documentation. Make every definition understandable to someone with zero programming knowledge.""",
    },
]


# ──────────────────────────────────────────────────────────────────────
# Architecture Diagram Prompt (standalone)
# ──────────────────────────────────────────────────────────────────────

ARCHITECTURE_DIAGRAM_PROMPT = """Generate a Mermaid diagram showing the system architecture.

Components:
{key_components}

Dependencies:
{dependencies}

Tech stack:
{tech_stack}

Generate a Mermaid flowchart (graph TD) showing:
1. Main components/modules as nodes
2. Dependencies between them as edges
3. External services as cylinder or cloud shapes
4. Group related components in subgraphs

Keep it high-level (max 15-20 nodes). Use clear, readable labels.

Respond with ONLY the Mermaid code. Start with ```mermaid and end with ```."""
