---
name: openssf-scorecard
category: security
description: Raise or set up an OpenSSF Scorecard score for a repository — install the scorecard.yml workflow, pin actions by SHA, fix Token-Permissions and Dangerous-Workflow findings, add the badge, and hand over the branch-protection settings that no file can turn on. Use whenever Scorecard, securityscorecards.dev, scorecard.dev, the OpenSSF badge, or a supply-chain posture review comes up; when someone asks why their score is low or how to raise it; and when a repo is being hardened for release, audit, or first publication, even if Scorecard is never named.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
license: MIT
---

# OpenSSF Scorecard

[Scorecard](https://scorecard.dev) grades a repository against eighteen checks
and publishes the result. Most of what it measures is real — an unpinned action
is a standing grant of code execution on a runner holding the repo's token — but
the score is a report, not a verdict, and some of it measures project size
rather than project security.

The work splits three ways, and keeping the split straight is most of the job:

| Bucket | Answered by | What to do |
| --- | --- | --- |
| **In-repo** | Files you can write | Fix them. This is the bulk of the score. |
| **GitHub-side** | Settings in the web UI | You cannot do this from a clone. Hand over a checklist. |
| **Structural** | Facts about the project | Report them accurately; do not work around them. |

The failure mode worth avoiding is chasing the number past the point where it
describes anything. A solo maintainer who opens pull requests to approve their
own work moves Code-Review off zero and makes the score less true. Aim for a
score the repo has actually earned, and say plainly where the remaining points
are and what they would cost.

## When to use

- Setting up Scorecard on a repo for the first time, or adding the badge
- A published score is lower than expected and someone wants to know why
- Hardening a repo before its first public release or a security review
- Scorecard findings appear in code scanning alerts and need triage
- Someone asks about pinning actions, workflow permissions, or supply-chain posture

## Workflow

### 1. Read the current score before changing anything

Guessing which checks are failing wastes effort on ones that already pass. Get
real data first.

If a run has published, the API has the per-check breakdown:

```bash
curl -s https://api.scorecard.dev/projects/github.com/<owner>/<repo> |
  jq '{score, checks: [.checks[] | {name, score, reason}] | sort_by(.score)}'
```

If nothing has published yet — no workflow, or it has never run on the default
branch — run it locally:

```bash
docker run -e GITHUB_AUTH_TOKEN="$(gh auth token)" \
  gcr.io/openssf/scorecard:stable \
  --repo=github.com/<owner>/<repo> --show-details
```

Two things about the local run: it queries the GitHub API rather than only the
checkout, so it needs the token; and Branch-Protection reads as inconclusive
unless that token has admin rights on the repo, because the protection rules
are not public. A `?` there is missing permission, not a missing rule.

Read `--show-details` output rather than only the scores — it names the file and
line behind each deduction, which turns "Token-Permissions: 0" into a specific
`permissions:` block that is missing.

### 2. Sort the findings

Put each failing check into one of the three buckets from the table above.
`references/checks.md` has the full list with what each check measures, how to
answer it, and where it commonly reports a false negative. Read it before
proposing fixes — several checks fail for reasons the name does not suggest.

Work the buckets in weight order — the aggregate is a weighted mean, so a
Critical check is worth four times a Low one, and a High-weight item in the
GitHub-side bucket deserves the user's attention before a Low one you could fix
yourself:

| Weight | Checks |
| --- | --- |
| Critical | Dangerous-Workflow |
| High | Binary-Artifacts, Branch-Protection, Code-Review, Dependency-Update-Tool, Maintained, Signed-Releases, Token-Permissions, Vulnerabilities |
| Medium | Fuzzing, Packaging, Pinned-Dependencies, SAST, Security-Policy |
| Low | CI-Tests, CII-Best-Practices, Contributors, License |

Treat this table as orientation and the run output as truth — Scorecard revises
weights between releases, and its output states the risk level per check.

### 3. Install the workflow, if it is not there

`assets/scorecard.yml` is a working `.github/workflows/scorecard.yml`. Copy it
in, then re-resolve every action SHA against upstream rather than trusting the
pins in the template, which age:

```bash
gh api repos/ossf/scorecard-action/commits/v2.4.4 --jq .sha
```

Four details in that file are load-bearing, and each is easy to undo:

- **`publish_results: true` plus `id-token: write`** is what creates the badge
  and the public API entry. A run without them still scores — into nowhere,
  which looks like the check is set up while nothing is recorded.
- **The trigger is `push` on the default branch, not `pull_request`.** Publishing
  is signed with an OIDC token a fork's PR does not have.
- **`persist-credentials: false`** is a hard requirement of the action. Scorecard
  reads the checkout to grade it, and a checkout carrying a credential in
  `.git/config` is a finding about the thing doing the grading.
- **The weekly schedule matters as much as the push trigger.** Maintained,
  Vulnerabilities, and Branch-Protection all change without anyone touching a
  file in the repo.

Leave it off the required status checks. A CVE disclosed in a transitive
dependency on a Tuesday would otherwise block every unrelated pull request until
it was patched, which teaches people to merge around the gate.

### 4. Fix the in-repo checks

The full per-check guidance is in `references/checks.md`. The three that pay
best per unit of effort, in most repos:

**Token-Permissions** — every workflow gets a top-level `permissions:` block, set
to the least it needs (usually `contents: read`), with any wider grant pushed
down to the single job that needs it:

```yaml
permissions: read-all        # or: contents: read

jobs:
  release:
    permissions:
      contents: write        # only this job writes
```

**Pinned-Dependencies** — everything CI executes is pinned to an artifact, not to
a name. A tag is a pointer its author can move; the `tj-actions/changed-files`
compromise in March 2025 was exactly that, a retagged release that dumped runner
memory into build logs across tens of thousands of repositories.

```yaml
uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

Keep the `# vX.Y.Z` comment: Dependabot rewrites the SHA and the comment
together, so the pin does not fossilise. The same rule reaches past actions —
container images want `image:tag@sha256:…`, npm wants `npm ci` against a
lockfile, pip wants `--require-hashes` against a fully hashed lock. Resolve every
SHA with `gh api`; never write one from memory.

**Dangerous-Workflow** — the only Critical check, and usually zero or ten. Look
for `pull_request_target` and for `${{ github.event.* }}` interpolated into a
`run:` block, which lets a PR title execute as shell on a runner with the repo's
token:

```bash
grep -rn "pull_request_target" .github/workflows/
grep -rn 'github\.event\.' .github/workflows/ | grep -v 'env:'
```

The fix for untrusted input is to pass it through `env:` and reference `"$VAR"`
inside the script, so it arrives as data rather than as text spliced into the
command.

### 5. Hand over the GitHub-side checklist

Branch-Protection, Code-Review, and CII-Best-Practices cannot be moved from
inside the repository. `references/github-settings.md` is the checklist: the five
branch-protection tiers and what each is worth, the repository settings that
matter, and the Best Practices badge registration.

Give it to the user as steps to perform, not as something you have done. Call out
the one decision with a real cost: tier 4 requires two approvals, which on a solo
repo means leaving admin bypass on to stay able to merge — worth a 9, and an
honest one, since the rule binds everyone who is not the admin.

### 6. Add the badge and write down the reasoning

Once a run has published on the default branch:

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/<owner>/<repo>/badge)](https://scorecard.dev/viewer/?uri=github.com/<owner>/<repo>)
```

The badge 404s until that first successful run — expected, not broken.
`securityscorecards.dev` is the previous host and still resolves; prefer
`scorecard.dev` in anything newly written.

Then leave a `docs/supply-chain.md` (or a section in an existing security doc)
recording what is checked, what each expected zero is, and the GitHub settings
the files depend on. The settings half lives nowhere in the repo, so without a
written record the next person cannot tell a deliberate zero from a regression,
and a workflow rename quietly breaks a guarantee nobody knew was load-bearing.

### 7. Report what the repo cannot score

End with an honest table of the checks that will stay low and why — a young
single-maintainer project has three or four of these:

| Check | Expected | Why |
| --- | --- | --- |
| Code-Review | 0 | One maintainer; Scorecard excludes the author from the reviewer count, correctly |
| Contributors | 0 | Needs contributors from ≥2 organisations; measures project size, not security |
| CII-Best-Practices | 0 | Until the project is registered at bestpractices.dev |
| Signed-Releases | `?` | Until a non-draft release exists — drafts are invisible to the public API |

Inconclusive checks (`?`) are excluded from the aggregate, so they cost nothing.
That is why an unreleased project is not penalised for having no signed releases.

## Constraints

- Do not make Scorecard a required status check, and do not gate merges on the score.
- Never trade a real guarantee for a point. If the only way to clear a warning is
  to weaken something — dropping SLSA Build L3 provenance to L2 to clear an
  unpinned-action finding, for instance — leave the warning and write down why.
  Scorecard has no suppression syntax, so a comment on the line is the record.
- Do not manufacture Code-Review score. Self-approvals and review-bot theatre
  make the number less accurate, which is the opposite of the point.
- Resolve action SHAs against upstream with `gh api`. A wrong SHA fails the
  workflow; a plausible-looking invented one is worse.
- Changing workflow permissions can break a release. When narrowing
  `permissions:`, check what each job actually does — pushing tags, commenting on
  PRs, and uploading SARIF all need a grant the default `contents: read` lacks.

## References

- `references/checks.md` — all eighteen checks: what each measures, how to answer
  it, and where it reports false negatives
- `references/github-settings.md` — branch-protection tiers, repository settings,
  and the Best Practices badge
- `assets/scorecard.yml` — the workflow, commented
