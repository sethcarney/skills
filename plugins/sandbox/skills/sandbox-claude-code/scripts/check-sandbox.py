#!/usr/bin/env python3
"""Audit a repository's Claude Code isolation posture.

Sandboxing fails quietly. If the sandbox can't start, Claude Code prints a
warning and runs commands unsandboxed. If a key is set in a scope that doesn't
honor it, the key is dropped with no error at all. Both read exactly like a
working sandbox.

This script resolves the settings the way Claude Code does -- scalars from the
highest-priority scope, arrays concatenated across every scope -- and then
reports what the resulting posture actually is.

Usage:
    check-sandbox.py [settings.json ...] [--strict] [--require-devcontainer]

With no paths, discovers the usual scopes in precedence order. Explicit paths
are merged in the order given, lowest precedence first.

Exits 1 on any failure, 0 otherwise. Warnings never fail the run unless
--warnings-as-errors is passed.

Stdlib only -- no pip install, runs anywhere Python 3 does.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from pathlib import Path

# Discovery order: lowest precedence first. Managed settings sit above
# everything, so they come last.
USER_SETTINGS = Path.home() / ".claude" / "settings.json"
PROJECT_SETTINGS = Path(".claude/settings.json")
LOCAL_SETTINGS = Path(".claude/settings.local.json")
MANAGED_SETTINGS = {
    "Darwin": Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
    "Linux": Path("/etc/claude-code/managed-settings.json"),
}

DEVCONTAINER_PATHS = [".devcontainer/devcontainer.json", ".devcontainer.json"]

# Keys project-scope settings files silently ignore. Setting one of these in
# .claude/settings.json looks like it worked and does nothing.
PROJECT_IGNORED_KEYS = [
    ("sandbox", "filesystem", "disabled"),
    ("sandbox", "network", "strictAllowlist"),
    ("sandbox", "network", "tlsTerminate"),
    ("sandbox", "allowAppleEvents"),
    ("sandbox", "credentials", "allowPlaintextInject"),
]

# Keys only managed settings honor.
MANAGED_ONLY_KEYS = [
    ("sandbox", "filesystem", "allowManagedReadPathsOnly"),
    ("sandbox", "network", "allowManagedDomainsOnly"),
    ("sandbox", "bwrapPath"),
    ("sandbox", "socatPath"),
]

# A sandbox exclusion this broad exempts effectively everything.
BROAD_EXCLUSIONS = {"*", "* *", "sh *", "bash *", "zsh *", "env *", "sudo *"}

# Secret paths worth a deny rule. Matched loosely: any deny rule mentioning the
# basename counts, so Read(./.env), Read(**/.env), and Read(.env) all satisfy
# the .env check.
SECRET_HINTS = [
    (".env", "Read(./.env) and Read(./.env.*)"),
    (".ssh", "Read(~/.ssh/**)"),
    (".aws", "Read(~/.aws/**)"),
]

# Rule forms that Claude Code accepts but never matches (v2.1.210+ warns at
# startup for each). They read as protection and provide none.
UNMATCHED_RULE_FORMS = re.compile(r"^(Write|NotebookEdit|Glob)\(")


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str) -> None:
        self.fails.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas.

    Settings files are usually strict JSON, but hand-written ones and
    devcontainer.json are JSONC. Comments inside strings must survive, so walk
    the text tracking string state rather than running a blind regex.
    """
    out = []
    i, n = 0, len(text)
    in_string = in_line_comment = in_block_comment = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
                out.append(c)
        elif in_block_comment:
            if c == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_string:
            out.append(c)
            if c == "\\":
                if i + 1 < n:
                    out.append(nxt)
                    i += 1
            elif c == '"':
                in_string = False
        else:
            if c == "/" and nxt == "/":
                in_line_comment = True
                i += 1
            elif c == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            else:
                if c == '"':
                    in_string = True
                out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load(path: Path) -> dict:
    return json.loads(strip_jsonc(path.read_text(encoding="utf-8")))


def merge(base: dict, overlay: dict) -> dict:
    """Merge overlay onto base the way Claude Code resolves scopes.

    Scalars take the higher-priority (overlay) value. Arrays concatenate and
    deduplicate -- lower-priority scopes can add entries, which is exactly how
    a user-level allow rule widens a locked-down project.
    """
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        elif isinstance(value, list) and isinstance(out.get(key), list):
            combined = out[key] + value
            seen, deduped = set(), []
            for item in combined:
                marker = json.dumps(item, sort_keys=True)
                if marker not in seen:
                    seen.add(marker)
                    deduped.append(item)
            out[key] = deduped
        else:
            out[key] = value
    return out


def dig(config: dict, *keys):
    node = config
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def has_devcontainer() -> bool:
    return any(Path(p).is_file() for p in DEVCONTAINER_PATHS)


