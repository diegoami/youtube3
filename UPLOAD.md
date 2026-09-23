## UPLOAD

A release is the owner's (`CLAUDE.md`, Merging). From a clean checkout of the
tagged commit:

```
python -m pip install -e ".[dev]"
python -m build
python -m twine check --strict dist/*
python -m twine upload dist/*
```
