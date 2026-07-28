---
name: bash-sandbox
category: sandbox
description: Configure Claude Code's built-in sandboxed Bash tool — the OS-level filesystem and network boundary around every Bash command and its child processes, using Seatbelt on macOS and bubblewrap on Linux and WSL2. Covers the sandbox.* settings keys, per-scope restrictions, credential protection, dependency setup, and the tools that break under it. Use when enabling /sandbox, when sandboxed commands fail, when choosing allowedDomains, or when enforcing sandboxing through managed settings.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# The sandboxed Bash tool

The Bash sandbox lets Claude run most shell commands without stopping to ask.
Instead of approving each command, you declare which files and domains commands
may touch, and the operating system enforces that on every Bash command and every
process it spawns.

For choosing between this and a container or VM, start at
[`sandbox-claude-code`](../sandbox-claude-code/SKILL.md).

## When to use

- Turning on `/sandbox` for a project or for all projects
- A command works in your terminal but fails under Claude
- Deciding what belongs in `allowedDomains`, `allowWrite`, or `excludedCommands`
- Protecting credentials from commands Claude runs
- Rolling sandboxing out through managed settings

## What it does and does not cover

**Covers:** Bash commands and every child process they spawn — including
`npm`, `kubectl`, `terraform`, and any script they run.

**Does not cover:** Read, Edit, Write, WebFetch, and other in-process tools;
MCP servers; hooks. Those run on the host under
[permission rules](../claude-permissions/SKILL.md) instead. To put them behind an
OS boundary too, use the [sandbox runtime](../sandbox-runtime/SKILL.md), a
container, or a VM.

Subagents share the parent session's sandbox configuration, so their Bash
commands are sandboxed too.

Say this plainly when someone asks whether the sandbox makes an install safe. It
constrains one tool.

## Platform support and dependencies

| Platform | Mechanism | Setup |
|---|---|---|
| macOS | Seatbelt | Nothing to install |
| Linux | bubblewrap | `bubblewrap`, `socat` |
| WSL2 | bubblewrap | Same as Linux; WSL1 is not supported |
| Native Windows | — | Not supported; use WSL2 or a container |

```bash
sudo apt-get install bubblewrap socat     # Debian/Ubuntu
sudo dnf install bubblewrap socat         # Fedora
```

Ripgrep ships with the native binary. The seccomp filter is optional and is what
blocks Unix domain sockets; install it with
`npm install -g @anthropic-ai/sandbox-runtime` if the Dependencies tab says it's
missing.

The dependency check runs at **startup**, so restart Claude Code after installing
anything or `/sandbox` won't see it.

### Ubuntu 24.04 and later

The default AppArmor policy blocks the user namespaces bubblewrap needs.

```bash
sysctl kernel.apparmor_restrict_unprivileged_userns
```

`0` or "No such file or directory" means you're fine. `1` needs a profile:

```bash
sudo tee /etc/apparmor.d/bwrap > /dev/null <<'EOF'
abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
  include if exists <local/bwrap>
}
EOF
sudo systemctl reload apparmor
```

The profile applies to `bwrap` itself, not to what runs inside it.

## Turning it on

`/sandbox` in a session opens a panel with Mode, Overrides, and Config tabs, plus
Dependencies on Linux when something is missing. Selecting a mode there writes to
`.claude/settings.local.json` — this project only, not checked in.

