---
name: dependabot-groups
category: dependabot
description: Fix Dependabot opening separate PRs for dependencies that must be upgraded together — sub-path actions like github/codeql-action/init and /analyze, or monorepo module families like golang.org/x/* and @typescript-eslint/*. Use when a single upstream release produces several Dependabot PRs that each break CI alone, when someone is hand-writing "align X and Y to version Z" commits, or when asked to reduce Dependabot PR noise in a repo.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write
license: MIT
---

# Dependabot grouping

Dependabot versions dependencies individually. When an upstream project ships
one release across several dependency names, that becomes several PRs — and if
those names must be pinned to the same version, none of them pass CI alone. The
maintainer ends up closing all of them and hand-writing a commit that bumps them
together.

Grouping is the fix: `groups` in `.github/dependabot.yml` collapses related
dependencies into a single PR.

## When to use

- Several open Dependabot PRs bump the same upstream project under different names
- CI fails on a Dependabot PR because a sibling dependency is still on the old version
- Commit history contains manual "align", "sync", or "pin X and Y to Z" commits
- Asked to cut down Dependabot PR volume

## Two distinct problems

Keep these separate — they call for different config:

1. **Must-match families.** Correctness. The versions are not independent; a
   partial bump is broken. Group them with **no `update-types` filter** so majors
   stay grouped too.
2. **General PR noise.** Convenience. Bumps are independent, there are just a lot
   of them. Group minor/patch only, so majors still get individual review.

## Instructions

1. **Find the must-match families.** Don't guess from the list below — verify
   against the repo:
   - `grep -rn "uses:" .github/workflows/` — look for one action repo appearing
     under multiple sub-paths (`github/codeql-action/init`, `/analyze`,
     `/upload-sarif`).
   - Scan the manifest (`go.mod`, `package.json`, `requirements.txt`, `pom.xml`)
     for module families released as one unit.
   - `git log --oneline | grep -iE "align|sync|pin|bump.*and"` — past manual
     alignment commits are direct evidence of a family that needs grouping.
   - Check open Dependabot PRs: several PRs moving to the same version number is
     the signal.

   Families that commonly need this:

   | Ecosystem | Family |
   |---|---|
   | github-actions | `github/codeql-action*` (init / analyze / upload-sarif) |
   | github-actions | `actions/*-pages*` (configure / upload-pages-artifact / deploy-pages) |
   | gomod | `golang.org/x/*`, `github.com/aws/aws-sdk-go-v2*`, `k8s.io/*` |
   | npm | `@typescript-eslint/*`, `@babel/*`, `eslint-*` plugin sets, `@aws-sdk/*` |
   | pip | `boto3` + `botocore`, `opentelemetry-*` |
   | maven | `com.fasterxml.jackson*`, `org.springframework*` |

2. **Write the `groups` block** per ecosystem entry. Named group first, catch-all
   last, and exclude the named patterns from the catch-all so a family member
   can't be pulled out of its group:

   ```yaml
   version: 2
   updates:
     - package-ecosystem: github-actions
       directory: /
       schedule:
         interval: weekly
       groups:
         # Must be pinned to the same SHA — all update types, majors included.
         codeql-action:
           patterns:
             - "github/codeql-action*"
         # Noise reduction only — majors stay as individual PRs.
         actions:
           patterns:
             - "*"
           exclude-patterns:
             - "github/codeql-action*"
           update-types:
             - minor
             - patch
   ```

   Notes on the schema:
   - `patterns` matches dependency names, with `*` as a wildcard. For
     github-actions the name is `owner/repo/sub-path`, so `github/codeql-action*`
     catches every sub-path.
   - Omitting `update-types` means all update types — that is what keeps majors
     inside a must-match group.
   - A dependency matches at most one group; first match wins. Order matters.
   - `groups` needs no `open-pull-requests-limit` change; grouped PRs count as one.

3. **Report superseded PRs.** The new config does not regroup PRs that already
   exist. List the open Dependabot PRs the grouping replaces and say they need to
   be closed so Dependabot can reopen them as one grouped PR on its next run
   (`@dependabot recreate` does not regroup).

4. **Optionally align commit messages.** If the repo uses Conventional Commits,
   Dependabot's default `Build(deps): Bump ...` won't match. Add:

   ```yaml
   commit-message:
     prefix: chore    # or `ci` for the github-actions ecosystem
     include: scope   # produces "chore(deps): bump ..."
   ```

   Mention this as a separate, optional change — it is unrelated to grouping.

## Constraints

- Config only. Do not change version pins, add auto-merge, or alter schedules
  unless asked.
- Validate the YAML before committing — a malformed `dependabot.yml` makes
  Dependabot silently stop rather than error loudly.
- Grouped PRs are all-or-nothing: one bad bump blocks every other bump in the
  group. In a repo with flaky CI, skip the catch-all group and only create the
  must-match ones.
- Never group majors for anything except a verified must-match family.
