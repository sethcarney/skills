---
name: claude-permissions
category: sandbox
description: Write Claude Code permission rules and choose a permission mode — allow, ask, and deny rules for Bash, Read, Edit, WebFetch, MCP, and subagents, plus defaultMode, additionalDirectories, and the managed locks that stop developers widening policy. Covers the rule precedence, the two different path syntaxes, and where rules stop being an enforcement boundary. Use when locking down what Claude may run or read, blocking access to secrets, cutting permission prompts safely, or auditing a settings.json.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# Claude Code permissions

Permission rules decide which tool calls run and which prompt you first. They
apply to every tool — Bash, Read, Edit, WebFetch, MCP, subagents — and are
enforced by Claude Code before a tool runs, not by the model.

They pair with the [Bash sandbox](../bash-sandbox/SKILL.md), which enforces at
the OS level once a command is running. For picking an overall posture, start at
[`sandbox-claude-code`](../sandbox-claude-code/SKILL.md).

## When to use

- Blocking access to `.env`, keys, or credential directories
- Cutting permission prompts without turning safety off
- Deciding a `defaultMode` for a repo or a fleet
- Reviewing a `.claude/settings.json` someone else wrote
- Constraining which subagents or MCP tools are available

## Precedence, and the thing it implies

Rules evaluate **deny, then ask, then allow**. First match in that order wins.
Specificity does not break the tie.

That has one consequence worth internalizing: a broad deny rule cannot carry
exceptions. `Bash(aws *)` in deny blocks `Bash(aws s3 ls)` even with that exact
allow rule present. Same between ask and allow — a matching ask rule prompts even
when a narrower allow rule also matches. If you need exceptions, don't write the
broad deny; enumerate what you're blocking.

A bare tool name in deny (`Bash`, or the equivalent `Bash(*)`) removes the tool
from Claude's context entirely — it never sees it. A scoped rule like
`Bash(rm *)` leaves the tool available and blocks matching calls.
`EndConversation` is the exception: no deny rule can remove it while another tool
remains.

Rules live in `permissions.allow`, `permissions.ask`, and `permissions.deny`, and
**merge across every settings scope** rather than overriding. A user-level allow
rule widens a locked-down project. Only `allowManagedPermissionRulesOnly` in
managed settings stops that.

## Rule syntax

`Tool` or `Tool(specifier)`.

| Rule | Matches |
|---|---|
| `Bash` | Every Bash command |
| `Bash(npm run build)` | That exact command |
| `Bash(npm run *)` | Commands starting with `npm run ` |
| `Read(./.env)` | `.env` in the current directory |
| `WebFetch(domain:example.com)` | Fetches to that host |
| `mcp__github__get_*` | Those tools from the `github` MCP server |
| `Agent(Explore)` | The Explore subagent |
| `Cd(~/code/**)` | `/cd` targets under `~/code` |

Deny and ask rules can also match a top-level input parameter —
`Bash(run_in_background:true)`, `Agent(model:opus)`,
`Bash(dangerouslyDisableSandbox:true)`. One parameter per rule; `*` wildcards;
a parameter the model omits never matches. Fields a tool already canonicalizes
(`command`, `file_path`, `path`, `url`) are not matchable this way — a rule like
`Bash(command:rm *)` is ignored with a startup warning, because a compound
command would bypass it.

Deny and ask rules accept globs in the tool-name position too: `"mcp__*"` denies
every MCP tool. Allow rules only accept a glob after a literal `mcp__<server>__`
prefix — an unanchored allow glob like `"*"` is skipped with a warning.

### Two different path syntaxes

This is the most common source of rules that silently don't match.

**Permission rules** (`Read`, `Edit`, `Cd`) use gitignore syntax:

| Pattern | Anchors at |
|---|---|
| `//path` | Filesystem root |
| `~/path` | Home directory |
| `/path` | **The settings file's own source**, not the filesystem root |
| `path` or `./path` | Current directory |

**Sandbox `filesystem.*` paths** use standard conventions, where `/tmp/build` is
absolute. They are not interchangeable.

So `Read(/Users/alice/secrets)` in user settings blocks
`~/.claude/Users/alice/secrets` — nothing useful. Use `//Users/alice/secrets`.
A `/path` rule resolves against the project root in `.claude/settings.json`,
the original cwd in `.claude/settings.local.json`, and `~/.claude` in user
settings.

