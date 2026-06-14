- When adding new feature or making significant changes, update `CHANGELOG.md`, `docs/user-guide.md` and `docs/index.md` accordingly. Update `docs/showcase.md` as well and rerender it.
- Do not commit changes unless explicitly asked to do so. When asked, use the following format for commit messages:

  ```txt
  <type>(<scope>): <subject>

  <body>

  <footer>
  ```

- **type:** chore, docs, feat, fix, refactor, style, test.
- **scope:** backend, frontend, infra, general.
- **subject:** A brief description of the change (max 50 characters).
- **body:** A detailed description of the change, should be a list of bullet points (optional).
- **footer:** Any relevant issue numbers or breaking change notes (optional).

## Instructions for Version Bump

- Check the changes done after last version bump using git tag or git log history
- Decide the version bump type based on the changes done (major, minor, patch)
- Update `__version__` in `md2pdf/__init__.py` and in `pyproject.toml` accordingly
- Run `uv lock` to update the lockfile version
- Validate `CHANGELOG.md` and update it with the changes done since last version bump
- Run tests (`uv run pytest`) to ensure everything is stable
- Commit, tag (e.g., `vX.Y.Z`), and push the changes (which will trigger the GitHub release workflow)
