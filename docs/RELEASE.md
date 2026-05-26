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

## Publish

No publishing target is configured yet. Decide whether the first public channel
is PyPI, Homebrew, GitHub Releases, or a combination.
