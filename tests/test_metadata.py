from importlib.metadata import metadata


def test_the_license_is_bsd_3_clause_with_its_file():
    # Reads the installed metadata: reinstall after editing pyproject.toml.
    meta = metadata("youtube3")

    assert meta["License-Expression"] == "BSD-3-Clause"
    assert meta.get_all("License-File") == ["LICENSE"]


def test_the_python_floor_is_3_11():
    assert metadata("youtube3")["Requires-Python"] == ">=3.11"
