"""Skills loading and system prompt construction."""

from pathlib import Path

from prompts import CODER


def _load_skills() -> dict[str, dict]:
    """Read skills/<name>/SKILL.md and return a dict keyed by skill name."""
    skills_dir = Path(__file__).parent / "skills"
    if not skills_dir.is_dir():
        return {}
    result = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = next(
            (skill_dir / n for n in ("SKILL.md", "skill.md") if (skill_dir / n).exists()),
            None,
        )
        if not skill_file:
            continue
        text = skill_file.read_text()
        name = description = None
        lines = text.splitlines()
        if lines and lines[0].startswith("--"):
            for line in lines[1:]:
                if line.startswith("--"):
                    break
                if line.startswith("name:"):
                    name = line[5:].strip().strip('"')
                elif line.startswith("description:"):
                    description = line[12:].strip().strip('"')
        if name:
            result[name] = {"name": name, "description": description or "", "path": str(skill_file)}
    return result


SKILLS: dict[str, dict] = _load_skills()


def append_skills(base_prompt: str, skill_names: list[str]) -> str:
    """Append skill availability notice to an existing prompt."""
    selected = [SKILLS[n] for n in skill_names if n in SKILLS]
    if not selected:
        return base_prompt
    skills_list = "\n".join(
        f"- **{s['name']}** ({s['path']}): {s['description']}" for s in selected
    )
    return (
        base_prompt
        + "\n\nYou have the following skills available:\n"
        + skills_list
        + "\n\nWhen you decide to use a skill, use the read_file tool to read the "
          "full contents of the skill file before using it."
    )


def build_system_prompt(skill_names: list[str] | None = None) -> str:
    """Build a system prompt, optionally including named skills."""
    selected = [SKILLS[n] for n in (skill_names or []) if n in SKILLS]
    if not selected:
        return CODER
    skills_list = "\n".join(
        f"- **{s['name']}** ({s['path']}): {s['description']}" for s in selected
    )
    return (
        CODER
        + "\n\nYou have the following skills available:\n"
        + skills_list
        + "\n\nWhen you decide to use a skill, use the read_file tool to read the "
        "full contents of the skill file before using it."
    )
