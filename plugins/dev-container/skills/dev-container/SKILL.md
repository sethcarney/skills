---
name: dev-container
category: dev-container
description: Wrap a project's development environment in a dev container and run Claude Code inside it, with authentication persisted across rebuilds. Mounting a volume at ~/.claude is not sufficient on its own — the OAuth session lives in ~/.claude.json beside the directory, so CLAUDE_CONFIG_DIR must also be set. Use when setting up .devcontainer/devcontainer.json, when engineers must re-authenticate Claude Code after every rebuild, or when startup reports "Claude configuration file not found at /home/<user>/.claude.json".
user-invocable: true
allowed-tools: Bash, Read, Edit, Write
---

# Dev containers with Claude Code

A [dev container](https://containers.dev/) defines one isolated environment every
engineer on the team runs identically. With Claude Code installed inside it,
commands Claude runs execute in the container rather than on the host, while file
edits land in the local repository through the bind-mounted workspace.

The default setup has one sharp edge: the container's home directory is discarded
on rebuild, so Claude Code authentication is lost every time. Fixing that properly
takes **three** settings, not one — see step 3, which is the main reason this skill
exists.

## When to use

- Setting up `.devcontainer/` for a repo that doesn't have one
- Adding Claude Code to a dev container that already exists
- Engineers report having to sign in to Claude Code after every rebuild
- Standardizing toolchain versions across a team
- Asked to containerize or isolate the development environment
- This appears on startup — the diagnostic signature of the split-state bug:

  ```
  Claude configuration file not found at: /home/<user>/.claude.json
  A backup file exists at: /home/<user>/.claude/backups/.claude.json.backup.<ts>
  You can manually restore it by running: cp "..." "..."
  ```

  That message means a `~/.claude` volume is mounted but `CLAUDE_CONFIG_DIR` is
  not set. Go to [step 3](#3-persist-authentication-across-rebuilds), then
  [Recover a lost session](#recover-a-container-that-already-lost-its-session).

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
ls Dockerfile docker-compose.yml .devcontainer/devcontainer-lock.json 2>/dev/null
```

If `devcontainer.json` already exists, **add to it** — do not replace it. The
`features`, `mounts`, and `containerEnv` blocks are additive.

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

`/home/vscode` is correct for `mcr.microsoft.com/devcontainers/base:*`. Node images
and Anthropic's reference container use `/home/node`. This column matters for
step 3 — get it wrong and the setup fails silently. Verify rather than trusting the
table: see step 6.

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

The feature auto-adds the `anthropic.claude-code` VS Code extension; other editors
ignore that part.

It declares `installsAfter: ["ghcr.io/devcontainers/features/node"]`, which is an
ordering hint rather than a hard dependency — Anthropic's minimal example pairs the
feature with a bare base image and no Node feature. If a build fails during feature
install, add `ghcr.io/devcontainers/features/node:1`.

### 3. Persist authentication across rebuilds

**A volume on `~/.claude` alone does not persist the login.** Claude Code splits
its state across two locations:

| Path | Holds | Inside a `~/.claude` volume? |
|---|---|---|
| `~/.claude/` | settings, session history, `backups/`, `projects/` | yes |
| `~/.claude.json` | **OAuth session**, app state, personal MCP servers | **no** — sits beside the directory |

So a bare mount persists everything except the thing you wanted. The error in
[When to use](#when-to-use) is the tell: `backups/` is inside the volume and
survives, while `~/.claude.json` — the file it was copied from — was on the
container's throwaway filesystem.

`CLAUDE_CONFIG_DIR` relocates the whole config directory, `.claude.json` included,
so one volume covers all of it. That means **three settings naming the same
directory**, which must be `remoteUser`'s home:

```jsonc
{
  "features": {
    "ghcr.io/anthropics/devcontainer-features/claude-code:1.0": {}
  },
  "mounts": [
    "source=claude-code-config-${devcontainerId},target=/home/vscode/.claude,type=volume"
  ],
  "containerEnv": {
    "CLAUDE_CONFIG_DIR": "/home/vscode/.claude"
  },
  "remoteUser": "vscode"
}
```

Substitute the real home directory in **all three places**. A mismatch fails
silently — no error, just a login prompt on every rebuild.

Use a **named volume, not a bind mount**. A bind mount exposes host credential
files to the container.

#### Choosing the volume name

| Source name | Effect |
|---|---|
| `claude-code-config-${devcontainerId}` | Separate login per repository. Isolated state; sign in once per project. |
| `claude-code-config` (fixed) | One login shared across every repository. Sign in once total; shares history, MCP servers, and trust decisions. |

Ask which the user wants instead of defaulting silently. For a multi-repo rollout
the fixed name is usually what people actually want — signing in once per
repository gets old fast. Per-project isolation is the safer default for a single
repo or when state shouldn't leak between projects.

### 4. Fix volume ownership

Docker creates a named volume owned by `root` when its mount point doesn't already
exist in the image. With an image + features setup and no Dockerfile, nothing
pre-creates `~/.claude`, so Claude Code cannot write its token.

With **no Dockerfile**, repair it in `postCreateCommand`:

```bash
CLAUDE_DIR="${HOME}/.claude"
if [ -d "$CLAUDE_DIR" ] && [ ! -w "$CLAUDE_DIR" ]; then
	sudo chown -R "$(id -u):$(id -g)" "$CLAUDE_DIR"
fi
```

Keep the `! -w` guard so it's a no-op once correct. Without it, every rebuild
recursively chowns accumulated session history.

With a **Dockerfile**, pre-create the directory instead so Docker seeds the volume
with the right ownership:

```dockerfile
RUN mkdir -p /home/vscode/.claude && chown vscode:vscode /home/vscode/.claude
```

### 5. Handle the auth path for the user's provider

| Provider | Behavior |
|---|---|
| Anthropic | Browser sign-in with a Claude or Anthropic Console account |
| Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry | Uses cloud provider credentials, no browser prompt |

For cloud providers, pass credentials in as **environment variables** via
`containerEnv`, a Codespaces secret, or workload identity. Do not mount host
credential files to solve this — see [Security](#security).

**GitHub Codespaces.** `~/.claude` survives stopping and starting a codespace but
is still cleared on rebuild, so steps 3 and 4 apply there too. To carry
authentication across *different* codespaces, store `ANTHROPIC_API_KEY`, or a
`CLAUDE_CODE_OAUTH_TOKEN` generated by `claude setup-token`, as a
[Codespaces secret](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces).
Codespaces exposes secrets as environment variables automatically.

### 6. Rebuild and verify

Rebuild: VS Code Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) →
**Dev Containers: Rebuild Container**. For other tools use that tool's rebuild
action, or the [Dev Containers CLI](https://github.com/devcontainers/cli).

Then, in a terminal **inside the container**:

```bash
echo $HOME                  # must match the target path from step 3
whoami                      # must NOT be root
echo $CLAUDE_CONFIG_DIR     # must equal "$HOME/.claude"
[ -w ~/.claude ] && echo "writable"
claude                      # sign in
```

After authenticating:

```bash
[ -f ~/.claude/.claude.json ] && echo "persisted OK"
[ -f ~/.claude.json ]         && echo "BROKEN: CLAUDE_CONFIG_DIR not in effect"
```

The real check is to **rebuild a second time and confirm you are still signed in.**
Do not report this as working without that second rebuild — the first run proves
nothing, and every failure mode here is silent.

**Callback gotcha.** If browser sign-in completes but never returns to the
container, copy the code from the browser and paste it at the
`Paste code here if prompted` prompt. This happens when the editor's port
forwarding doesn't route the localhost callback.

## Recover a container that already lost its session

The OAuth session is in the backup, and the backup is inside the volume. Apply the
step 3 fix, rebuild, then:

```bash
cp ~/.claude/backups/.claude.json.backup.<timestamp> ~/.claude/.claude.json
```

The target is `~/.claude/.claude.json`, **not** the `~/.claude.json` path the error
message prints. That message is emitted before `CLAUDE_CONFIG_DIR` has moved the
location, so following it literally restores the file to the throwaway filesystem
and the session is lost again on the next rebuild.

## Optional hardening

Each of these is independent — apply only what the user asks for.

### Guard against regression

These failures are silent: nothing errors, the login just stops persisting. This
skill ships a checker that turns that into a loud failure —
[`scripts/check-devcontainer-auth.py`](scripts/check-devcontainer-auth.py), stdlib
Python 3, no dependencies:

```bash
# Checks .devcontainer/devcontainer.json by default
python3 scripts/check-devcontainer-auth.py

# Or name files explicitly
python3 scripts/check-devcontainer-auth.py path/to/devcontainer.json
```

Copy it into the target repo and run it in CI. It exits non-zero when:

1. `containerEnv.CLAUDE_CONFIG_DIR` is missing — **the exact bug this skill
   exists to prevent**, where a `~/.claude` volume is mounted but the OAuth
   session in `~/.claude.json` is still discarded.
2. `CLAUDE_CONFIG_DIR` and the mount target disagree, or either disagrees with
   `remoteUser`'s home. The expected path is derived from the file's own
   `remoteUser`, so this catches a base-image swap leaving the three paths
   drifted apart.
3. No mount targets the config directory.
4. That mount is `type=bind` rather than a named volume.
5. `remoteUser` is root or unset.

It exits 0 when there is no `devcontainer.json`, and skips a file that has no
Claude Code feature — pass `--require-feature` to make that a failure instead.

The suite in [`tests/`](tests/) exercises it against fixtures for each failure
mode; run `tests/run-tests.sh` after changing the checker.

If you'd rather write the assertions into an existing test suite than copy the
script, the three properties to assert are the checker's items 1–4 above.

### Pin the feature in devcontainer-lock.json

If the repo has a `devcontainer-lock.json`, adding a feature without a lock entry
leaves it unpinned:

```jsonc
"ghcr.io/anthropics/devcontainer-features/claude-code:1.0": {
  "version": "1.0.5",
  "resolved": "ghcr.io/anthropics/devcontainer-features/claude-code@sha256:<digest>",
  "integrity": "sha256:<digest>"
}
```

`devcontainer upgrade` regenerates this. To resolve the digest by hand:

```bash
T=$(curl -s "https://ghcr.io/token?scope=repository:anthropics/devcontainer-features/claude-code:pull&service=ghcr.io" \
    | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
curl -s -D - -o /dev/null -H "Authorization: Bearer $T" \
  -H "Accept: application/vnd.oci.image.manifest.v1+json" \
  "https://ghcr.io/v2/anthropics/devcontainer-features/claude-code/manifests/1.0" \
  | tr -d '\r' | sed -n 's/^[Dd]ocker-[Cc]ontent-[Dd]igest: //p'
```

A wrong digest is a hard build failure; a missing entry only means unpinned. **If
the digest cannot be verified, omit the entry rather than guess.**

### Enforce organization policy

Claude Code reads `/etc/claude-code/managed-settings.json` on Linux at the highest
precedence in the settings hierarchy, overriding anything in the config directory
or the project's `.claude/`. Install it from the Dockerfile:

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
checked in beside the dev container config. Note that *personal* MCP servers live
in `.claude.json`, so they persist only once step 3 is correct. Install any
binaries local stdio servers depend on in the Dockerfile, and add remote server
domains to the network allowlist if a firewall is in use.

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

- **Named volume, never a bind mount**, for the config directory. A bind mount
  exposes host credential files to the container.
- **Never mount host secrets** — not `~/.ssh`, not cloud credential files. Prefer
  repository-scoped or short-lived tokens, and pass cloud credentials as
  environment variables.
- Anything running in the container can read the token in the config directory.
  Treat that volume as a credential store, and avoid pairing it with
  `--dangerously-skip-permissions` on untrusted repositories — a dev container does
  not prevent a malicious project from exfiltrating anything reachable inside it,
  **including the credentials in the volume this skill sets up**.

## Constraints

- Config only. Don't restructure the project's build, change toolchain versions, or
  add unrequested tooling to the Dockerfile.
- Never replace an existing `devcontainer.json` — merge into it.
- Validate the JSON before finishing. `devcontainer.json` permits `//` comments
  (JSONC), so a plain `json.load` may report a false failure on a hand-written
  file; check that any parse error is real before "fixing" it.
- The firewall, managed settings, lock pinning, and bypass-permissions sections are
  opt-in. Don't apply them because they look thorough.

## Notes and confidence

- **The official dev containers page is incomplete on this point.** It states that
  `~/.claude` holds the auth token and that mounting a volume there is sufficient.
  The `.claude` directory reference is the accurate one: it lists `~/.claude.json`
  under `~/` as holding OAuth and warns against deleting it. Trust step 3 over the
  dev containers page.
- `CLAUDE_CONFIG_DIR` is thinly documented — mentioned in passing on the dev
  containers page, absent from the environment variables reference. Behavior
  verified directly against Claude Code CLI **v2.1.220**:
  - unset: writes both `$HOME/.claude.json` and `$HOME/.claude`
  - set: `$HOME` stays empty; `.claude.json`, `backups/`, `projects/`, `sessions/`
    all created inside the config directory
  - pointed at an already-populated `.claude`: `settings.json` and `backups/` left
    untouched

  Re-check if a future release changes the layout.

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
