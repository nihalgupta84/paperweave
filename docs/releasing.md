# Releasing PaperWeave

PaperWeave is configured for PyPI Trusted Publishing. This avoids storing a
PyPI API token in GitHub or in the repository. The official Python packaging
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
3. Confirm that the project name `paperweave` is available before the first
   release.

No `PYPI_API_TOKEN` GitHub secret is required for this workflow.

## Release a version

1. Update `version` in `pyproject.toml`, `CITATION.cff`, and `CHANGELOG.md`.
2. Run the local checks:

   ```bash
   python -m pip install -e ".[dev]"
   python -m unittest discover -s tests -v
   python -m build
   python -m twine check dist/*
   ```

3. Commit the version change and create an annotated tag:

   ```bash
   git tag -a v0.2.0 -m "Release PaperWeave 0.2.0"
   git push origin main --follow-tags
   ```

4. GitHub Actions builds the wheel and source distribution, then publishes
   them to the `pypi` environment. If the environment requires approval, review
   the run before approving it.
5. Verify the public installation in a fresh environment:

   ```bash
   python -m venv /tmp/paperweave-check
   /tmp/paperweave-check/bin/python -m pip install "paperweave[full]"
   /tmp/paperweave-check/bin/paperweave --help
   ```

Do not reuse a version already uploaded to PyPI. PyPI releases are immutable;
increment the version when a release must be corrected.
