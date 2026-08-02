#!/usr/bin/env bash
# Repair ownership of the Claude Code config volume.
#
# Docker creates a named volume owned by root when its mount point does not
# already exist in the image. This container is image + features with no
# Dockerfile, so nothing pre-creates ~/.claude -- leaving Claude Code unable to
# write its token into the very volume meant to persist it.
#
# The `! -w` guard keeps this a no-op once ownership is correct. Without it,
# every rebuild would recursively chown accumulated session history.
set -euo pipefail

claude_dir="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"

if [ -d "$claude_dir" ] && [ ! -w "$claude_dir" ]; then
	echo "post-create: ${claude_dir} is not writable, fixing ownership."
	sudo chown -R "$(id -u):$(id -g)" "$claude_dir"
fi

echo "post-create: ok. mdm $(mdm --version 2>/dev/null || echo '(not on PATH)')"
