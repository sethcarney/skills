# Skills

Custom agentic coding skills for Claude Code, Cursor, Windsurf, Copilot, and friends.

Install them with **[mdm](https://github.com/sethcarney/mdm)**: one command installs a skill
into every agent you use, in the format each one expects. No per-agent copying, no
hand-maintaining four parallel skills directories that drift apart.

## Install

```bash
# One skill, into your configured agents
mdm skills add sethcarney/skills --full-depth --skill go-report-card

# Everything
mdm skills add sethcarney/skills --full-depth --all

# Pick the agents explicitly
mdm skills add sethcarney/skills --full-depth --skill gh-issue -a claude-code cursor
```

Agent names: `claude-code`, `cursor`, `windsurf`, `cline`, `roo`, `github-copilot`,
`gemini-cli`, `codex`, `opencode`.

**Set your agents once** and every later install targets them by default, so you can drop `-a`:

```bash
mdm agents add claude-code cursor
```

### Flags worth knowing

| Flag | Why |
|------|-----|
| `--full-depth` | **Required for this repo.** Skills live at `plugins/<plugin>/skills/<skill>/SKILL.md`; this tells mdm to search subdirectories for `SKILL.md` instead of only the top level. Without it nothing is found. |
| `--list`, `-l` | Show what's in the repo without installing anything. |
| `--all` | Shorthand for `--skill '*' --agent '*' -y` — every skill, every agent, no prompts. |
| `--global`, `-g` | Install to `~/.agents/skills/` instead of the current project. |

Browse before committing to anything:

```bash
mdm skills add sethcarney/skills --full-depth --list
```

On install, mdm scans every markdown file for hidden Unicode characters and runs a security
audit before anything lands in your agent's skills directory — worth having when the skills
you're installing are instructions an agent will follow. Installs are recorded in
`skills-lock.json` so they're reproducible.

### Claude Code marketplace (alternative)

```
/plugin marketplace add sethcarney/skills
/plugin install go-report-card@sethcarney-skills
```

Works fine, but it's Claude Code only — the other agents on your machine won't see these skills.

## Plugin Catalog

| Plugin | Skills | Description |
|--------|--------|-------------|
| [go-report-card](plugins/go-report-card/) | [go-report-card](plugins/go-report-card/skills/go-report-card/SKILL.md) | Run Go quality checks — tests, vuln scan, cyclomatic complexity, and formatting |
| [godot](plugins/godot/) | [godot-cli](plugins/godot/skills/godot-cli/SKILL.md) | Godot 4.6 CLI build verification and headless validation |
| [github-pm](plugins/github-pm/) | [gh-issue](plugins/github-pm/skills/gh-issue/SKILL.md), [gh-project-scope](plugins/github-pm/skills/gh-project-scope/SKILL.md) | Create well-structured GitHub issues with acceptance criteria and scope a project into milestones via the GitHub CLI |
| [dependabot](plugins/dependabot/) | [dependabot-groups](plugins/dependabot/skills/dependabot-groups/SKILL.md) | Group dependencies that must be upgraded together into a single Dependabot PR and cut PR noise |
| [dev-container](plugins/dev-container/) | [dev-container](plugins/dev-container/skills/dev-container/SKILL.md) | Wrap the dev environment in a dev container, run Claude Code inside it, and persist auth across rebuilds |

Copy-paste, one line per skill (`--skill` repeats, so grab several at once):

```bash
mdm skills add sethcarney/skills --full-depth -s go-report-card
mdm skills add sethcarney/skills --full-depth -s godot-cli
mdm skills add sethcarney/skills --full-depth -s gh-issue -s gh-project-scope
mdm skills add sethcarney/skills --full-depth -s dependabot-groups
mdm skills add sethcarney/skills --full-depth -s dev-container
```

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
3. Test it locally before opening a PR:

   ```bash
   # Confirm mdm discovers your skill and reads its frontmatter
   mdm skills add . --full-depth --list

   # Install straight from your working copy and try it for real
   mdm skills add ./plugins/<plugin>/skills/<your-skill> -a claude-code
   ```

   If your skill doesn't show up in `--list`, the frontmatter is malformed or the
   directory is nested somewhere `SKILL.md` discovery won't reach.

4. Open a PR

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
  dev-container/
    skills/
      dev-container/
        SKILL.md                  # Dev container setup with Claude Code + persistent auth
        scripts/                  # check-devcontainer-auth.py regression guard
        tests/                    # Fixtures + runner for the guard
.github/workflows/                 # CI: runs the dev-container guard suite
.claude/skills/                    # Active copies for local dev
```
