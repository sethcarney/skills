# The half that is not in the repository

Branch-Protection, Code-Review, and CII-Best-Practices cannot be moved by
committing anything. This is the checklist to hand to whoever administers the
repository — written as steps they perform, since an agent working from a clone
cannot perform them.

## 1. Branch protection on the default branch

**Settings → Branches → Add branch ruleset** (or a classic protection rule),
targeting the default branch. Scorecard scores this in five tiers, and each tier
only counts once the one below it is complete — so the order matters more than
the list.

| Tier | Score | Settings |
| --- | --- | --- |
| 1 | 3 | Block force pushes; restrict deletions |
| 2 | 6 | Require a pull request before merging; require **≥1** approval; require branches to be up to date before merging; require approval of the most recent reviewable push |
| 3 | 8 | Require status checks to pass — name the actual check jobs (build, lint, CodeQL analysis) |
| 4 | 9 | Require **≥2** approvals **and** require review from Code Owners |
| 5 | 10 | Dismiss stale approvals when new commits are pushed **and** do not allow bypassing the above |

**Tiers 1–3 are free** on any project — turn them all on.

**Tier 4 costs something real on a solo repo**: two required approvals means you
cannot merge your own work without two other people. The way to have the score
and still be able to work is to configure the two approvals and the Code Owners
requirement, and leave **admin bypass on**. Scorecard reads the configured rule,
so tier 4 counts; you keep the ability to merge; and tier 5 — which is precisely
"admins cannot bypass" — does not. That is an honest 9: the rule is real for
everyone who is not you.

Ticking "Require review from Code Owners" is also what makes `.github/CODEOWNERS`
binding rather than advisory. Until then the file only requests reviewers.

Do not add Scorecard itself to the required status checks. A CVE disclosed in a
transitive dependency would block every unrelated pull request until it was
patched, which trains people to merge around the gate.

## 2. Code review

Not a setting. Scorecard counts unique reviewers excluding the author across the
last thirty changesets, so a single maintainer scores zero however the repository
is configured. A second human or a review bot with its own identity is what moves
it. Treat the zero as a description of the project rather than a defect to route
around — self-approving pull requests to raise it makes the score less true.

## 3. Repository settings

**Settings → Code security**

- **Private vulnerability reporting** — on. It is the intake path `SECURITY.md`
  points at; without it the link 404s.
- **Dependabot alerts** and **Dependabot security updates** — on. The config file
  schedules routine bumps; these two are what turns a disclosure into a PR the
  same day. Scorecard's Vulnerabilities check reads the same OSV data.
- **CodeQL default setup** — off if the repo has its own `codeql.yml` (advanced
  setup). Both together analyse twice and produce duplicate alerts.

**Settings → Actions → General**

- **Workflow permissions** → _Read repository contents and packages permissions_.
  Workflows that declare their own `permissions:` are unaffected; this default
  covers the ones somebody forgets to annotate, and a permissive default is how
  they stay forgotten.
- **Allow GitHub Actions to create and approve pull requests** → off. An action
  that can approve a pull request is an action that can satisfy the review
  requirement above.

## 4. The OpenSSF Best Practices badge

CII-Best-Practices stays at zero until the project is registered at
<https://www.bestpractices.dev/>. Work through the questionnaire — most of it is
already true of a repo that has done the rest of this list — and put the badge id
in the README.

Worth doing after the first release rather than before: several questions are
about release process and vulnerability response, and answering them honestly
needs a release to have happened.

## 5. The badge

After the first successful run on the default branch:

```markdown
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/<owner>/<repo>/badge)](https://scorecard.dev/viewer/?uri=github.com/<owner>/<repo>)
```

It 404s until that run publishes, which is expected rather than broken.
`securityscorecards.dev` is the previous host and still resolves; prefer
`scorecard.dev` in anything newly written.
