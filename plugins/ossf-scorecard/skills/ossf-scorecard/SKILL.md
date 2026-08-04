---
name: ossf-scorecard
category: security
description: Bring a GitHub repository up to a high OpenSSF Scorecard score — add the Scorecard, CodeQL and Dependabot wiring, pin every action to a commit SHA, sign releases with cosign and SLSA provenance, satisfy the Fuzzing check with property tests, and produce the branch-protection and repository-settings checklist that no file in the repo can configure. Use when asked to wire up OSSF checks, improve a Scorecard score, harden CI, set up supply-chain compliance, or interpret a Scorecard report.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, WebFetch
---

# OpenSSF Scorecard compliance

Take a repository from an unmeasured supply-chain posture to a high, honest
[Scorecard](https://scorecard.dev) score.

**The word that matters is honest.** Several checks measure facts about the
project rather than about the code — how many organisations contribute, whether
a second human reviewed the last thirty changesets. Those are not to be worked
around. Opening a pull request and self-approving it to satisfy Code-Review
makes the number less true, and the number is the only thing it was for.

Read [`references/checks.md`](references/checks.md) before deciding what to do.
Several checks are counter-intuitive and guessing wastes a cycle: Fuzzing is
satisfied by a `fast-check` import, Packaging returns *inconclusive* rather than
zero for anything it does not recognise, and `.bundle` is not a signature
extension but `.sigstore.json` is.

## Procedure

Steps 1–5 are files. Step 6 is the part only the repository owner can do, and
without it steps 1–5 are worth about six points.

### 1. Survey

Establish before writing anything:

- **Primary language** — decides the SAST config and whether Fuzzing is
  reachable at all.
- **Package manager and lockfile** — decides the Dependabot ecosystem. Getting
  this wrong produces PRs that bump the manifest and leave the lockfile behind,
  which a `--frozen-lockfile` CI then rejects, every week, forever.
- **Whether it publishes releases, and how** — Signed-Releases and Packaging
  both hinge on it.
- **Whether the repo is public** — `publish_results: true` and the badge need
  it.
- **What already exists.** Read the current workflows before adding any. A repo
  with a good `check.yml` needs pinning and permissions, not a second CI file.

### 2. Scorecard and SAST workflows

Add `.github/workflows/scorecard.yml`, and CodeQL (or the language's
equivalent) for SAST. Both on `push` to the default branch **and** a weekly
schedule — most of what Scorecard measures changes without anyone touching a
file, and a CodeQL query added upstream next month finds a bug in code committed
last month.

Non-obvious requirements, each of which silently produces a useless run:

- Scorecard needs `id-token: write` (that is how `publish_results` works),
  `security-events: write`, `actions: read`, and **`persist-credentials: false`
  on the checkout** — a hard requirement of the action, not a nicety.
- Scorecard must run from `push`, never `pull_request`. A fork's PR has no OIDC
  token; the run still scores, into nowhere.
- CodeQL for JS/TS wants `build-mode: none`. Building first hands CodeQL
  bundled, minified output — the same code with the names removed.
- Do not enable GitHub's CodeQL *default setup* alongside an advanced workflow.
  Both run, and every alert arrives twice.

### 3. Pin every action

Use the [`pin-github-actions`](../pin-github-actions/SKILL.md) skill. In short:

```bash
scripts/pin-actions.py --check      # report
GITHUB_TOKEN=$(gh auth token) scripts/pin-actions.py
```

Add `persist-credentials: false` to every checkout that does not push, while
you are in the file.

### 4. Policy files

- **`.github/dependabot.yml`** — the ecosystem matching the real lockfile, plus
  `github-actions`. The second one is what stops the SHA pins fossilising.
  Group `github/codeql-action*` on its own: init/analyze/upload-sarif are three
  dependencies and one thing.
- **`SECURITY.md`** — a real reporting path. Prefer GitHub private
  vulnerability reporting over an email address, and enable it in settings
  (step 6) or the link 404s. Write the release-verification commands here too;
  it is where someone holding a downloaded installer will look.
- **`.github/CODEOWNERS`** — advisory until "Require review from Code Owners"
  is ticked, and worth a point of Branch-Protection once it is.

### 5. Fuzzing and signed releases

**Fuzzing** is usually the cheapest ten points available — see the language
table in `references/checks.md`. For JS/TS it is an import of `fast-check` (or
`@fast-check/{ava,jest,vitest}`) in any `.ts`/`.tsx` file.

Do not add a token test to game it. Pick the functions where a generator
genuinely beats an example — quoting, encoding, parsers, anything handling
untrusted input — and state **properties, not outputs**:

- round-trip: `decode(encode(x)) == x`
- never-throws: any input at all, including the empty and the enormous
- invariant: length preserved, ordering stable, no output outside a shape
- injectivity: `x != y` implies `f(x) != f(y)` — this is how you pin "does not
  normalise"

Written that way they find real bugs, which is both the point and the
justification for the ten points.

**Signed releases** score 8 for a signature and 10 for provenance:

- Signature: a release asset ending `.asc`, `.minisig`, `.sig`, `.sign`,
  `.sigstore` or `.sigstore.json`. With cosign v3:
  `cosign sign-blob <f> --bundle <f>.sigstore.json`. v3 removed
  `--output-signature` and `--output-certificate`, and **`.bundle` alone is not
  a recognised extension** — name the bundle `.sigstore.json`.
- Provenance: an asset ending `.intoto.jsonl`, from
  `slsa-framework/slsa-github-generator`.

Two ordering rules:

- **Sign before creating the release, in the same job**, and attach in one
  call. Signing afterwards leaves a window where the release holds unsigned
  assets, and a separate upload step is one a failure can silently skip.
- **Generate provenance in the reusable workflow, not a step.** The guarantee is
  that the attestation is produced somewhere the build cannot reach.

Adding the SLSA generator has a second effect worth knowing: Scorecard then
classifies the workflow as a *releasing* workflow, which is what stops its
`contents: write` costing Token-Permissions points.

### 6. Produce the GitHub-side checklist

Branch protection, Dependabot alerts, private vulnerability reporting and the
default token permission are not in any file. Write them into a doc in the repo
(`docs/supply-chain.md` or equivalent) **and** state them in the reply — this is
the part the user has to act on, and it is worth more points than everything
above.

Use [`references/github-setup.md`](references/github-setup.md) as the basis. Its
Branch-Protection tier table is the piece people get wrong: the tiers are
cumulative, tier 4 needs **two** approvals, and there is a specific configuration
that scores 9 while leaving a solo maintainer able to merge.

### 7. Verify

```bash
actionlint                    # workflow syntax, action inputs, expressions
<the repo's own check command>
```

Then, with a token:

```bash
docker run -e GITHUB_AUTH_TOKEN="$(gh auth token)" \
  gcr.io/openssf/scorecard:stable \
  --repo=github.com/OWNER/REPO --show-details
```

`--show-details` is the useful part: it names the file and line behind each
deduction rather than only the score.

## Reporting back

Give three things, separated:

1. **What landed in the repo**, and what each file buys.
2. **The GitHub-side checklist**, ordered, with settings paths.
3. **What will not score, and why.** Name the structural zeros plainly instead
   of letting the user discover them from the badge. A projected score with the
   unreachable checks named is worth more than a promise of 10.

## References

- [`references/checks.md`](references/checks.md) — every check: what it
  inspects, how it scores, how to satisfy it.
- [`references/github-setup.md`](references/github-setup.md) — the settings
  checklist and the Branch-Protection tier table.
- [`pin-github-actions`](../pin-github-actions/SKILL.md) — the pinning pass and
  its script.
