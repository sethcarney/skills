# Changelog

All notable changes to this fork are documented here.

This project is a fork of the upstream [agent-skills](https://agentskills.io) CLI. The changelog below tracks changes made in this fork only; it does not reflect upstream changes.

---

## [1.8.0] — 2026-04-19

### Added

- **OSV vulnerability scanning** (`src/osv.ts`) — when installing a skill from a GitHub source, the CLI now queries the [OSV database](https://osv.dev) (`https://api.osv.dev/v1/query`) for known advisories against that repository. Results are shown in a note before the confirmation prompt. The check runs in parallel with agent/scope prompts (zero added latency), requires no API key, and never blocks installation — it is advisory only. If no advisories are found, nothing is displayed.

- **`-p` / `--project` flag for `skills add`** — forces project-scope installation without showing the global/project prompt. Useful for scripting and for teams that always want skills committed to the project. Mutually exclusive with `-g` / `--global`.

- **Declarative `skills-lock.json` entries** — `computedHash` is now optional in the project lock file schema. This means you can manually add skill entries to `skills-lock.json` before running `skills install`, and the hash will be populated on first install.

### Changed

- `skills-lock.json` is now documented as the unified project lock for both local path skills (`./src/my-skill`) and remote GitHub skills (`owner/repo`). Both were always supported; this release makes it explicit and adds the `-p` flag to make project-scope installs frictionless.

---

## [1.7.2] — 2026-04-19

### Removed

- **All telemetry** — removed `track()` and its supporting infrastructure (`isEnabled`, `isCI`, `setVersion`, all telemetry event interfaces, `TELEMETRY_URL`) from `src/telemetry.ts`. The `fetchAuditData` security audit function was retained at this point (see 1.7.2 patch below).

- **Third-party audit API** — removed the `fetchAuditData` call to `https://add-skill.vercel.sh/audit`, which sent the repo name and skill slugs to the upstream project's backend on every install. Also removed all dependent display code: `riskLabel`, `socketLabel`, `padEnd`, `buildSecurityLines`, and the parallel `auditPromise` fetch during install. `src/telemetry.ts` is now deleted entirely.

- **`initTelemetry` wrapper** — removed the one-liner `initTelemetry(version)` export from `add.ts` that existed solely to call `setVersion()`.

- **`UNIVERSAL_SKILLS_DIR` unused export** — removed from `src/constants.ts`; the constant was never imported anywhere.

### Fixed

- **Duplicate `getSkillLockPath()`** — the local copy in `src/cli.ts` was removed; the function is now imported from `src/skill-lock.ts` where the canonical implementation lives.

- **Stale "telemetry" references in comments** — updated comments across `source-parser.ts`, `types.ts`, `providers/types.ts`, `providers/wellknown.ts`, and `skill-lock.ts` to reflect that source identifiers are used for lock file storage, not telemetry.

- **Dead `bySource` grouping block in `remove.ts`** — this block existed only to group removals for the now-deleted `track()` call. Removed along with the orphaned `source`/`sourceType` fields on the results array and the unused `getSkillFromLock` import.

---

## [1.7.1] — baseline fork

Initial fork of the upstream agent-skills CLI. The following changes were made relative to upstream at the time of forking:

- Self-update command (`skills update-cli`) — updates the CLI binary in place without a package manager
- Bun binary distribution — builds compile to standalone native executables via `bun build --compile`

### Known issues at fork time (since fixed)

- README incorrectly described the self-update command as `skills update --self`
- README claimed telemetry was "removed" when it was only opt-in (required `ENABLE_TELEMETRY=1`)

---

## Decision log

### Why OSV instead of the upstream audit API

The upstream CLI used `https://add-skill.vercel.sh/audit` to fetch security ratings from a closed-source backend that aggregated results from Socket.dev, Snyk, and an internal scanner. This was removed because:

1. The backend is opaque — there is no way to verify what it logs server-side
2. It uses the same domain (`add-skill.vercel.sh`) as the telemetry endpoint, raising the question of whether install intent is being recorded even when `ENABLE_TELEMETRY` is unset
3. It requires trusting a third-party service with the names of every skill you install

OSV (`osv.dev`) was chosen as the replacement because:

1. Fully open — the advisory database is public and the API requires no authentication
2. What is sent is minimal and obvious: a `pkg:github/owner/repo` PURL in a POST body
3. Run by Google's open-source security team with a clear public charter
4. Covers the GitHub Actions ecosystem which is the most relevant attack surface for skill repos

The trade-off is that OSV's coverage of arbitrary GitHub repos is narrower than a dedicated supply-chain scanner. Most skill repos will return zero results — which is honest rather than showing manufactured "Safe" labels.

### Why `computedHash` is optional in `skills-lock.json`

Making the hash required forced every entry to have been installed at least once before being committed. This made it impossible to use `skills-lock.json` as a declarative manifest — e.g., adding a remote skill reference before running `skills install` on a fresh clone. Making it optional means:

- You can declare skills in the lock file before first install
- `skills install` restores them and populates the hash
- Existing entries with a hash continue to work unchanged for update detection