Matching depth also differs by rule type for single-segment directory patterns:

| Rule | `src/app.ts` | `vendor/pkg/src/lib.js` |
|---|---|---|
| `Edit(src/**)` as allow | yes | no |
| `Edit(src/**)` as deny or ask | yes | yes |
| `Edit(/src/**)` any type | yes | no |
| `Edit(**/src/**)` any type | yes | yes |

Deny rules casting wider than allow rules is deliberate — a deny should catch the
nested copy. Bare filenames follow gitignore semantics and match at any depth, so
`Read(.env)` and `Read(**/.env)` are the same rule.

Symlinks are checked on both the link and its target. Allow rules require both to
match; deny rules fire if either does. A symlink inside an allowed directory
pointing outside it still prompts.

### Read and Edit specifics

`Edit` rules cover every built-in file-editing tool. A `Read` deny rule also
blocks the Edit tool on the same path, including creating a file there
(v2.1.208+) — but Write and NotebookEdit aren't covered, so add an `Edit` deny
for paths nothing may change.

`Write(path)`, `NotebookEdit(path)`, and `Glob(path)` rules are accepted but
**never matched** by file permission checks. v2.1.210+ warns at startup for each
one. Use `Edit(...)` and `Read(...)` instead.

### Bash specifics

`*` matches any sequence including spaces, at any position. The space matters:
`Bash(ls *)` matches `ls -la` but not `lsof`; `Bash(ls*)` matches both. The `:*`
suffix is equivalent to a trailing ` *`, and is only recognized at the end.

Claude Code splits compound commands on `&&`, `||`, `;`, `|`, `|&`, `&`, and
newlines, and a rule must match each subcommand independently — so
`Bash(safe-cmd *)` does not authorize `safe-cmd && rm -rf .`.

It strips a fixed wrapper set before matching: `timeout`, `time`, `nice`,
`nohup`, `stdbuf`, `command`, `builtin`, zsh's `noglob`, and bare `xargs`. It
also strips leading assignments of known-safe environment variables for allow
rules; deny and ask rules match past any assignment.

**Environment runners are not stripped.** `direnv exec`, `devbox run`,
`mise exec`, `npx`, and `docker exec` execute their arguments, so
`Bash(devbox run *)` authorizes `devbox run rm -rf .`. Write
`Bash(devbox run npm test)` — one rule per inner command.

`watch`, `setsid`, `ionice`, `flock`, and `find` with `-exec`/`-delete` always
prompt and can't be covered by a prefix rule.

A built-in read-only set (`ls`, `cat`, `grep`, `find`, `wc`, `which`, `diff`,
`stat`, read-only `git`, and friends) runs without a prompt in every mode. It is
not configurable; add an `ask` or `deny` rule to require a prompt for one.

**Argument-constraining Bash rules are fragile.** `Bash(curl http://github.com/ *)`
misses `curl -X GET http://...`, `https://`, redirects, and `URL=... && curl $URL`.
For network control, deny `curl` and `wget` outright and use WebFetch domain
rules — or better, use the sandbox's `allowedDomains`, which the OS enforces.

### WebFetch

`WebFetch(domain:example.com)` matches that host.
`WebFetch(domain:*.example.com)` matches subdomains at any depth but not the
apex. Elsewhere in the pattern, `*` matches only between two dots, so
`example.*` matches `example.org` but not `example.evil.com`.

WebFetch allow rules also pre-allow domains for the Bash sandbox. And WebFetch
rules don't stop network access on their own — if Bash is allowed, `curl` reaches
anything.

## Permission modes

Set `permissions.defaultMode`, or pass `--permission-mode`.

| Mode | Behavior |
|---|---|
| `default` (alias `manual`) | Prompts on first use of each tool |
| `plan` | Reads and read-only commands only; no source edits |
| `acceptEdits` | Auto-accepts edits and common filesystem commands in the working directory |
| `auto` | Auto-approves with a classifier that checks actions against your request |
| `dontAsk` | Auto-denies anything not pre-approved |
| `bypassPermissions` | Skips prompts |

