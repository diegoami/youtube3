## UPLOAD

A PyPI upload is the owner's (`AGENTS.md`, Merging). From a clean checkout of the
tagged commit:

```
python -m pip install -e ".[dev]"
python -m build
python -m twine check --strict dist/*
python -m twine upload dist/*
```
