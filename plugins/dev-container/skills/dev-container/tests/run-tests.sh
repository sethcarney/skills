#!/usr/bin/env bash
# Exercise check-devcontainer-auth.py against known-good and known-broken
# devcontainer.json fixtures.
#
# Every fixture in fixtures/pass/ must exit 0; every fixture in fixtures/fail/
# must exit 1. A fail fixture that starts passing means the guard has stopped
# catching a regression it used to catch.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checker="${here}/../scripts/check-devcontainer-auth.py"

pass=0
fail=0

expect() {
	local want="$1" file="$2"
	local out rc
	out="$(python3 "$checker" "$file" 2>&1)"
	rc=$?
	if [ "$rc" -eq "$want" ]; then
		pass=$((pass + 1))
		printf '  ok    %-24s exit %d\n' "$(basename "$file")" "$rc"
	else
		fail=$((fail + 1))
		printf '  FAIL  %-24s expected exit %d, got %d\n' \
			"$(basename "$file")" "$want" "$rc"
		printf '%s\n' "$out" | sed 's/^/          /'
	fi
}

echo "expecting exit 0:"
for f in "${here}"/fixtures/pass/*.json; do expect 0 "$f"; done

echo "expecting exit 1:"
for f in "${here}"/fixtures/fail/*.json; do expect 1 "$f"; done

# --require-feature turns "no feature" from a skip into a failure.
echo "expecting exit 1 with --require-feature:"
if python3 "$checker" --require-feature \
	"${here}/fixtures/pass/no-feature-skipped.json" >/dev/null 2>&1; then
	fail=$((fail + 1))
	echo "  FAIL  no-feature-skipped.json  --require-feature did not fail"
else
	pass=$((pass + 1))
	echo "  ok    no-feature-skipped.json  --require-feature fails as expected"
fi

# No devcontainer.json anywhere is "nothing to check", not a failure.
echo "expecting exit 0 when there is nothing to check:"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if (cd "$tmp" && python3 "$checker" >/dev/null 2>&1); then
	pass=$((pass + 1))
	echo "  ok    empty directory          exits 0"
else
	fail=$((fail + 1))
	echo "  FAIL  empty directory          should exit 0"
fi

echo
echo "${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