def check_scope_placement(path: Path, config: dict, report: Report) -> None:
    """Flag keys sitting in a scope that ignores them."""
    # ~/.claude/settings.json is user scope and may set the restricted keys;
    # a .claude/settings.json anywhere else is project scope and may not.
    user_dir = (Path.home() / ".claude").resolve()
    is_project = (
        path.name in ("settings.json", "settings.local.json")
        and path.parent.name == ".claude"
        and path.parent.resolve() != user_dir
    )
    is_managed = "managed-settings" in path.name

    if is_project:
        for keys in PROJECT_IGNORED_KEYS:
            if dig(config, *keys) is not None:
                report.fail(
                    f"{path}: sandbox.{'.'.join(keys[1:])} is set here, but "
                    f"project-scope settings can't set it -- it is dropped with "
                    f"no error. Move it to ~/.claude/settings.json or managed "
                    f"settings"
                )
        for entry in dig(config, "sandbox", "credentials", "envVars") or []:
            if isinstance(entry, dict) and entry.get("mode") == "mask":
                report.fail(
                    f"{path}: credentials.envVars entry {entry.get('name')!r} "
                    f"uses mode 'mask', which project-scope settings can't set. "
                    f"The variable is NOT protected here; use 'deny' or move "
                    f"the entry to user or managed settings"
                )

    if not is_managed:
        for keys in MANAGED_ONLY_KEYS:
            if dig(config, *keys) is not None:
                report.warn(
                    f"{path}: sandbox.{'.'.join(keys[1:])} is honored only from "
                    f"managed settings and is ignored here"
                )


def check_sandbox(config: dict, report: Report, strict: bool) -> None:
    sandbox = config.get("sandbox") or {}

    if not sandbox.get("enabled"):
        report.fail(
            "sandbox.enabled is not true -- Bash commands run with no OS-level "
            "filesystem or network boundary"
        )

    if dig(sandbox, "filesystem", "disabled") is True:
        report.fail(
            "sandbox.filesystem.disabled is true -- sandboxed commands get "
            "unrestricted read and write access to the host, denyRead and "
            "credentials.files stop applying, and commands are still "
            "auto-allowed. A command can then write ~/.bashrc or a binary on "
            "$PATH and widen its own access on the next run"
        )

    if dig(sandbox, "network", "allowAllUnixSockets") is True:
        report.fail(
            "sandbox.network.allowAllUnixSockets is true -- this permits "
            "/var/run/docker.sock, which effectively grants access to the host"
        )

    for socket in dig(sandbox, "network", "allowUnixSockets") or []:
        if "docker.sock" in str(socket):
            report.fail(
                f"sandbox.network.allowUnixSockets includes {socket!r} -- the "
                f"Docker socket grants access to the host system"
            )

    excluded = sandbox.get("excludedCommands") or []
    for entry in excluded:
        if str(entry).strip() in BROAD_EXCLUSIONS:
            report.fail(
                f"sandbox.excludedCommands includes {entry!r}, which exempts "
                f"effectively every command from the sandbox"
            )

    if sandbox.get("enableWeakerNestedSandbox") and not has_devcontainer():
        report.warn(
            "sandbox.enableWeakerNestedSandbox is true but this repo has no "
            "devcontainer.json. It exists for unprivileged containers where the "
            "container is already the boundary; on a bare host it weakens the "
            "sandbox for nothing"
        )

    if sandbox.get("enableWeakerNetworkIsolation"):
        report.warn(
            "sandbox.enableWeakerNetworkIsolation is true -- it opens the macOS "
            "trust service and with it a data exfiltration path. Prefer listing "
            "the affected Go-based tools in excludedCommands"
        )

    if sandbox.get("allowAppleEvents"):
        report.warn(
            "sandbox.allowAppleEvents is true -- sandboxed commands can launch "
            "other applications unsandboxed with no prompt, which removes "
            "code-execution isolation"
        )

    domains = dig(sandbox, "network", "allowedDomains") or []
    if "*" in [str(d).strip() for d in domains]:
        report.fail(
            "sandbox.network.allowedDomains includes '*' -- every host is "
            "reachable, so there is no network boundary"
        )

    if sandbox.get("enabled") and not sandbox.get("failIfUnavailable"):
        report.note(
            "sandbox.failIfUnavailable is not set: if the sandbox can't start "
            "(missing bubblewrap, unsupported platform) Claude Code warns and "
            "runs unsandboxed"
        )

    if not strict:
        return

    if not sandbox.get("failIfUnavailable"):
        report.fail(
            "--strict: sandbox.failIfUnavailable is not true, so a missing "
            "dependency silently downgrades to unsandboxed execution"
        )
    if sandbox.get("allowUnsandboxedCommands") is not False:
        report.fail(
            "--strict: sandbox.allowUnsandboxedCommands is not false, so the "
            "dangerouslyDisableSandbox escape hatch can retry commands outside "
            "the sandbox"
        )
    if not domains:
        report.fail(
            "--strict: sandbox.network.allowedDomains is empty, so every new "
            "domain prompts instead of being decided in advance"
        )
    if dig(sandbox, "network", "strictAllowlist") is not True:
        report.fail(
            "--strict: sandbox.network.strictAllowlist is not true, so hosts "
            "outside the allowlist prompt rather than being denied (requires "
            "Claude Code v2.1.219+)"
        )


