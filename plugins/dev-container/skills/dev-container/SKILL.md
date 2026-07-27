---
name: dev-container
category: dev-container
description: Wrap a project's development environment in a dev container and run Claude Code inside it, with authentication and settings persisted across container rebuilds via a named volume on ~/.claude. Use when setting up .devcontainer/devcontainer.json, when engineers have to re-authenticate Claude Code after every rebuild, when standardizing a toolchain across a team, or when asked to containerize local development.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write
---

# Dev containers with Claude Code

A [dev container](https://containers.dev/) defines one isolated environment every
engineer on the team runs identically. With Claude Code installed inside it,
commands Claude runs execute in the container rather than on the host, while file
edits land in the local repository through the bind-mounted workspace.

The default setup has one sharp edge: the container's home directory is discarded
on rebuild, so Claude Code authentication is lost every time. Fixing that is a
one-line volume mount, and it is the main reason this skill exists.

## When to use

- Setting up `.devcontainer/` for a repo that doesn't have one
- Adding Claude Code to a dev container that already exists
- Engineers report having to sign in to Claude Code after every rebuild
- Standardizing toolchain versions across a team
- Asked to containerize or isolate the development environment

## Scope check first

Dev containers require an editor that supports the Dev Containers spec — VS Code,
GitHub Codespaces, a JetBrains IDE, or Cursor. Plain Vim, Emacs, or a bare
terminal workflow are **not** part of this setup. Confirm the user's editor before
building anything; if it isn't supported, say so rather than producing config they
can't open.

## Instructions

### 1. Survey what already exists

```bash
ls -la .devcontainer/ 2>/dev/null       # existing config?
cat .devcontainer/devcontainer.json 2>/dev/null
ls Dockerfile docker-compose.yml 2>/dev/null
```

If `devcontainer.json` already exists, **add to it** — do not replace it. The
`features` block and the `mounts` array are additive.

Identify the toolchain to pick a base image:

```bash
ls package.json go.mod pyproject.toml requirements.txt Cargo.toml pom.xml 2>/dev/null
```

| Project | Image | Default `remoteUser` home |
|---|---|---|
| Node / TypeScript | `mcr.microsoft.com/devcontainers/typescript-node` | `/home/node` |
| Python | `mcr.microsoft.com/devcontainers/python` | `/home/vscode` |
| Go | `mcr.microsoft.com/devcontainers/go` | `/home/vscode` |
| Rust | `mcr.microsoft.com/devcontainers/rust` | `/home/vscode` |
| Java | `mcr.microsoft.com/devcontainers/java` | `/home/vscode` |
| Anything else | `mcr.microsoft.com/devcontainers/base:ubuntu` | `/home/vscode` |

The home directory column matters for step 3 — get it wrong and the volume mount
silently does nothing. Verify it rather than trusting the table: see step 5.

### 2. Install Claude Code through the feature

Claude Code installs into any dev container through the
[Claude Code Dev Container Feature](https://github.com/anthropics/devcontainer-features/tree/main/src/claude-code):

```json
{
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "features": {
    "ghcr.io/anthropics/devcontainer-features/claude-code:1.0": {}
  }
}
```

Replace `image` with the project's base image, or drop it entirely if the config
uses `build.dockerfile`.

The `:1.0` tag pins **the feature's install script, not the Claude Code release**.
The feature always installs the latest Claude Code, which then auto-updates itself
inside the container. To pin the CLI, see [Pin the CLI version](#pin-the-cli-version).

In VS Code and Codespaces the feature also adds the Claude Code VS Code extension;
other editors ignore that part.

### 3. Persist authentication across rebuilds

This is the step that stops the re-authentication loop. Claude Code stores its
auth token, user settings, and session history under `~/.claude`. Mount a named
volume there:

```json
"mounts": [
  "source=claude-code-config-${devcontainerId},target=/home/node/.claude,type=volume"
]
```

Two things to get right:

- **`target` must be the home directory of the container's `remoteUser`.** Replace
  `/home/node` with whatever that user's home actually is. A wrong path mounts an
  empty volume somewhere harmless and auth still resets on every rebuild — it
  fails silently, with no error.
- **`${devcontainerId}`** scopes the volume to this project. Without it, one
  shared volume is reused across every repository on the machine. The
  [reference configuration](https://github.com/anthropics/claude-code/blob/main/.devcontainer/devcontainer.json)
  uses `claude-code-config-${devcontainerId}` for exactly this reason. Drop it only
  if the user explicitly wants one sign-in shared across all their repos.

If you mount the volume somewhere other than `~/.claude`, set `CLAUDE_CONFIG_DIR`
to the mount path so Claude Code reads and writes there.

A complete minimal config:

```json
{
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
  "features": {
    "ghcr.io/anthropics/devcontainer-features/claude-code:1.0": {}
  },
  "mounts": [
    "source=claude-code-config-${devcontainerId},target=/home/vscode/.claude,type=volume"
  ],
  "remoteUser": "vscode"
}
```

### 4. Handle the auth path for the user's provider

What the sign-in prompt does depends on the provider:

| Provider | Behavior |
|---|---|
| Anthropic | Browser sign-in with a Claude or Anthropic Console account |
| Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry | Uses cloud provider credentials, no browser prompt |

For cloud providers, pass credentials in as **environment variables** via
`containerEnv`, a Codespaces secret, or workload identity:

```json
"containerEnv": {
  "AWS_REGION": "us-east-1"
}
```

Do **not** mount host credential files to solve this. See [Security](#security).

**GitHub Codespaces.** `~/.claude` survives stopping and starting a codespace, but
is still cleared on rebuild — so the volume mount in step 3 applies there too. To
carry authentication across *different* codespaces, store `ANTHROPIC_API_KEY`, or a
`CLAUDE_CODE_OAUTH_TOKEN` generated by `claude setup-token`, as a
[Codespaces secret](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces).
Codespaces exposes secrets as environment variables automatically.

### 5. Rebuild and verify

Rebuild: VS Code Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) →
**Dev Containers: Rebuild Container**. For other tools use that tool's rebuild
action, or the [Dev Containers CLI](https://github.com/devcontainers/cli).

Then, in a terminal **inside the container**:

```bash
echo $HOME                # must match the target path from step 3
whoami                    # must NOT be root
ls -la ~/.claude          # the mounted volume
claude                    # sign in
```

If `$HOME` doesn't match the mount target, fix `target` and rebuild — this is the
single most common failure.

Confirm persistence properly: rebuild the container a second time and run `claude`
again. It should start without an auth prompt. Do not report this as working
without that second rebuild — the first run proves nothing.

**Callback gotcha.** If browser sign-in completes but never returns to the
container, copy the code from the browser and paste it at the
`Paste code here if prompted` prompt. This happens when the editor's port
forwarding doesn't route the localhost callback.

## Optional hardening

Each of these is independent — apply only what the user asks for.

### Enforce organization policy

Claude Code reads `/etc/claude-code/managed-settings.json` on Linux at the highest
precedence in the settings hierarchy, overriding anything in `~/.claude` or the
project's `.claude/`. Install it from the Dockerfile:

```dockerfile
RUN mkdir -p /etc/claude-code
COPY managed-settings.json /etc/claude-code/managed-settings.json
```

Be honest about the limits when recommending this: the Dockerfile lives in the
repository, so anyone with write access can edit or delete that step. For policy
engineers cannot bypass, it has to be delivered through server-managed settings or
MDM instead.

### Pin the CLI version

The feature always installs the latest release. For reproducible builds, skip the
feature and install from the Dockerfile, then disable the auto-updater:

```dockerfile
RUN npm install -g @anthropic-ai/claude-code@X.Y.Z
```

```json
"containerEnv": {
  "DISABLE_AUTOUPDATER": "1",
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
}
```

`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` opts out of telemetry and error
reporting; include it only if that's wanted.

### MCP servers

Define them at project scope in a `.mcp.json` at the repository root so they're
checked in beside the dev container config. Install any binaries local stdio
servers depend on in the Dockerfile, and add remote server domains to the network
allowlist if a firewall is in use.

### Restrict network egress

The reference container's
[`init-firewall.sh`](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh)
blocks all outbound traffic except allowed domains. Running a firewall inside a
container needs extra capabilities:

```json
"runArgs": ["--cap-add=NET_ADMIN", "--cap-add=NET_RAW"]
```

Neither the script nor these capabilities are required for Claude Code itself —
leave them out if the user relies on their own network controls.

### Run without permission prompts

Because the container runs as a non-root user and confines execution,
`--dangerously-skip-permissions` is a defensible option for unattended work. The
CLI **rejects this flag when launched as root**, so `remoteUser` must be a
non-root account.

State the tradeoff plainly when suggesting it: skipping prompts removes the chance
to review tool calls, and Claude can still modify any file in the bind-mounted
workspace — which is your host filesystem — and reach anything the network policy
allows. Pair it with egress restrictions. If the user wants fewer prompts without
disabling safety checks, point them at auto mode instead. To block the flag
entirely, set `permissions.disableBypassPermissionsMode` to `"disable"` in managed
settings.

## Security

- **Never mount host secrets into the container** — not `~/.ssh`, not cloud
  credential files. Prefer repository-scoped or short-lived tokens, and pass cloud
  credentials as environment variables.
- A dev container provides substantial protection but is not immune to everything.
  Under `--dangerously-skip-permissions` it does not prevent a malicious project
  from exfiltrating anything reachable inside the container — **including the
  Claude Code credentials in the `~/.claude` volume this skill sets up**.
- Use dev containers with trusted repositories, and monitor what Claude does.

## Constraints

- Config only. Don't restructure the project's build, change toolchain versions, or
  add unrequested tooling to the Dockerfile.
- Never replace an existing `devcontainer.json` — merge into it.
- Validate the JSON before finishing. `devcontainer.json` permits `//` comments
  (JSONC), so a plain `json.load` may report a false failure on a hand-written
  file; check that any parse error is real before "fixing" it.
- The firewall, managed settings, and bypass-permissions sections are opt-in. Don't
  apply them because they look thorough.

## Reference

The [`anthropics/claude-code`](https://github.com/anthropics/claude-code/tree/main/.devcontainer)
repo has a working example combining the CLI, egress firewall, persistent volumes,
and a Zsh shell. It's a demonstration, not a maintained base image — read it to see
how the pieces fit, then adapt.

| File | Purpose |
|---|---|
| `devcontainer.json` | Volume mounts, `runArgs` capabilities, extensions, `containerEnv` |
| `Dockerfile` | Base image, dev tools, Claude Code install |
| `init-firewall.sh` | Blocks outbound traffic except allowed domains |
