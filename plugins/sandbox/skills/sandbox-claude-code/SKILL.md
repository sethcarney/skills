---
name: sandbox-claude-code
category: sandbox
description: Choose and apply an isolation posture for Claude Code in a repository, then verify it. Compares the built-in Bash sandbox, the sandbox runtime, dev containers, custom containers, and VMs against a threat model, and wires up the recommended default — dev container + Bash sandbox + permission rules. Use when setting up Claude Code on a new or untrusted repo, when asked to make an install "safe" or "sandboxed", before running unattended or with --dangerously-skip-permissions, or when auditing an existing setup.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# Sandbox Claude Code

Isolation limits what a session can read, write, and reach on the network. It
matters most when Claude runs with fewer prompts, runs unattended, or points at
code you don't fully trust.

This skill picks the boundary, applies it, and **verifies it** —
[`scripts/check-sandbox.py`](scripts/check-sandbox.py) is the part that makes the
result something you can trust rather than assume.

The three deeper skills are [`bash-sandbox`](../bash-sandbox/SKILL.md),
[`claude-permissions`](../claude-permissions/SKILL.md), and
[`sandbox-runtime`](../sandbox-runtime/SKILL.md). The container path is
[`dev-container`](../../../dev-container/skills/dev-container/SKILL.md), which
also covers installing Claude Code in the container and persisting its login.

## When to use

- Setting up Claude Code on a repository for the first time
- Asked to "sandbox Claude", "make this safe to run", or "isolate the agent"
- Before an unattended run, `--dangerously-skip-permissions`, or auto mode
- Auditing an existing setup — run the checker and report what it finds
- Reviewing a `.claude/settings.json` someone else wrote

## Say this out loud, once

No option here is a hard boundary against a determined attacker. Every approach
that allows any network egress can still leak whatever the agent can read, and
every approach that mounts the project writable can still modify that code.
Isolation reduces blast radius; it does not eliminate it. State that when you
report the result — do not tell the user their install is "safe", tell them what
it now contains and what it still doesn't.

Isolation also changes nothing about what leaves for the model. Prompts and file
contents go to the API with or without a sandbox.

## 1. Establish the threat model

Ask, don't assume. Two questions decide almost everything:

1. **Do you trust this repository's code and its dependencies?** Untrusted code
   means postinstall scripts, test suites, and build tooling that you are about
   to execute.
2. **Will you be watching?** Attended work with prompts is a different problem
   from an unattended run.

Then check what's available, because it prunes the options:

```bash
uname -s                                     # Darwin | Linux | MINGW/MSYS = native Windows
command -v docker && docker info >/dev/null 2>&1 && echo "docker usable"
command -v bwrap socat                       # Linux/WSL2 Bash sandbox dependencies
claude --version
```

Native Windows rules out the Bash sandbox and the sandbox runtime entirely —
that's a WSL2 or container conversation. No usable Docker rules out dev
containers.

## 2. Choose the boundary

| Goal | Approach | Covers |
|---|---|---|
| Fewer prompts on your own machine, trusted repo | [Bash sandbox](../bash-sandbox/SKILL.md) (`/sandbox`) | Bash commands and their children only |
| Same, plus MCP servers and hooks, no Docker | [Sandbox runtime](../sandbox-runtime/SKILL.md) | The whole Claude Code process |
| A standard environment for a team | [Dev container](../../../dev-container/skills/dev-container/SKILL.md) | Full dev environment |
| Unattended / `--dangerously-skip-permissions` | Dev container, custom container, or sandbox runtime | Full dev environment |
| Untrusted repository | A dedicated VM, or Claude Code on the web | Full OS |
| Existing container infrastructure or CI | Custom container image | Full dev environment |

**Scope is the thing people get wrong.** The Bash sandbox restricts Bash and its
child processes. Read, Edit, WebFetch, MCP servers, and hooks all run outside it,
on the host. Anything that must contain those has to wrap the whole process:
sandbox runtime, container, or VM.

### The recommended default

For a normal repository on a machine you control, apply all three layers:

1. **Dev container** — the outer boundary; puts file tools, MCP servers, and
   hooks inside it too, and lets you drop a default-deny egress firewall in.
2. **Bash sandbox inside it** — per-command OS-level restrictions, so a build
   script can't wander outside the workspace even though it runs in a container
   that trusts it.
3. **Permission rules** — deny reads of secrets, deny the network CLIs, allow the
   handful of commands you actually run.

