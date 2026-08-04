---
name: pin-github-actions
category: security
description: Pin every third-party GitHub Action in a repository to a full commit SHA with a version comment, and keep the pins fresh with Dependabot. Use when asked to pin actions, harden CI against a compromised action, fix OpenSSF Scorecard's Pinned-Dependencies check, or audit which workflow steps are running unversioned code.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

# Pin GitHub Actions to a commit SHA

`uses: actions/checkout@v5` names a tag. A tag is a pointer, and the action's
owner can move it whenever they like — so that line is a standing grant of
arbitrary code execution on a runner holding your repository's token, redeemable
at any future time by whoever controls that account.

That is not hypothetical. In March 2025 `tj-actions/changed-files` was
compromised by retagging existing releases to point at a malicious commit; the
payload dumped runner memory — including secrets — into public build logs across
tens of thousands of repositories. Every repository pinning by SHA was
unaffected, because a SHA cannot be repointed.

Pinning turns "whatever they publish next" into "this commit, which I can read".

## Do it

```bash
# Report what is unpinned. Exits 1 if anything is. No network calls.
scripts/pin-actions.py --check

# Resolve every floating ref to its commit SHA and rewrite in place.
GITHUB_TOKEN=$(gh auth token) scripts/pin-actions.py
```

Defaults to `.github/workflows`; pass paths to narrow it. `GITHUB_TOKEN` is
optional but raises the API limit from 60 requests an hour to 5000.

The result:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

**The comment is not decoration.** It is the only human-readable record of which
version the SHA is, and Dependabot parses it to know what to bump to. Keep it to
the bare version — prose in that comment stops the pin from being updated.

## What is correctly not pinned

The script skips these, and so should you:

| Ref                                | Why                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------- |
| `./.github/actions/thing`          | Local. It is already this commit.                                      |
| `docker://alpine:3.20`             | A container image, pinned by digest instead if you want it pinned      |
| `slsa-framework/slsa-github-generator/...` | **Must** stay on a tag — see below                              |

### The SLSA generator is the exception that looks like a mistake

`slsa-github-generator`'s reusable workflows read `github.action_ref` at runtime
to decide which of their own binary releases to download. A commit SHA there
resolves to nothing and the job fails. This is
[a documented upstream requirement](https://github.com/slsa-framework/slsa-github-generator#referencing-slsa-builders-and-generators).

Leave a comment beside it saying so. Otherwise the next person to run a pinning
pass — or a well-meaning reviewer — will "fix" it and break releases.

## Then keep them fresh

A SHA does not float. That is the point, and it is also the cost: a security fix
upstream reaches you only if something opens the PR. Dependabot is that
something — it rewrites the SHA **and** the version comment together.

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    groups:
      # init, analyze and upload-sarif are three dependencies to Dependabot and
      # one thing in reality: they must land on the same SHA or the analysis and
      # the upload disagree about the bundle. One PR always, majors included.
      codeql-action:
        patterns: ['github/codeql-action*']
      actions:
        patterns: ['*']
        exclude-patterns: ['github/codeql-action*']
        update-types: [minor, patch]
```

Without this step, pinning makes a repository *less* current than it was. Do not
do one without the other.

## Enforce it

Add `--check` to CI so an unpinned action fails review rather than being noticed
a year later:

```yaml
- name: Actions are pinned to commit SHAs
  run: scripts/pin-actions.py --check
```

It makes no network calls, so it costs nothing and cannot flake on a rate limit.

## Verifying by hand

To confirm a SHA is what a tag really points at — worth doing once, to see why
the script dereferences twice:

```bash
gh api repos/OWNER/REPO/git/ref/tags/vX.Y.Z --jq '.object | {type, sha}'
```

If `type` is `commit`, that SHA is the answer. If it is `tag` — an *annotated*
tag — you have the tag object's SHA, which resolves to nothing on a runner.
Dereference it:

```bash
gh api repos/OWNER/REPO/git/tags/<that-sha> --jq '.object.sha'
```

`ossf/scorecard-action` ships annotated tags, so this is the common case, not a
corner one.

## Related

Pinning is one check of many. For the whole supply-chain posture — Scorecard,
CodeQL, signed releases, and the GitHub settings none of it works without — see
[`ossf-scorecard`](../ossf-scorecard/SKILL.md).
