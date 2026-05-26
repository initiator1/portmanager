# Release Checklist

Portmanager is not published yet. Use this checklist before the first public
release and for every release after that.

## Preflight

```bash
git status --short
uv run pytest
rm -rf dist build
uv build
```

Inspect the artifacts:

```bash
tar -tf dist/portmanager-*.tar.gz | sed -n '1,80p'
python -m zipfile -l dist/portmanager-*.whl | sed -n '1,80p'
```

Privacy scan:

```bash
rg -n "User[s]/|Picture[s]/|passw[o]rd|secr[e]t|api[_-]?ke[y]|BEGIN .*PRIVAT[E]" \
  README.md CONTRIBUTING.md LICENSE MANIFEST.in docs examples src tests pyproject.toml
```

The scan should produce no private paths or credentials.

## Version

1. Update `version` in `pyproject.toml`.
2. Update release notes.
3. Commit the version bump.
4. Tag the release after CI passes.

## Distribution Channel

Recommended initial channel:

1. Publish source and wheel artifacts to GitHub Releases.
2. Publish to PyPI once the name is available and the README renders cleanly.
3. Add Homebrew only after the CLI has a few external users; maintaining a tap
   before that adds release overhead without much benefit.

Do not publish until CI passes on the release commit and the privacy scan is
clean.

## GitHub Release

Tag pushes matching `v*` build the package, run tests, and create a GitHub
release with the artifacts from `dist/`.

```bash
git tag v0.1.0
git push origin v0.1.0
```

Do not create a tag until the release commit is already pushed and CI is green.