def check_permissions(config: dict, report: Report) -> None:
    perms = config.get("permissions") or {}
    deny = [str(rule) for rule in perms.get("deny") or []]
    allow = [str(rule) for rule in perms.get("allow") or []]
    ask = [str(rule) for rule in perms.get("ask") or []]

    mode = perms.get("defaultMode")
    if mode == "bypassPermissions" and not has_devcontainer():
        report.fail(
            "permissions.defaultMode is 'bypassPermissions' but this repo has "
            "no devcontainer.json -- with no prompts left, the isolation "
            "boundary is the only remaining control, and there is no evidence "
            "of one here"
        )

    joined_deny = " ".join(deny)
    for hint, suggestion in SECRET_HINTS:
        if hint not in joined_deny:
            report.warn(
                f"no deny rule mentions {hint!r} -- consider {suggestion}. The "
                f"sandbox's default read policy allows these paths too"
            )

    for rule in deny + allow + ask:
        if UNMATCHED_RULE_FORMS.match(rule):
            report.fail(
                f"permission rule {rule!r} is never matched by file permission "
                f"checks -- only Read(path) and Edit(path) rules are. Use "
                f"Edit(...) in place of Write(...) or NotebookEdit(...), and "
                f"Read(...) in place of Glob(...)"
            )

    if "*" in allow or "Bash(*)" in allow or "Bash" in allow:
        report.warn(
            "permissions.allow grants every Bash command. That is defensible "
            "only when a PreToolUse hook or an isolation boundary is doing the "
            "real work -- allow rules can't carry exceptions"
        )


def resolve(paths: list[Path], report: Report) -> dict:
    config: dict = {}
    for path in paths:
        try:
            loaded = load(path)
        except json.JSONDecodeError as e:
            report.fail(f"{path}: not valid JSON -- {e}")
            continue
        check_scope_placement(path, loaded, report)
        config = merge(config, loaded)
        report.note(f"read {path}")
    return config


def discover() -> list[Path]:
    found = [p for p in (USER_SETTINGS, PROJECT_SETTINGS, LOCAL_SETTINGS) if p.is_file()]
    managed = MANAGED_SETTINGS.get(platform.system())
    if managed and managed.is_file():
        found.append(managed)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit a repository's Claude Code isolation posture."
    )
    ap.add_argument(
        "paths",
        nargs="*",
        help="settings files to merge, lowest precedence first",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="also require the keys an unattended or managed deployment needs",
    )
    ap.add_argument(
        "--require-devcontainer",
        action="store_true",
        help="fail when the repo has no devcontainer.json",
    )
    ap.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="exit non-zero on warnings as well as failures",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the notes section",
    )
    args = ap.parse_args()

    report = Report()

    if args.paths:
        targets = [Path(p) for p in args.paths]
        missing = [p for p in targets if not p.is_file()]
        if missing:
            for p in missing:
                print(f"FAIL  {p}: no such file", file=sys.stderr)
            return 1
    else:
        targets = discover()
        if not targets:
            print(
                "FAIL  no Claude Code settings found -- this repo has no "
                "isolation configured at all. Add .claude/settings.json with "
                "sandbox.enabled set to true.",
                file=sys.stderr,
            )
            return 1

    config = resolve(targets, report)

    check_sandbox(config, report, args.strict)
    check_permissions(config, report)

    if args.require_devcontainer and not has_devcontainer():
        report.fail(
            "--require-devcontainer: no .devcontainer/devcontainer.json, so "
            "nothing constrains the in-process tools, MCP servers, or hooks "
            "that the Bash sandbox does not cover"
        )
    elif has_devcontainer():
        report.note(
            "devcontainer.json present -- also run check-devcontainer-auth.py "
            "from the dev-container skill"
        )

    if not args.quiet:
        for note in report.notes:
            print(f"NOTE  {note}")

    for warn in report.warns:
        print(f"WARN  {warn}")

    for fail in report.fails:
        print(f"FAIL  {fail}", file=sys.stderr)

    if report.fails:
        print(
            f"\n{len(report.fails)} failure(s), {len(report.warns)} warning(s). "
            f"This configuration does not isolate Claude Code the way it looks "
            f"like it does.",
            file=sys.stderr,
        )
        return 1

    if report.warns:
        print(f"\nOK with {len(report.warns)} warning(s).")
        return 1 if args.warnings_as_errors else 0

    print("\nOK    isolation posture checks out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
