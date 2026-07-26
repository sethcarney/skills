# Skills

A collection of custom agentic coding skills installable via [mdm](https://github.com/sethcarney/mdm).

## Install

```bash
# Install a specific skill for your configured agents
mdm skills add sethcarney/skills --full-depth --skill go-report-card

# Install all skills
mdm skills add sethcarney/skills --full-depth --all

# Target specific agents
mdm skills add sethcarney/skills --full-depth --skill gh-issue -a claude-code cursor
```

`mdm` handles placing skills in the right format for each agent (Claude Code, Cursor, Copilot, Windsurf, etc.).

### Claude Code marketplace (alternative)

```
/plugin marketplace add sethcarney/skills
/plugin install go-report-card@sethcarney-skills
```

## Plugin Catalog

| Plugin | Skills | Description |
|--------|--------|-------------|
| [go-report-card](plugins/go-report-card/) | [go-report-card](plugins/go-report-card/skills/go-report-card/SKILL.md) | Run Go quality checks — tests, vuln scan, cyclomatic complexity, and formatting |
| [godot](plugins/godot/) | [godot-cli](plugins/godot/skills/godot-cli/SKILL.md) | Godot 4.6 CLI build verification and headless validation |
| [github-pm](plugins/github-pm/) | [gh-issue](plugins/github-pm/skills/gh-issue/SKILL.md), [gh-project-scope](plugins/github-pm/skills/gh-project-scope/SKILL.md) | Create well-structured GitHub issues with acceptance criteria and scope a project into milestones via the GitHub CLI |
| [dependabot](plugins/dependabot/) | [dependabot-groups](plugins/dependabot/skills/dependabot-groups/SKILL.md) | Group dependencies that must be upgraded together into a single Dependabot PR and cut PR noise |

## How Skills Work

Each skill is a `SKILL.md` file with YAML frontmatter and a markdown body containing instructions for the AI assistant:

```yaml
---
name: skill-name
description: What this skill does and when to use it.
user-invocable: true
allowed-tools: Bash, Read
---
```

| Field | Purpose |
|-------|---------|
| `name` | Unique identifier (lowercase, hyphens) |
| `description` | When and how the AI should use this skill |
| `user-invocable` | Whether users can invoke it as a slash command |
| `allowed-tools` | Which tools the skill can use |

The markdown body contains the actual instructions — workflows, reference tables, code patterns, debugging steps. Only the frontmatter loads at startup; the body loads on demand.

## Contributing

1. To add a skill to an existing plugin, create `plugins/<plugin>/skills/<your-skill>/SKILL.md`
2. To add a new plugin, create `plugins/<your-plugin>/skills/` and add an entry to `.claude-plugin/marketplace.json`
3. Open a PR

Guidelines:
- Keep skill names lowercase with hyphens
- Write a description that explains both *what* the skill does and *when* to use it
- Keep `SKILL.md` under 500 lines — move detailed reference to separate files in the same directory
- Include real examples and concrete gotchas, not just theory

## Repo Structure

```
.claude-plugin/
  marketplace.json                 # Claude Code marketplace manifest
plugins/
  go-report-card/
    skills/
      go-report-card/SKILL.md     # Go quality checks (tests, vuln, complexity, fmt)
  godot/
    skills/
      godot-cli/SKILL.md          # CLI build verification
  github-pm/
    skills/
      gh-issue/SKILL.md           # Structured issue creation with acceptance criteria
      gh-project-scope/SKILL.md   # Project decomposition into milestones and issues
  dependabot/
    skills/
      dependabot-groups/SKILL.md  # Group must-match dependencies into one Dependabot PR
.claude/skills/                    # Active copies for local dev
```