They are complementary, not redundant. The container bounds the environment, the
sandbox bounds each command, and permission rules bound what Claude attempts. In
an unprivileged container the inner sandbox needs
`sandbox.enableWeakerNestedSandbox`; see [step 4](#4-nested-sandbox-in-a-container).

If Docker isn't available or isn't wanted, drop layer 1 and add the
[sandbox runtime](../sandbox-runtime/SKILL.md) in its place — it covers the same
in-process surface without Docker, at the cost of being a beta research preview.

## 3. Apply it

Work through the layers the user chose. Don't apply layers they didn't ask for
just because the stack above lists three.

### Layer 1 — container

Follow the [`dev-container`](../../../dev-container/skills/dev-container/SKILL.md)
skill. It handles the base image, the Claude Code feature, and the three settings
needed to keep the login across rebuilds. Its "Restrict network egress" section
covers the default-deny iptables firewall, which is what makes a container
defensible for unattended runs.

Two of its warnings matter here specifically:

- The workspace is bind-mounted from your host. A container does not stop Claude
  from rewriting your actual source tree.
- The config volume holds a live OAuth token that anything in the container can
  read. A container is not a reason to point Claude at a repo you distrust.

### Layer 2 — Bash sandbox

Full detail in [`bash-sandbox`](../bash-sandbox/SKILL.md). The minimum for a
project is `.claude/settings.json`:

```json
{
  "sandbox": {
    "enabled": true,
    "excludedCommands": ["docker *"],
    "network": {
      "allowedDomains": ["registry.npmjs.org", "github.com", "*.githubusercontent.com"]
    }
  }
}
```

Set `allowedDomains` from what the project's toolchain actually fetches — package
registry, VCS host, and nothing else. `docker` is incompatible with the sandbox,
so it needs `excludedCommands`; drop that entry if the project doesn't use it.

Add credential protection, since the sandbox's default read policy still allows
reading `~/.aws/credentials` and `~/.ssh`:

```json
{
  "sandbox": {
    "credentials": {
      "files": [
        { "path": "~/.aws/credentials", "mode": "deny" },
        { "path": "~/.ssh", "mode": "deny" }
      ],
      "envVars": [
        { "name": "GITHUB_TOKEN", "mode": "deny" },
        { "name": "NPM_TOKEN", "mode": "deny" }
      ]
    }
  }
}
```

`sandbox.credentials` requires Claude Code v2.1.187 or later. There is no
built-in credential deny list — only what you list is protected.

### Layer 3 — permission rules

Full detail in [`claude-permissions`](../claude-permissions/SKILL.md). The
repo-level starting point, in the same `.claude/settings.json`:

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
      "Bash(git push *)"
    ],
    "allow": [
      "Bash(npm test *)",
      "Bash(npm run *)"
    ]
  }
}
```

Deny beats ask beats allow, first match in that order, and specificity does not
break the tie. So a broad `Bash(curl *)` deny cannot carry an allowlist exception
— don't try to write one.

Adjust `allow` to the project's real commands. Leave it empty rather than guess:
an over-broad allow rule is worse than a prompt.

### 4. Nested sandbox in a container

Inside an unprivileged container, bubblewrap can't mount a fresh `/proc`, so the
inner Bash sandbox fails to start. Set:

```json
{ "sandbox": { "enableWeakerNestedSandbox": true } }
```

This exposes container process information to sandboxed commands that a fresh
`/proc` would hide. It is defensible **only** because the container is already
your boundary. Never set it on a bare host — there, it just weakens the sandbox
for nothing.

## 5. Verify

Do not report this as done from the config alone. Run the checker:

```bash
# Audits the resolved settings for this project
python3 scripts/check-sandbox.py

# Or point it at specific files, lowest precedence first
python3 scripts/check-sandbox.py ~/.claude/settings.json .claude/settings.json

