#!/usr/bin/env python3
"""Pin every third-party GitHub Action to a full commit SHA.

    pin-actions.py --check [PATH ...]    report unpinned actions, exit 1 if any
    pin-actions.py [PATH ...]            resolve and rewrite in place

PATH defaults to .github/workflows. Directories are walked for *.yml/*.yaml.

Rewrites `uses: owner/repo@v1.2.3` to `uses: owner/repo@<40-hex> # v1.2.3`.
The comment is not decoration: it is the only human-readable record of which
version the SHA is, and Dependabot reads it to know what to bump to.

Set GITHUB_TOKEN to raise the API rate limit from 60/hour to 5000.

Deliberately a line-oriented rewrite rather than a YAML round-trip. Workflow
files in a repo that cares about this are full of comments explaining why each
pin exists, and every YAML library in the standard library discards them.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"

# `uses:` value, capturing indent/key, the action ref, and any trailing comment.
USES = re.compile(
    r"^(?P<lead>\s*(?:-\s+)?uses:\s*)"
    r"(?P<action>[^\s#'\"]+)"
    r"(?P<tail>\s*(?:#.*)?)$"
)

SHA = re.compile(r"^[0-9a-f]{40}$")

# Reusable workflows that MUST stay on a tag.
#
# slsa-github-generator reads github.action_ref at runtime to decide which of
# its own binary releases to download. A commit SHA there resolves to nothing
# and the job fails — this is a documented upstream requirement, not a bug:
# https://github.com/slsa-framework/slsa-github-generator#referencing-slsa-builders-and-generators
TAG_ONLY = ("slsa-framework/slsa-github-generator",)


class Resolver:
    """tag -> commit SHA, with a cache so a repeated action costs one call."""

    def __init__(self):
        self.cache = {}
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def _get(self, url):
        request = urllib.request.Request(url)
        request.add_header("Accept", "application/vnd.github+json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def resolve(self, repo, ref):
        """Return the commit SHA `ref` points at, or None."""
        key = (repo, ref)
        if key in self.cache:
            return self.cache[key]

        sha = None
        for kind in ("tags", "heads"):
            try:
                data = self._get(f"{API}/repos/{repo}/git/ref/{kind}/{ref}")
            except urllib.error.HTTPError as error:
                if error.code in (403, 429):
                    raise SystemExit(
                        "GitHub API rate limit hit. Set GITHUB_TOKEN and retry."
                    ) from error
                continue

            obj = data.get("object", {})
            # An ANNOTATED tag points at a tag object, not a commit. Pinning
            # the tag object's SHA produces a ref that resolves to nothing on
            # a runner, so dereference one more time.
            if obj.get("type") == "tag":
                obj = self._get(f"{API}/repos/{repo}/git/tags/{obj['sha']}").get(
                    "object", {}
                )
            sha = obj.get("sha")
            if sha:
                break

        self.cache[key] = sha
        return sha


def workflow_files(paths):
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(
                p for p in path.rglob("*") if p.suffix in (".yml", ".yaml")
            )
        elif path.is_file():
            yield path


def classify(action):
    """Why an action is exempt from pinning, or None if it should be pinned."""
    if action.startswith("./") or action.startswith(".\\"):
        return "local action"
    if action.startswith("docker://"):
        return "docker image"
    if "@" not in action:
        return "no ref"

    repo_path, ref = action.rsplit("@", 1)
    if SHA.match(ref):
        return "already pinned"
    if any(repo_path.startswith(prefix) for prefix in TAG_ONLY):
        return "tag-only by upstream requirement"
    return None


def process(path, resolver, check_only):
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    changed = False
    findings = []

    for index, line in enumerate(lines):
        match = USES.match(line.rstrip("\n"))
        if not match:
            continue

        action = match.group("action")
        if classify(action) is not None:
            continue

        repo_path, ref = action.rsplit("@", 1)
        # owner/repo/sub/path -> owner/repo
        repo = "/".join(repo_path.split("/")[:2])

        findings.append((index + 1, action))
        if check_only:
            continue

        sha = resolver.resolve(repo, ref)
        if not sha:
            print(f"  ?? {path}:{index + 1} could not resolve {action}", file=sys.stderr)
            continue

        # The trailing comment becomes `# <ref>` and nothing else. Dependabot
        # parses that comment to learn which version the SHA is, and extra
        # prose in it stops the pin being updated. Say so rather than dropping
        # a human's note silently.
        existing = match.group("tail").strip().lstrip("#").strip()
        if existing and existing != ref:
            print(
                f"  !! {path}:{index + 1} dropped comment {existing!r} — "
                f"move it to its own line above if it still matters",
                file=sys.stderr,
            )

        newline = "\n" if line.endswith("\n") else ""
        lines[index] = f"{match.group('lead')}{repo_path}@{sha} # {ref}{newline}"
        changed = True
        print(f"  -> {path}:{index + 1} {action} -> {sha[:12]}… # {ref}")

    if changed:
        path.write_text("".join(lines))

    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=[".github/workflows"])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report unpinned actions without rewriting; exit 1 if any are found",
    )
    args = parser.parse_args()
    paths = args.paths or [".github/workflows"]

    files = list(workflow_files(paths))
    if not files:
        print(f"No workflow files under: {', '.join(paths)}", file=sys.stderr)
        return 1

    resolver = Resolver()
    unpinned = []
    for path in files:
        unpinned.extend((path, line, action) for line, action in process(path, resolver, args.check))

    if args.check:
        if unpinned:
            print(f"{len(unpinned)} unpinned action(s):")
            for path, line, action in unpinned:
                print(f"  {path}:{line}  {action}")
            return 1
        print(f"All actions in {len(files)} workflow file(s) are pinned to a commit SHA.")
        return 0

    print(f"Done. {len(files)} file(s) scanned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
