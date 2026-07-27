#!/usr/bin/env python3
"""Regression guard for Claude Code auth persistence in a dev container.

Mounting a volume at ~/.claude does NOT persist the Claude Code login on its
own: the OAuth session lives in ~/.claude.json, beside the directory rather
than inside it. Persisting it takes three settings that must all name the same
directory -- the volume mount, containerEnv.CLAUDE_CONFIG_DIR, and remoteUser.

Every way of getting this wrong fails silently: no error, no warning, just a
sign-in prompt on every rebuild. This script turns that silent failure into a
loud one.

Usage:
    check-devcontainer-auth.py [devcontainer.json ...] [--require-feature]

With no paths, searches the usual locations. Exits 0 when every checked file
passes (or there is nothing to check), 1 on any failure.

Stdlib only -- no pip install, runs anywhere Python 3 does.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FEATURE = "ghcr.io/anthropics/devcontainer-features/claude-code"

DEFAULT_PATHS = [
    ".devcontainer/devcontainer.json",
    ".devcontainer.json",
]

# remoteUser -> home directory, for the users that don't follow /home/<name>.
HOME_OVERRIDES = {"root": "/root"}


def strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas.

    devcontainer.json is JSONC. Comments inside strings must survive, so this
    walks the text tracking string state rather than running a blind regex.
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
    # trailing commas before } or ]
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def home_for(remote_user: str) -> str:
    return HOME_OVERRIDES.get(remote_user, f"/home/{remote_user}")


def parse_mount(mount) -> dict:
    """Normalize a mount entry. Accepts the string and object forms."""
    if isinstance(mount, dict):
        return {k: str(v) for k, v in mount.items()}
    parsed = {}
    for part in str(mount).split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            parsed[k.strip()] = v.strip()
    return parsed


def has_feature(config: dict) -> bool:
    return any(str(k).startswith(FEATURE) for k in (config.get("features") or {}))


def check(path: Path, require_feature: bool) -> tuple[list[str], list[str]]:
    """Return (failures, notes) for one devcontainer.json."""
    fails: list[str] = []
    notes: list[str] = []

    raw = path.read_text(encoding="utf-8")
    try:
        config = json.loads(strip_jsonc(raw))
    except json.JSONDecodeError as e:
        return ([f"{path}: not valid JSONC -- {e}"], notes)

    if not has_feature(config):
        if require_feature:
            fails.append(
                f"{path}: the Claude Code feature ({FEATURE}) is not in `features`"
            )
        else:
            notes.append(f"{path}: no Claude Code feature, skipped")
        return (fails, notes)

    # remoteUser drives the expected paths, so resolve it first.
    remote_user = config.get("remoteUser")
    if not remote_user:
        fails.append(
            f"{path}: `remoteUser` is not set, so the config directory path "
            f"cannot be verified (and the container likely runs as root)"
        )
        return (fails, notes)
    if remote_user == "root":
        fails.append(
            f"{path}: `remoteUser` is root -- Claude Code rejects "
            f"--dangerously-skip-permissions as root, and the container should "
            f"not run privileged"
        )

    expected = f"{home_for(remote_user)}/.claude"

    # 1. CLAUDE_CONFIG_DIR must point at the same directory as the mount.
    #    Without it, ~/.claude.json (the OAuth session) stays on the throwaway
    #    filesystem and the login is lost on every rebuild.
    config_dir = (config.get("containerEnv") or {}).get("CLAUDE_CONFIG_DIR")
    if not config_dir:
        fails.append(
            f"{path}: containerEnv.CLAUDE_CONFIG_DIR is not set -- a volume on "
            f"~/.claude alone does NOT persist the login, because the OAuth "
            f"session lives in ~/.claude.json beside it. Set it to {expected!r}"
        )
    elif config_dir.rstrip("/") != expected:
        fails.append(
            f"{path}: containerEnv.CLAUDE_CONFIG_DIR is {config_dir!r} but "
            f"remoteUser {remote_user!r} means it must be {expected!r}"
        )

    # 2. A named volume must be mounted at that same path.
    mounts = [parse_mount(m) for m in (config.get("mounts") or [])]
    target_match = [
        m for m in mounts if (m.get("target") or m.get("dst") or "").rstrip("/") == expected
    ]
    if not target_match:
        seen = [m.get("target") or m.get("dst") or "?" for m in mounts] or ["none"]
        fails.append(
            f"{path}: no mount targets {expected!r} (targets found: "
            f"{', '.join(seen)}) -- without it the config directory is "
            f"discarded on rebuild"
        )
    else:
        for m in target_match:
            mtype = m.get("type", "")
            if mtype == "bind":
                fails.append(
                    f"{path}: the mount at {expected!r} is type=bind -- use a "
                    f"named volume instead; a bind mount exposes host "
                    f"credential files to the container"
                )
            elif mtype != "volume":
                fails.append(
                    f"{path}: the mount at {expected!r} has type={mtype!r}, "
                    f"expected type=volume"
                )
            if not (m.get("source") or m.get("src")):
                fails.append(f"{path}: the mount at {expected!r} has no source")

    return (fails, notes)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify a dev container persists Claude Code authentication."
    )
    ap.add_argument("paths", nargs="*", help="devcontainer.json files to check")
    ap.add_argument(
        "--require-feature",
        action="store_true",
        help="fail when the Claude Code feature is absent (default: skip the file)",
    )
    args = ap.parse_args()

    if args.paths:
        targets = [Path(p) for p in args.paths]
        missing = [p for p in targets if not p.is_file()]
        if missing:
            for p in missing:
                print(f"FAIL  {p}: no such file", file=sys.stderr)
            return 1
    else:
        targets = [Path(p) for p in DEFAULT_PATHS if Path(p).is_file()]
        if not targets:
            print("No devcontainer.json found, nothing to check.")
            return 0

    all_fails: list[str] = []
    all_notes: list[str] = []
    for path in targets:
        fails, notes = check(path, args.require_feature)
        all_fails += fails
        all_notes += notes

    for note in all_notes:
        print(f"SKIP  {note}")

    if all_fails:
        for f in all_fails:
            print(f"FAIL  {f}", file=sys.stderr)
        print(
            f"\n{len(all_fails)} problem(s). Claude Code authentication will not "
            f"survive a rebuild.",
            file=sys.stderr,
        )
        return 1

    checked = len(targets) - len(all_notes)
    if checked:
        print(f"OK    {checked} file(s) persist Claude Code authentication correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