For all your projects, set it in `~/.claude/settings.json`. For a repository, set
it in `.claude/settings.json`. For a fleet, use
[managed settings](#enforce-it-for-an-organization).

```json
{ "sandbox": { "enabled": true } }
```

### The two modes

**Auto-allow** (`autoAllowBashIfSandboxed`, default `true`): sandboxed commands
run without prompting, because the boundary contains them. Still enforced on top:

- Explicit deny rules
- `rm`/`rmdir` against `/`, your home directory, or other critical paths
- Content-scoped ask rules such as `Bash(git push *)`
- In plan mode, commands outside the built-in read-only set still prompt

A bare `Bash` ask rule (or `Bash(*)`) is skipped for commands that run sandboxed,
but still applies to ones that fall back — except in plan mode, where it prompts
for sandboxed commands too.

**Regular permissions** (`autoAllowBashIfSandboxed: false`): every Bash command
goes through the normal permission flow even when sandboxed. Same boundary, more
approvals.

Auto-allow is independent of the session's permission mode. That surprises
people: with auto-allow on, a sandboxed Bash command that modifies files inside
the boundary runs with no prompt even when the Edit tool would have asked.

### The escape hatch

When a command fails because of a sandbox restriction, Claude may retry it with
the `dangerouslyDisableSandbox` parameter, which runs it outside the sandbox and
through the normal permission flow — a prompt in default mode, the classifier in
auto mode.

To be prompted on every unsandboxed retry even in auto mode, add an ask rule for
`Bash(dangerouslyDisableSandbox:true)`. To remove the hatch entirely:

```json
{ "sandbox": { "allowUnsandboxedCommands": false } }
```

The `/sandbox` Overrides tab calls that **Strict sandbox mode**. With it off,
every command must run sandboxed or be listed in `excludedCommands`.

## The defaults

| Layer | Default |
|---|---|
| Write | Working directory and its subdirectories, plus the session temp directory |
| Read | The entire machine, minus denied paths — **including `~/.aws/credentials` and `~/.ssh`** |
| Network | No domains pre-allowed; the first command needing a new domain prompts |
| Settings files | `settings.json` at every scope is deny-write, so a command can't rewrite its own policy |

Two defaults catch people out. Reads are wide open by default — sandboxing does
not protect your credentials until you say so. And `$TMPDIR` points at the
session temp directory for sandboxed commands but at your shell's value for
unsandboxed ones, so the two see different temp directories; pass files through
the working directory instead.

In a linked git worktree, the sandbox also allows writes to the main repository's
shared `.git` directory so `git commit` works. `hooks/` and `config` inside it
stay denied.

## Settings reference

All keys nest under `sandbox`.

| Key | Default | Notes |
|---|---|---|
| `enabled` | `false` | macOS, Linux, WSL2 |
| `failIfUnavailable` | `false` | Error at startup instead of silently running unsandboxed |
| `autoAllowBashIfSandboxed` | `true` | Auto-approve sandboxed commands |
| `excludedCommands` | — | Commands that run outside the sandbox |
| `allowUnsandboxedCommands` | `true` | `false` kills the `dangerouslyDisableSandbox` hatch |
| `filesystem.allowWrite` | — | Extra writable paths; merges with `Edit(...)` allow rules |
| `filesystem.denyWrite` | — | Merges with `Edit(...)` deny rules |
| `filesystem.denyRead` | — | Merges with `Read(...)` deny rules |
| `filesystem.allowRead` | — | Re-open reads inside a `denyRead` region |
| `filesystem.disabled` | `false` | Drop the filesystem layer, keep network. **v2.1.216+**, user/managed/CLI only |
| `filesystem.allowManagedReadPathsOnly` | `false` | Managed settings only |
| `credentials.files` | — | `{ "path": ..., "mode": "deny" }`. **v2.1.187+** |
| `credentials.envVars` | — | `deny` or `mask`. **v2.1.187+**; `mask` needs **v2.1.199+** |
| `credentials.allowPlaintextInject` | `false` | `mask` over plain HTTP. Leave off |
| `network.allowedDomains` | — | Wildcards supported, e.g. `*.npmjs.org` |
| `network.deniedDomains` | — | Beats `allowedDomains`; merges from every scope regardless of locks |
| `network.strictAllowlist` | `false` | Deny instead of prompt. **v2.1.219+**, user/managed/CLI only |
| `network.allowManagedDomainsOnly` | `false` | Managed settings only |
| `network.allowAllUnixSockets` | `false` | The only way to permit Unix sockets on Linux/WSL2 |
| `network.allowUnixSockets` | — | macOS only; ignored on Linux and WSL2 |
| `network.allowLocalBinding` | `false` | Bind to localhost ports; macOS only |
| `network.allowMachLookup` | — | XPC/Mach service names; macOS only |
| `network.httpProxyPort` / `socksProxyPort` | — | Bring your own proxy |
| `network.tlsTerminate` | — | Experimental; required for `mask`. **v2.1.199+**, user/managed/CLI only |
| `enableWeakerNestedSandbox` | `false` | Unprivileged Docker, Linux/WSL2. **Reduces security** |
| `enableWeakerNetworkIsolation` | `false` | macOS TLS trust service. **Reduces security** |
| `allowAppleEvents` | `false` | macOS. **Removes code-execution isolation** |
| `bwrapPath` / `socatPath` | — | Managed settings only |

### Path prefixes

`filesystem.*` and `credentials.files` paths use standard conventions:

| Prefix | Resolves to |
|---|---|
| `/` | Absolute from filesystem root — `/tmp/build` is `/tmp/build` |
| `~/` | Home directory |
| `./` or bare | Project root in project settings, `~/.claude` in user settings |

**This is not the syntax permission rules use.** `Read`/`Edit` rules use `//path`
for absolute and `/path` for settings-source-relative. Writing `/tmp/build` in a
permission rule gets you a project-relative path; writing `//tmp/build` in a
sandbox filesystem path is the legacy form. Getting these backwards is the single
most common mistake in a hand-written config.

### Example

```json
{
  "sandbox": {
    "enabled": true,
    "excludedCommands": ["docker *"],
    "filesystem": {
      "allowWrite": ["/tmp/build", "~/.kube"],
      "denyRead": ["~/.aws/credentials"]
    },
    "network": {
      "allowedDomains": ["github.com", "*.npmjs.org"],
      "deniedDomains": ["uploads.github.com"]
    }
  }
}
```

Prefer `filesystem.allowWrite` over `excludedCommands` when a tool needs to write
somewhere specific. Widening one path keeps the tool inside the boundary;
excluding the command removes the boundary for it entirely.

## Protecting credentials

There is no built-in deny list. Only what you list is protected, and the default
read policy allows everything else.

```json
{
  "sandbox": {
    "enabled": true,
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

`deny` on a file blocks reads inside the sandbox; `deny` on an environment
variable unsets it before each sandboxed command. Files use `deny` only.

**`mask` keeps the tool working.** `deny` on `GH_TOKEN` breaks `gh`. `mask`
replaces the value with a per-session sentinel inside the sandbox, and the proxy
substitutes the real value on outbound requests to that entry's `injectHosts`:

```json
{
  "sandbox": {
    "enabled": true,
    "network": {
      "tlsTerminate": {},
      "allowedDomains": ["*.github.com", "registry.npmjs.org"]
    },
    "credentials": {
      "envVars": [
        { "name": "GH_TOKEN", "mode": "mask", "injectHosts": ["api.github.com"] },
        { "name": "NPM_TOKEN", "mode": "mask" }
      ]
    }
  }
}
```

`mask` requires `network.tlsTerminate` — without it, masking fails closed: the
command sees the sentinel, the sentinel reaches the server, authentication fails.
Claude Code reports the misconfiguration at startup. Every `injectHosts` entry
must also be covered by `allowedDomains`. An entry with no `injectHosts` is
substituted on every allowed domain, which is broader than most people intend.

Because `mask` authorizes the proxy to send your real credential somewhere, it is
honored only from user, managed, or `--settings` scope. `mask` entries,
`tlsTerminate`, and `allowPlaintextInject` in a repository's settings are ignored.
`deny` wins when the same variable appears with both modes.

To strip Anthropic and cloud credentials from **all** subprocesses regardless of
sandboxing, set `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`. It also forces filesystem
isolation to stay on, overriding `filesystem.disabled` from every source.

## Which scope can set what

| Scope | Can set |
|---|---|
| `.claude/settings.json`, `.claude/settings.local.json` | Everything except the keys below |
| User (`~/.claude/settings.json`), managed, `--settings` | `filesystem.disabled`, `network.strictAllowlist`, `network.tlsTerminate`, `allowAppleEvents`, `credentials` `mask` entries, `credentials.allowPlaintextInject` |
| Managed only | `filesystem.allowManagedReadPathsOnly`, `network.allowManagedDomainsOnly`, `bwrapPath`, `socatPath` |

A key set in a scope that doesn't honor it is **dropped without an error**. If a
setting appears to do nothing, check this table before debugging anything else.

Array keys — `allowWrite`, `denyRead`, `allowedDomains`, `excludedCommands`,
`credentials.*` — are concatenated and deduplicated across every scope, not
replaced. Boolean keys take the highest-priority scope's value.

## Turning the filesystem layer off

`filesystem.disabled: true` (v2.1.216+) keeps network isolation and drops
filesystem isolation. Use it when you sandbox to control where commands
*connect*, not what they write.

Understand what goes with it: `denyRead` and `credentials.files` stop applying,
because the filesystem layer is what enforces them; `$TMPDIR` is no longer
overridden; and `autoAllowBashIfSandboxed` still defaults to `true`, so commands
keep running without prompts. A sandboxed command can then write `~/.bashrc`, a
binary on `$PATH`, or `~/.claude/settings.json` and widen its own access on the
next run. `credentials.envVars` deny and mask entries still apply.

Only set it for workloads you trust not to escalate.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Host-not-allowed error | Approve when prompted, or pre-add to `allowedDomains` |
| `jest` hangs | `jest --no-watchman` — watchman is incompatible |
| `docker` fails | Incompatible; add `docker *` to `excludedCommands` |
| `gh`, `gcloud`, `terraform` fail TLS on macOS | Add to `excludedCommands`; or with a MITM proxy and custom CA, `enableWeakerNetworkIsolation: true` |
| `open`/`osascript` fail with `-600` on macOS | `allowAppleEvents: true` (removes code-execution isolation) or `excludedCommands` |
| bubblewrap won't start in a container | `enableWeakerNestedSandbox: true` — only when the container is already your boundary |
| Only a Dependencies tab in `/sandbox` | Install what it lists, restart Claude Code |
| `--dangerously-skip-permissions` fails as root | Run as a non-root user; the check is skipped inside a recognized sandbox |
| WSL2 can't run `cmd.exe` or `/mnt/c/...` | WSL hands those to Windows over a Unix socket, which the sandbox blocks; add to `excludedCommands` |

## Enforce it for an organization

Deliver `sandbox` keys through managed settings — an MDM-managed file or
server-managed settings on Claude.ai:

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false
  }
}
```

`failIfUnavailable` turns a missing bubblewrap into a startup failure instead of
a warning followed by unsandboxed execution. `allowUnsandboxedCommands: false`
removes the retry-outside path.

Add `credentials` entries for `~/.aws`, `~/.ssh`, and secret environment
variables, since the default read policy allows them. Add `excludedCommands` for
approved tools that genuinely can't be sandboxed, and keep that list short —
there is no managed-only lock for it, so developers can always append.

To stop developers widening the rest, set
`filesystem.allowManagedReadPathsOnly` and `network.allowManagedDomainsOnly`.
Without those, array merging means a user-scope entry widens your policy.

The sandbox doesn't run on native Windows. Scope this to macOS and Linux, or put
Windows users in WSL2 or a container.

## Security limitations

- **No TLS inspection by default.** The proxy decides from the client-supplied
  hostname. A broad entry like `github.com` is an exfiltration path, and domain
  fronting can reach hosts outside the allowlist. If your threat model needs
  more, run a custom proxy that terminates TLS and install its CA inside the
  sandbox. `network.tlsTerminate` exists for credential masking and does not add
  content filtering.
- **Unix sockets escalate.** Allowing `/var/run/docker.sock` effectively grants
  the host.
- **Write paths escalate.** Granting writes to a directory on `$PATH`, to system
  config, or to `~/.bashrc` buys code execution in another context.
- **`enableWeakerNestedSandbox` and `enableWeakerNetworkIsolation` are named
  honestly.** Only use them where something else is already the boundary.
- **Environment variables are inherited** by sandboxed commands unless you deny
  or mask them.

Both layers matter. Without network isolation a compromised agent exfiltrates;
without filesystem isolation it backdoors something to get network access. When
you widen one side, check the other side's restriction still holds.

## Reference

- [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [Settings: sandbox settings](https://code.claude.com/docs/en/settings#sandbox-settings)
- [`anthropics/claude-code` examples/settings](https://github.com/anthropics/claude-code/tree/main/examples/settings) — `settings-bash-sandbox.json` and `settings-strict.json`

Verified against Claude Code CLI **v2.1.220**. Keys carry version floors; check
`claude --version` before recommending one.
