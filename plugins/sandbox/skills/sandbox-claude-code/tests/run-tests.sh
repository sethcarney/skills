#!/usr/bin/env bash
# Exercise check-sandbox.py against known-good and known-broken settings
# fixtures.
#
# Every fixture in fixtures/pass/ must exit 0; every fixture in fixtures/fail/
# must exit 1. A fail fixture that starts passing means the checker has stopped
# catching a misconfiguration it used to catch.
#
# Each fixture is a directory laid out like a real project, because several
# checks depend on where a settings file sits: keys that project scope silently
# ignores, and rules that only make sense with a devcontainer.json present. The
# runner cds into the fixture so relative discovery resolves against it, and
# passes settings files explicitly so the developer's own ~/.claude/settings.json
# never leaks into a test.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checker="${here}/../scripts/check-sandbox.py"

pass=0
fail=0

# Args for one fixture: its optional user-scope file first (lowest precedence),
# then its project settings.
fixture_args() {
	local dir="$1"
	[ -f "${dir}/user-settings.json" ] && printf '%s\n' "user-settings.json"
	printf '%s\n' ".claude/settings.json"
}

expect() {
	local want="$1" dir="$2"
	shift 2
	local out rc name
	name="$(basename "$dir")"
	# A fixture that isn't on disk makes the cd below fail, and a failed cd
	# exits 1 -- indistinguishable from a fail fixture doing its job. Check
	# first so a missing fixture is reported as missing.
	if [ ! -d "$dir" ]; then
		fail=$((fail + 1))
		printf '  FAIL  %-28s no such fixture directory\n' "$name"
		return
	fi
	mapfile -t files < <(fixture_args "$dir")
	out="$(cd "$dir" && python3 "$checker" "${files[@]}" "$@" 2>&1)"
	rc=$?
	if [ "$rc" -eq "$want" ]; then
		pass=$((pass + 1))
		printf '  ok    %-28s exit %d\n' "$name" "$rc"
	else
		fail=$((fail + 1))
		printf '  FAIL  %-28s expected exit %d, got %d\n' "$name" "$want" "$rc"
		printf '%s\n' "$out" | sed 's/^/          /'
	fi
}

# An unmatched glob stays literal, so an empty fixtures/fail/ would run one
# "fixture" named * that fails to cd and exits 1 -- a whole missing suite
# reporting itself as a pass. Require the glob to have matched something.
expect_all() {
	local want="$1" root="$2"
	local dirs=("${root}"/*/)
	if [ ! -d "${dirs[0]}" ]; then
		fail=$((fail + 1))
		printf '  FAIL  %-28s no fixtures found under %s\n' "$(basename "$root")" "$root"
		return
	fi
	for d in "${dirs[@]}"; do expect "$want" "${d%/}"; done
}

echo "expecting exit 0:"
expect_all 0 "${here}/fixtures/pass"

echo "expecting exit 1:"
expect_all 1 "${here}/fixtures/fail"

# The hardened fixture has no devcontainer, so --require-devcontainer must turn
# a clean pass into a failure.
echo "expecting exit 1 with --require-devcontainer:"
expect 1 "${here}/fixtures/pass/hardened" --require-devcontainer

# ...and must still pass for the fixture that has one.
echo "expecting exit 0 with --require-devcontainer:"
expect 0 "${here}/fixtures/pass/hardened-with-devcontainer" --require-devcontainer

# --strict adds the unattended-deployment requirements. The plain hardened
# fixture doesn't meet them; the user-scope one does.
echo "expecting exit 1 with --strict:"
expect 1 "${here}/fixtures/pass/hardened" --strict

echo "expecting exit 0 with --strict:"
expect 0 "${here}/fixtures/pass/user-scope-strict-keys" --strict

# A repo with no settings at all is a failure, not "nothing to check" -- the
# absence of configuration IS the finding here.
echo "expecting exit 1 when there is nothing configured:"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if (cd "$tmp" && HOME="$tmp" python3 "$checker" >/dev/null 2>&1); then
	fail=$((fail + 1))
	echo "  FAIL  unconfigured repo           should exit 1"
else
	pass=$((pass + 1))
	echo "  ok    unconfigured repo           exits 1"
fi

# A named file that doesn't exist is an error, not a silent skip.
echo "expecting exit 1 for a missing file:"
if python3 "$checker" "${here}/does-not-exist.json" >/dev/null 2>&1; then
	fail=$((fail + 1))
	echo "  FAIL  missing file                should exit 1"
else
	pass=$((pass + 1))
	echo "  ok    missing file                exits 1"
fi

echo
echo "${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
