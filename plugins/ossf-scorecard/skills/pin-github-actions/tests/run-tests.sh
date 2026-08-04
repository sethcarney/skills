#!/usr/bin/env bash
# Exercise pin-actions.py --check against workflow fixtures.
#
# Every fixture in fixtures/pass/ must exit 0; every fixture in fixtures/fail/
# must exit 1. A fail fixture that starts passing means the checker has stopped
# catching a way an action can float.
#
# --check makes no network calls, deliberately: the rewrite path needs the
# GitHub API, and a test suite that depends on an API rate limit fails for
# reasons that have nothing to do with the code.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checker="${here}/../scripts/pin-actions.py"

pass=0
fail=0

expect() {
	local want="$1" file="$2"
	local out rc
	out="$(python3 "$checker" --check "$file" 2>&1)"
	rc=$?
	if [ "$rc" -eq "$want" ]; then
		pass=$((pass + 1))
		printf '  ok    %-20s exit %d\n' "$(basename "$file")" "$rc"
	else
		fail=$((fail + 1))
		printf '  FAIL  %-20s expected exit %d, got %d\n' \
			"$(basename "$file")" "$want" "$rc"
		printf '%s\n' "$out" | sed 's/^/          /'
	fi
}

echo "pinned / exempt (expect exit 0):"
for file in "${here}"/fixtures/pass/*.yml; do
	expect 0 "$file"
done

echo
echo "unpinned (expect exit 1):"
for file in "${here}"/fixtures/fail/*.yml; do
	expect 1 "$file"
done

echo
if [ "$fail" -ne 0 ]; then
	echo "${fail} failed, ${pass} passed."
	exit 1
fi
echo "All ${pass} checks passed."
