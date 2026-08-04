# The eighteen checks

What each one actually inspects, and what satisfies it. Derived from
`ossf/scorecard` v5 source rather than the prose docs, because several checks
behave differently from how they read.

A check can return **inconclusive** (`?`) as well as 0–10. Inconclusive checks
are excluded from the aggregate, so an unreachable check is not the same as a
failed one.

## Critical

### Dangerous-Workflow

Looks for two patterns, both in `.github/workflows`:

1. **Untrusted code checkout** — `pull_request_target` or `workflow_run`
   combined with a checkout of `github.event.pull_request.*` /
   `github.event.workflow_run.*`. That runs a fork's code with a write token.
2. **Script injection** — a `${{ github.event.* }}` expression interpolated
   into a `run:` block. Only `github.event.*` counts;
   `${{ steps.x.outputs.y }}` and `${{ matrix.* }}` are not flagged.

Binary: 10 if clean, 0 if not. Easiest check to keep and one of the hardest to
recover: fix by passing untrusted values through `env:` and referencing them as
shell variables.

## High

### Token-Permissions

Wants a **top-level `permissions:`** in every workflow, read-only. `permissions:
read-all` or `contents: read` both qualify. A missing top-level block scores
worse than a restrictive one, because the repository default then applies.

Job-level writes are tolerated in proportion:

- `security-events: write` is expected in a SARIF-uploading job.
- `contents: write` is only forgiven when the workflow is recognised as a
  *releasing* workflow. The recognised shapes include `goreleaser-action`,
  `semantic-release`, `python-semantic-release`, `mvn release:prepare`, and a
  job whose `uses:` is `slsa-framework/slsa-github-generator/...`. A workflow
  that just runs `gh release create` is **not** recognised — adding the SLSA
  generator is what makes it so.

### Pinned-Dependencies

Every dependency of the build pinned by hash: actions by commit SHA, container
images by digest, and package installs done from a lockfile. Scored as a
proportion, so partial pinning gets partial credit.

Use the `pin-github-actions` skill. Note that Scorecard does not recognise every
package manager — `bun install --frozen-lockfile` is not flagged, but neither is
it credited.

### Dependency-Update-Tool

Existence only. `.github/dependabot.yml`, `.github/renovate.json`,
`renovate.json`, or `.pyup.yml`. The contents are not inspected — but write it
properly anyway, because the *Vulnerabilities* check reads the result.

### SAST

Looks for CodeQL, SonarCloud, Snyk, Qodana, or `github/codeql-action` in a
workflow, and for whether recent PRs were analysed. A CodeQL workflow on
`pull_request` is the straightforward answer.

### Vulnerabilities

Queries OSV for known unfixed vulnerabilities in the dependency tree. Nothing to
configure; Dependabot security updates are what keep it at 10.

### Maintained

Commit and issue activity over the last 90 days. Nothing to configure, and
nothing to do about it on a quiet project except be honest that it is quiet.

### Binary-Artifacts

Committed executables — `.jar`, `.exe`, `.dll`, `.so`, class files, and so on.
Images and fonts are fine. Scored down per artefact found.

### Branch-Protection

Requires a token with admin read to see the settings. Five cumulative tiers —
see [`github-setup.md`](github-setup.md), which has the exact table.

### Code-Review

Reads the last thirty changesets on the default branch and counts **unique
reviewers excluding the author**. A self-approved PR counts as zero reviewers;
so does a direct push.

**A single-maintainer repository scores 0 here and there is no configuration
that changes it.** Only a second reviewer does.

### Signed-Releases

Looks at the five most recent releases (the public releases API — **drafts are
invisible**, so a repo whose releases are all drafts returns inconclusive).

Per release, for each asset:

| Asset suffix                                                    | Worth |
| --------------------------------------------------------------- | ----- |
| `.asc`, `.minisig`, `.sig`, `.sign`, `.sigstore`, `.sigstore.json` | 8     |
| `.intoto.jsonl`                                                  | 10    |

`.bundle` and `.pem` are **not** in the list. With cosign v3 — which removed
`--output-signature` and `--output-certificate` from `sign-blob` — write the
bundle as `<name>.sigstore.json`.

## Medium

### Security-Policy

`SECURITY.md` (or `.github/SECURITY.md`, or in the org's `.github` repo).
Scored on content as well as presence: it wants a disclosure address or link and
some indication of a timeline. A one-line file scores lower than a real policy.

### Fuzzing

Satisfied by **any** of: an OSS-Fuzz project entry, `.clusterfuzzlite/Dockerfile`,
OneFuzz, or a language-native fuzzer / property-testing import found by pattern
in a prominent language of the repo.

| Language     | Pattern it looks for                                      |
| ------------ | ---------------------------------------------------------- |
| Go           | `func Fuzz…(… *testing.F)` in `*_test.go`                  |
| JS / TS      | import of `fast-check` or `@fast-check/{ava,jest,vitest}` in `*.js`/`*.jsx`/`*.ts`/`*.tsx` |
| Python       | `import atheris`                                           |
| Rust         | `libfuzzer_sys`                                            |
| C / C++      | `LLVMFuzzerTestOneInput`                                   |
| Java         | `com.code_intelligence.jazzer.api.FuzzedDataProvider;`     |
| C# / F#      | `FsCheck`, `Expecto.ExpectoFsCheck`                        |
| Haskell      | `Test.{Hspec,Tasty}.{QuickCheck,Hedgehog,Validity,SmallCheck}` |
| Elixir       | `use PropCheck` / `use ExUnitProperties`                   |
| Erlang       | `-include_lib("{eqc,proper}/include/….hrl")`               |
| Swift        | `LLVMFuzzerTestOneInput`                                   |
| Gleam        | `import qcheck`                                            |

"Prominent language" means at or above a quarter of the average lines-per-language
in the repo, per GitHub's language stats. A test-only language usually qualifies.

Binary: 10 if any fuzzer is found, 0 otherwise.

### Packaging

Recognises a publishing workflow by shape: `setup-node` + `npm publish`,
`setup-java` + `mvn deploy`/`gradle publish`, `gem push`, `nuget push`,
`docker push` or `docker/build-push-action`, `pypa/gh-action-pypi-publish`,
`goreleaser-action`, `cargo publish`, `ko-build/setup-ko`, `sbt ci-release`.

Anything else — including `gh release create` with installers attached — is not
recognised, and the check returns **inconclusive**, not 0. That costs nothing.

## Low

### License

`LICENSE`/`COPYING` in a recognised location, with an FSF/OSI-recognised licence.

### CII-Best-Practices

Looks up the project in the OpenSSF Best Practices database. 0 until you
register at <https://www.bestpractices.dev/>. Nothing in the repository affects
it.

### Contributors

Contributors from **at least two organisations** across the last 30 commits,
where "organisation" comes from contributors' public company field and org
membership. A solo or single-company project scores 0. This measures project
breadth, not security, and is weighted `low` accordingly.

### CI-Tests

Of the recent merged pull requests, how many ran a CI check. A `check`/`test`
workflow on `pull_request` gets this to 10 — provided PRs are actually used.
Direct pushes to the default branch score nothing here, because there was no PR
to run checks on.
