# GitHub-side setup

None of this lives in the repository, and most of it cannot. Without it, the
files a repo can hold are worth roughly six points.

Give this to the user as an ordered checklist with the settings paths, not as a
description.

## 1. Branch protection on the default branch

**Settings → Rules → Rulesets → New branch ruleset** (or Settings → Branches for
the classic rule), targeting the default branch.

Scorecard scores this in five **cumulative** tiers. Each only counts once the one
below it is complete, so a repository with tier 5 settings and no tier 1 settings
scores zero. Order matters more than the list.

| Tier | Score | Settings                                                                                                                                                              |
| ---- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | 3     | Block force pushes; restrict deletions                                                                                                                                |
| 2    | 6     | Require a pull request before merging; require **≥1** approval; require branches to be up to date before merging; require approval of the most recent reviewable push |
| 3    | 8     | Require status checks to pass — name the actual checks (`check`, `Analyze (…)`)                                                                                       |
| 4    | 9     | Require **≥2** approvals **and** require review from Code Owners                                                                                                      |
| 5    | 10    | Dismiss stale approvals when new commits are pushed **and** do not allow bypassing the above settings                                                                  |

### Tiers 1–3 are free

Nothing there stops a solo maintainer working. Turn all of it on.

### Tier 4 costs something real

Two required approvals means you cannot merge your own work without two other
people. On a solo repository that is a choice between the point and the ability
to ship.

**The configuration that gets 9 and stays workable**: set the two approvals and
the Code Owners requirement, and leave **admin bypass on**. Scorecard reads the
configured rule, so tier 4 counts; you keep the ability to merge; tier 5 — which
is precisely "admins cannot bypass" — does not count. That is an honest 9: the
rule is real for everyone who is not you.

Ticking "Require review from Code Owners" is also what makes `.github/CODEOWNERS`
binding rather than advisory.

## 2. Code review — the one that cannot be configured

Scorecard reads the last thirty changesets and counts unique reviewers
**excluding the author**. Self-approval counts as zero. A single-maintainer
repository scores 0 on Code-Review and no setting changes that.

What moves it: a second human, or a review bot with its own identity.

Say this to the user rather than letting the badge say it. Do **not** suggest
routing work through PRs and self-approving to raise it — it does not raise it,
and if it did it would be a lie about the project.

## 3. Repository settings

**Settings → Code security:**

| Setting                          | Value | Why                                                                                  |
| -------------------------------- | ----- | ------------------------------------------------------------------------------------ |
| Private vulnerability reporting  | on    | The intake path `SECURITY.md` links to. Without it the link 404s.                    |
| Dependabot alerts                | on    | Feeds the Vulnerabilities check                                                      |
| Dependabot security updates      | on    | Opens the PR the day of a disclosure, rather than at the next weekly run             |
| CodeQL *default setup*           | off   | Only if using an advanced workflow — both enabled means every alert arrives twice    |
| Secret scanning + push protection | on   | Not a Scorecard check; free, and it stops the failure mode Scorecard cannot see      |

**Settings → Actions → General:**

| Setting                                              | Value                | Why                                                                        |
| ---------------------------------------------------- | -------------------- | -------------------------------------------------------------------------- |
| Workflow permissions                                 | Read repository contents | Workflows declare what they need; a permissive default only covers what someone forgot to declare |
| Allow GitHub Actions to create and approve pull requests | off              | An action that can approve a PR can satisfy the review requirement from §1 |

## 4. The OpenSSF Best Practices badge

CII-Best-Practices is 0 until the project is registered at
<https://www.bestpractices.dev/>. Nothing in the repository changes it.

Worth doing **after** the first release: several questions are about release
process and vulnerability response, and answering them honestly needs a release
to have happened.

## 5. The badge

After the first successful `scorecard.yml` run on the default branch:

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/OWNER/REPO/badge)](https://scorecard.dev/viewer/?uri=github.com/OWNER/REPO)
```

It 404s until that run has published — expected, not broken. Publishing requires
the repo to be public and `publish_results: true` with `id-token: write`.

## Checking the result

```bash
docker run -e GITHUB_AUTH_TOKEN="$(gh auth token)" \
  gcr.io/openssf/scorecard:stable \
  --repo=github.com/OWNER/REPO --show-details
```

Branch-Protection needs a token with admin read on the repo; with a plain token
that check comes back inconclusive locally even when it scores fine in CI.