**`bypassPermissions` needs a container or VM.** It skips writes to `.git`,
`.claude`, `.vscode`, `.devcontainer`, and similar. What still prompts: explicit
ask rules, connector tools your org set to `ask`, MCP tools marked
`requiresUserInteraction`, and removals targeting `/` or your home directory —
including through `$(...)`, backticks, or `<(...)` as of v2.1.208. Protected-path
checks are skipped entirely. With no prompts to catch a mistake, the isolation
boundary is the only thing left; see
[`sandbox-claude-code`](../sandbox-claude-code/SKILL.md).

**`auto` mode** is the better answer for "fewer prompts". A classifier reviews
each action and blocks ones that escalate beyond the request, target unrecognized
infrastructure, or look driven by hostile content Claude read. It's a per-action
control, not a boundary, so pair it with isolation for unattended runs — but it
doesn't *require* one the way `bypassPermissions` does.

To take either off the table:

```json
{
  "permissions": {
    "disableBypassPermissionsMode": "disable",
    "disableAutoMode": "disable"
  }
}
```

Most useful in managed settings, where they can't be overridden.

## Starting configurations

### A repository worth checking in

```json
{
  "permissions": {
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Read(~/.ssh/**)",
      "Read(~/.aws/**)",
      "Bash(curl *)",
      "Bash(wget *)"
    ],
    "ask": [
      "Bash(git push *)",
      "Bash(gh pr merge *)"
    ],
    "allow": [
      "Bash(npm test *)",
      "Bash(npm run lint)",
      "Bash(git commit *)"
    ]
  }
}
```

Derive the allow list from the project's real scripts. Leaving it empty and
answering prompts beats guessing.

### Locked down, for managed settings

```json
{
  "permissions": {
    "disableBypassPermissionsMode": "disable",
    "ask": ["Bash"],
    "deny": ["WebSearch", "WebFetch"]
  },
  "allowManagedPermissionRulesOnly": true,
  "allowManagedHooksOnly": true,
  "strictKnownMarketplaces": []
}
```

`allowManagedPermissionRulesOnly` is a **top-level** key, not inside
`permissions`. Without it, array merging means any scope can add allow rules.

## Where rules stop being a boundary

- **Read and Edit deny rules cover Claude's file tools** and the file commands
  Claude Code recognizes in Bash — `cat`, `head`, `tail`, `sed`. They do **not**
  cover an arbitrary subprocess: a Python or Node script that opens the file
  itself sails past them. Only the [sandbox](../bash-sandbox/SKILL.md) blocks
  that, at the OS level.
- **CLAUDE.md is not enforcement.** It shapes what Claude tries. Rules decide
  what runs.
- **Prompts and rules don't constrain what leaves.** Both go to the model either
  way.

## Extending with hooks

PreToolUse hooks run before the permission prompt and can deny a call, force a
prompt, or skip one. They don't override rules: deny and ask rules are evaluated
regardless of what the hook returns. A hook exiting with code 2 blocks the call
before rules are evaluated, so it beats an allow rule.

That gives you the "allow everything except these" shape rules can't express:
put `"Bash"` in allow, and register a PreToolUse hook that rejects the specific
commands you care about.

## Working directories

Claude has access to the launch directory. Extend it with `--add-dir`, `/add-dir`,
or `permissions.additionalDirectories`.

One asymmetry: `--add-dir` and `/add-dir` load a few kinds of `.claude/`
configuration from the added directory, while `additionalDirectories` in a
settings file grants file access only and loads none of it.

## Auditing an existing config

```bash
claude doctor                    # reads settings without a trust prompt
```

In a session, `/permissions` lists every rule **and the settings file it came
from**, which is the fastest way to find the user-scope rule widening a project
you thought was locked down.

Startup warnings are worth reading rather than dismissing — they catch rules that
name an unknown tool, rules in an unmatched form like `Write(path)`, and
parameter rules on canonicalized fields. All three are rules that will never fire.

## Reference

- [Permissions](https://code.claude.com/docs/en/permissions)
- [Permission modes](https://code.claude.com/docs/en/permission-modes)
- [Settings](https://code.claude.com/docs/en/settings)
- [Hooks](https://code.claude.com/docs/en/hooks-guide)

Verified against Claude Code CLI **v2.1.220**.