# For an unattended or managed deployment
python3 scripts/check-sandbox.py --strict --require-devcontainer
```

Copy it into the repo and run it in CI so the posture can't silently drift. It
reports failures and warnings separately, exits 1 on any failure, and covers:

1. `sandbox.enabled` is not on
2. `sandbox.filesystem.disabled` turns the filesystem layer off
3. `network.allowAllUnixSockets`, which can hand over `/var/run/docker.sock` and
   with it the host
4. `excludedCommands` entries broad enough to exempt everything
5. `enableWeakerNestedSandbox` with no container config in the repo
6. `defaultMode: "bypassPermissions"` with no container config in the repo
7. Missing deny rules for common secret paths
8. Under `--strict`: `failIfUnavailable`, `allowUnsandboxedCommands: false`,
   `network.strictAllowlist`, and a non-empty `allowedDomains`
9. Keys placed in a scope that ignores them — project settings can't set
   `filesystem.disabled`, `network.strictAllowlist`, `network.tlsTerminate`,
   `allowAppleEvents`, or credential `mask` entries, and they are dropped with no
   error

The suite in [`tests/`](tests/) exercises it against a fixture per failure mode;
run `tests/run-tests.sh` after changing the checker.

Then verify at runtime, in the environment Claude will actually run in:

```bash
claude --version                # sandbox keys have version floors; see each skill
```

In a session, run `/sandbox` and read the Config tab: it shows the **resolved**
settings after merging every scope, which is the only reliable answer to "is this
actually on". If the panel shows only a Dependencies tab, a required package is
missing — install it, restart Claude Code, and look again.

Last, prove the boundary rather than trusting it. Ask Claude to run one command
that should fail:

```bash
touch ~/should-not-exist        # expect a sandbox denial, not a file
```

If that file appears, the sandbox is not on, whatever the config says.

## Failure modes that look like success

- **Warn-and-continue.** If the sandbox can't start — missing bubblewrap,
  unsupported platform — Claude Code prints a warning and runs commands
  unsandboxed. A scrolled-past warning reads exactly like a working sandbox. Set
  `sandbox.failIfUnavailable` to `true` to make it a startup error instead.
- **Silently ignored keys.** A key set in a scope that doesn't honor it is
  dropped without an error. `filesystem.disabled` in `.claude/settings.json` does
  nothing; the same key in `~/.claude/settings.json` works.
- **Arrays merge, they don't override.** `permissions.allow`,
  `excludedCommands`, `allowedDomains`, and `filesystem.*` concatenate across
  every scope. A user-level allow rule widens a project you thought was locked
  down. Only the managed `allowManaged*Only` locks stop that.
- **The escape hatch.** When a command fails under the sandbox, Claude may retry
  it with `dangerouslyDisableSandbox`, which runs it outside. In default mode
  that prompts; in auto mode the classifier decides. Set
  `allowUnsandboxedCommands: false` to remove it.
- **Broad allowed domains.** The proxy allows on the client-supplied hostname
  without inspecting TLS. A wide entry like `github.com` is an exfiltration path,
  and domain fronting can reach hosts outside the allowlist entirely.

## Enforcing it for other people

A repo's `.claude/settings.json` is a convention — anyone can edit it, and the
sandbox keys that matter most are the ones project settings can't set anyway.
Real enforcement is managed settings, read at the highest precedence from
`/etc/claude-code/managed-settings.json` on Linux and WSL,
`/Library/Application Support/ClaudeCode/` on macOS, or
`C:\Program Files\ClaudeCode\` on Windows — or delivered as server-managed
settings from Claude.ai.

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "network": { "allowManagedDomainsOnly": true },
    "filesystem": { "allowManagedReadPathsOnly": true }
  },
  "permissions": { "disableBypassPermissionsMode": "disable" },
  "allowManagedPermissionRulesOnly": true
}
```

Boolean keys take the managed value outright. Array keys still merge from every
scope, which is what the two `allowManaged*Only` locks exist to stop.
`excludedCommands` has no such lock — a developer can always append to it, so
keep the managed list narrow.

Note the sandbox doesn't run on native Windows, so a mixed fleet needs this
scoped to macOS and Linux, with Windows users in WSL2 or a container.

## Constraints

- Config only. Don't restructure the build, change toolchain versions, or add
  tooling nobody asked for.
- Merge into an existing `.claude/settings.json`; never replace it. Arrays are
  additive by design.
- Don't invent `allowedDomains` or `allow` entries. Derive them from the
  project's lockfiles, CI config, and scripts, or leave them out and let the
  first run prompt.
- `.claude/settings.local.json` is per-developer and not checked in — put shared
  policy in `.claude/settings.json`.
- Report what the checker actually returned, including warnings. If a layer was
  skipped, say which and why.

## Reference

| Page | Covers |
|---|---|
| [Sandbox environments](https://code.claude.com/docs/en/sandbox-environments) | Comparison of every isolation approach |
| [Sandboxing](https://code.claude.com/docs/en/sandboxing) | The built-in Bash sandbox |
| [Permissions](https://code.claude.com/docs/en/permissions) | Rule syntax and precedence |
| [Settings](https://code.claude.com/docs/en/settings#sandbox-settings) | Every `sandbox.*` key |
| [Security](https://code.claude.com/docs/en/security) | The full security model |
| [`anthropics/claude-code` examples/settings](https://github.com/anthropics/claude-code/tree/main/examples/settings) | Starter `settings-strict.json` and `settings-bash-sandbox.json` |

Behavior in this skill was verified against Claude Code CLI **v2.1.220**. Several
keys have version floors — v2.1.187 for `credentials`, v2.1.199 for `mask` and
`tlsTerminate`, v2.1.216 for `filesystem.disabled`, v2.1.219 for
`network.strictAllowlist`. Check `claude --version` before recommending them.
