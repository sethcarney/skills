---
name: sandbox-runtime
category: sandbox
description: Wrap the entire Claude Code process in OS-level filesystem and network isolation with @anthropic-ai/sandbox-runtime (srt), so MCP servers, hooks, and built-in file tools are constrained too — not just Bash — without needing Docker. Covers ~/.srt-settings.json configuration, the deny-by-default network model, the paths Claude Code needs allowed to start at all, and platform dependencies. Use when isolating more than Bash without a container, sandboxing a standalone MCP server, or preparing an unattended run on a machine with no Docker.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# Sandbox runtime (srt)

[`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime)
wraps an arbitrary process in the same Seatbelt and bubblewrap isolation the
built-in Bash sandbox uses. Run Claude Code through it and **every** tool, hook,
and MCP server in the session is inside the boundary — not just Bash.

It is the answer to "I want more than the Bash sandbox but I don't have Docker".

> It is a **beta research preview**. APIs and the configuration format may
> change. Say that when you recommend it; a container is the more stable choice
> when Docker is available.

For choosing between this and the alternatives, start at
[`sandbox-claude-code`](../sandbox-claude-code/SKILL.md).

## When to use

- Isolating MCP servers and hooks, not just Bash, without Docker
- Preparing an unattended run on a machine with no container runtime
- Sandboxing a standalone MCP server or a single risky command
- The [Bash sandbox](../bash-sandbox/SKILL.md) is in place but the gap in its
  coverage — in-process tools, hooks, MCP — is the actual concern

## What it changes versus the Bash sandbox

| | Bash sandbox | Sandbox runtime |
|---|---|---|
| Scope | Bash commands and children | The whole Claude Code process |
| Covers MCP servers, hooks | No | Yes |
| Covers Read, Edit, WebFetch | No | Yes |
| Configured in | `settings.json` | `~/.srt-settings.json` |
| Default write | Working directory | **Nothing** |
| Default read | Everywhere | Everywhere, minus `denyRead` |
| Default network | Prompts per domain | **Denied** |
| Stability | Shipped | Beta research preview |

The two are not mutually exclusive — you can leave the Bash sandbox on inside
srt. But srt's boundary is the outer one, and it is stricter by default.

## Install and dependencies

```bash
npm install -g @anthropic-ai/sandbox-runtime
```

| Platform | Mechanism | Needs |
|---|---|---|
| macOS | `sandbox-exec` | `ripgrep` (`brew install ripgrep`) |
| Linux | bubblewrap | `bubblewrap`, `socat`, `ripgrep` |
| Windows | bundled `srt-win.exe` | **Alpha.** One-time elevated `npx @anthropic-ai/sandbox-runtime windows-install` |

```bash
sudo apt-get install bubblewrap socat ripgrep     # Debian/Ubuntu
sudo dnf install bubblewrap socat ripgrep         # Fedora
```

On Ubuntu 24.04+, `kernel.apparmor_restrict_unprivileged_userns` strips
capabilities from the user namespaces bubblewrap needs. Prefer the scoped
AppArmor profile from the [`bash-sandbox`](../bash-sandbox/SKILL.md) skill over
`sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`, which relaxes the
restriction for everything on the machine, not just `bwrap`.

Installing the package also supplies the seccomp filter the built-in Bash sandbox
uses for Unix socket blocking — so this install fixes that separate gap too.

## Configure before you launch

**srt denies all writes and all network access by default.** Launch Claude Code
through it with no configuration and it won't start: it can't write its own
session files or reach the API.

Configuration lives at `~/.srt-settings.json`, or a path passed with
`--settings`.

```json
{
  "network": {
    "allowedDomains": [
      "api.anthropic.com",
      "statsig.anthropic.com",
      "github.com",
      "*.github.com",
      "registry.npmjs.org"
    ],
    "deniedDomains": [],
    "allowLocalBinding": false
  },
  "filesystem": {
    "denyRead": ["~/.ssh", "~/.aws"],
    "allowWrite": [".", "~/.claude", "~/.claude.json", "/tmp"],
    "denyWrite": [".env"]
  }
}
```

The four `allowWrite` entries are the minimum for Claude Code itself:

| Path | Why |
|---|---|
| `.` | The project you're working in |
| `~/.claude` | Settings, sessions, history, projects |
| `~/.claude.json` | The OAuth session and app state — a separate file, not inside the directory |
| `/tmp` | Runtime files |

Missing `~/.claude.json` is the one people hit: it sits *beside* `~/.claude`, not
inside it, so allowing the directory alone isn't enough. (Same split that bites
dev container setups — see the
[`dev-container`](../../../dev-container/skills/dev-container/SKILL.md) skill.)

If you use a third-party provider — Bedrock, Vertex, Foundry — allow its endpoint
instead of, or alongside, `api.anthropic.com`.

## Launch

```bash
npx @anthropic-ai/sandbox-runtime claude
```

Or with the global install:

```bash
srt claude
srt --settings ./ci-srt-settings.json claude -p "run the test suite"
```

The same wrapper sandboxes anything else — a standalone MCP server, a single
command:

```bash
srt "npm install"
srt --settings /path/to/srt-settings.json "jest --no-watchman"
```

For MCP servers, wrap the server's command in its `.mcp.json` entry rather than
wrapping Claude Code, when you want the server constrained more tightly than the
session around it.

## The two filesystem models, which are opposites

This trips people up, so read it twice:

- **Write is allow-only.** Everything is denied; `allowWrite` opens paths;
  `denyWrite` takes precedence over `allowWrite`.
- **Read is deny-then-allow.** Everything is allowed; `denyRead` closes regions;
  `allowRead` takes precedence over `denyRead` and re-opens paths inside them.

So `denyWrite` beats `allowWrite`, but `allowRead` beats `denyRead`. To get a
workspace-only read policy, deny the home tree and re-allow the project:

```json
{
  "filesystem": {
    "denyRead": ["/home"],
    "allowRead": ["."]
  }
}
```

Use `/Users` on macOS. System paths like `/usr` and `/lib` stay readable either
way.

**Glob support is macOS-only.** macOS accepts gitignore-style patterns —
`src/**/*.ts`, `file[0-9].txt`. Linux takes literal paths only. A config with
globs works on a Mac and silently under-matches on Linux, which is a bad way to
find out. Absolute or cwd-relative paths both work, and `~` expands, on every
platform.

## Network

Allow-only. An empty `allowedDomains` means no network at all.

- Wildcards: `*.example.com`
- Optional port suffix: `api.example.com:443` restricts to that port; no suffix
  matches any port
- `deniedDomains` is checked first and wins; a bare `*` is accepted for deny-all
- `allowLocalBinding` (default `false`) controls binding local ports — turn it on
  for a dev server

`network.tlsTerminate` (experimental) terminates HTTPS in-process so srt can
filter decrypted requests, pointing the sandboxed process at a trust bundle
containing the MITM CA plus the host's roots. `excludeDomains` tunnels named
hosts opaquely instead — needed for mTLS upstreams and certificate-pinning
clients, which TLS termination fundamentally breaks.

## Unix sockets

Blocked by default on both platforms.

| Setting | macOS | Linux |
|---|---|---|
| `allowUnixSockets: string[]` | Allowlist of paths | **Ignored** — seccomp can't filter by path |
| `allowAllUnixSockets: boolean` | Allow all | Disables seccomp blocking entirely |

On Linux the only lever is all-or-nothing. If seccomp isn't available (non-x64,
non-arm64 without `gcc` and `libseccomp-dev`), sockets are unrestricted and srt
prints a warning — read it rather than scrolling past.

Allowing `/var/run/docker.sock` hands over the host. It is not a socket like the
others.

## The weakening switches

Same three as the built-in sandbox, same honest names:

- `enableWeakerNestedSandbox` — for Docker environments without privileged
  namespaces. Only where the container is already your boundary.
- `enableWeakerNetworkIsolation` — macOS only; opens `com.apple.trustd.agent` so
  Go tools (`gh`, `gcloud`, `terraform`) verify TLS through a MITM proxy. Opens
  an exfiltration path.
- `allowAppleEvents` — macOS only; needed for `open` and `osascript`, which
  otherwise fail with `-600`. **Removes code-execution isolation**: a sandboxed
  command can launch applications that run entirely outside the boundary.

The upstream README is explicit that `allowAppleEvents` should only come from
trusted user-level config, never from a file in a checked-out repository — an
attacker-authored project could otherwise elevate its own sandbox permissions.
That applies to the other two as well.

## Verifying

Prove the boundary before trusting it:

```bash
srt "cat ~/.ssh/id_rsa"      # expect: Operation not permitted
srt "curl example.com"       # expect: Connection blocked by network allowlist
srt "curl api.anthropic.com" # expect: a response
```

Then start a real session and confirm it comes up, an MCP server connects, and a
build runs. Failures here are loud rather than silent — srt fails closed, which
is the opposite of the built-in sandbox's warn-and-continue.

On macOS, srt can tap the system sandbox violation log store for real-time
alerts, and `ignoreViolations` filters known-noisy paths per command pattern.

## Known friction

| Symptom | Fix |
|---|---|
| Claude Code won't start | `~/.claude.json` missing from `allowWrite` — it's beside `~/.claude`, not inside |
| API calls fail | `api.anthropic.com` (or your provider's endpoint) not in `allowedDomains` |
| `jest` violations | `jest --no-watchman` |
| Globs match on macOS, not Linux | Linux has no glob support; use literal paths |
| Unix socket warning on Linux | seccomp unavailable for the architecture; install `gcc` and `libseccomp-dev` |
| `open`/`osascript` fail with `-600` | `allowAppleEvents`, understanding what it gives up |

## Constraints

- Don't put `allowAppleEvents`, `enableWeakerNestedSandbox`, or
  `enableWeakerNetworkIsolation` in a repo-local settings file.
- Derive `allowedDomains` from the project's real dependencies. An overly broad
  entry is an exfiltration path; the proxy allows on hostname.
- Call the beta status out when recommending this over a container.
- Keep `~/.srt-settings.json` out of version control if it names host paths, and
  ship a project-specific file passed with `--settings` instead.

## Reference

- [`anthropic-experimental/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime) — the full configuration schema
- [Sandbox environments](https://code.claude.com/docs/en/sandbox-environments#sandbox-runtime)
- [Sandboxing](https://code.claude.com/docs/en/sandboxing) — the built-in Bash sandbox built on the same primitives
