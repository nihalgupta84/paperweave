# Releasing PaperWeave

PaperWeave includes a PyPI Trusted Publishing workflow for future releases.
For the first release, the package can be uploaded manually with the local
credential file supplied by the maintainer. The official Python packaging
workflow is: build an sdist and wheel, validate them, then upload them to the
package index. See the [PyPA packaging flow](https://packaging.python.org/en/latest/flow/)
and [Trusted Publishing guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/).

## One-time PyPI setup

1. Create or sign in to a PyPI account and enable two-factor authentication.
2. In PyPI account settings, add a pending trusted publisher with:
   - owner: `nihalgupta84`
   - repository: `paperweave`
   - workflow: `publish.yml`
   - environment: `pypi`
3. Confirm that the PyPI project `paperweave` is owned by this release and that
   the `0.1.0` version has not already been uploaded.

No `PYPI_API_TOKEN` GitHub secret is required for this workflow.

## Release a version manually

1. Update `version` in `pyproject.toml`, `CITATION.cff`, and `CHANGELOG.md`.
2. Run the local checks:

   ```bash
   python -m pip install -e ".[dev]"
   python -m unittest discover -s tests -v
   python -m build
   python -m twine check dist/*
   ```

3. Build and upload the artifacts with a credential stored outside the
   repository. Do not put the token in a shell script, commit, or log:

   ```bash
   python -m pip install --upgrade build twine
   python -m build
   python -m twine check dist/*
   python -m twine upload dist/*
   ```

   Twine reads `TWINE_USERNAME` and `TWINE_PASSWORD`; use a secret manager or
   your shell’s protected environment to provide them.

4. Commit the version change and create an annotated tag:

   ```bash
   git tag -a v0.1.0 -m "Release PaperWeave 0.1.0"
   git push origin main --follow-tags
   ```

5. Verify the public installation in a fresh environment:

   ```bash
   python -m venv /tmp/paperweave-check
   /tmp/paperweave-check/bin/python -m pip install "paperweave[full]"
   /tmp/paperweave-check/bin/paperweave --help
   ```

Do not reuse a version already uploaded to PyPI. PyPI releases are immutable;
increment the version when a release must be corrected.

## Trusted Publishing for future releases

1. Register a PyPI Trusted Publisher for owner `nihalgupta84`, repository
   `paperweave`, workflow `publish.yml`, and environment `pypi`.
2. Open the **Publish package** workflow manually in GitHub Actions after
   reviewing the version and artifacts.
3. Approve the `pypi` environment if repository protection requires approval.

Trusted Publishing is preferred for ongoing releases because it avoids a
long-lived upload token in CI.
