# Release Checklist

Every version bump follows these steps in order.

## Pre-release

- [ ] All tests pass: `pytest tests/ -v`
- [ ] `cold_eyes/__init__.py` `__version__` matches the target version
- [ ] `CHANGELOG.md` has an entry for this version with test count
- [ ] No uncommitted changes: `git status` is clean

## Release

- [ ] Create git tag: `git tag vX.Y.Z`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Create GitHub Release from tag (include upgrade steps + known limitations)

## Post-release

- [ ] GitHub repo About description matches current version/test count
- [ ] Verify install: `bash install.sh && python ~/.claude/scripts/cold_eyes/cli.py doctor`
