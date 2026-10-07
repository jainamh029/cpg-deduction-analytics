#!/usr/bin/env bash
# Rebuild the static site and publish it to the gh-pages branch (GitHub Pages serves that branch).
# Usage: scripts/publish_pages.sh   (needs `gh auth login` and push access to origin)
set -euo pipefail
cd "$(dirname "$0")/.."
repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
.venv/bin/python -m scripts.build_site --repo "$repo"
work="$(mktemp -d)"
cp -R site/. "$work/"
git -C "$work" init -q -b gh-pages
git -C "$work" add -A
git -C "$work" -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name || echo publisher)}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-$(git config user.email || echo publisher@users.noreply.github.com)}" \
    commit -q -m "Publish site from $(git rev-parse --short HEAD)"
git -C "$work" push -q --force "https://github.com/$repo.git" gh-pages
gh api -X POST "repos/$repo/pages" -f 'source[branch]=gh-pages' -f 'source[path]=/' >/dev/null 2>&1 || true
echo "published: https://$(echo "$repo" | cut -d/ -f1).github.io/$(echo "$repo" | cut -d/ -f2)/"
