# Releasing prefect-northflank

## Prepare

1. Confirm that the version in `prefect_northflank/__init__.py` is unused on PyPI and has an entry in `CHANGELOG.md`.
2. Merge the release PR after CI passes.
3. Check out the merged `master` commit with a clean working tree.
4. Build and validate fresh distributions:

   ```sh
   uv sync --locked --python 3.12
   uv run --locked pytest -q
   uv build --out-dir dist-release
   uvx --from twine==7.0.0 twine check --strict dist-release/*
   ```

Use a new, empty output directory so that the upload cannot include distributions from an earlier release.

## Publish 1.0.2

Run these steps only when the release is approved. Use your existing PyPI credentials; do not put credentials in repository files.

```sh
uvx --from twine==7.0.0 twine upload dist-release/prefect_northflank-1.0.2-py3-none-any.whl dist-release/prefect_northflank-1.0.2.tar.gz
git tag v1.0.2
git push origin v1.0.2
```

Create a GitHub release for `v1.0.2` using the changelog entry. Note that existing Prefect work pools need a base job template update to expose the new storage variables.

CI builds distributions for review; it does not publish to PyPI.
