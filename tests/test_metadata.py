from importlib.metadata import metadata


def test_the_license_is_bsd_3_clause_with_its_file():
    # Reads the installed metadata: reinstall after editing pyproject.toml.
    meta = metadata("youtube3")

    assert meta["License-Expression"] == "BSD-3-Clause"
    assert meta.get_all("License-File") == ["LICENSE"]


def test_the_python_floor_is_3_11():
    assert metadata("youtube3")["Requires-Python"] == ">=3.11"


def test_download_backend_is_only_an_optional_extra():
    meta = metadata("youtube3")
    assert "download" in meta.get_all("Provides-Extra")
    requirements = meta.get_all("Requires-Dist")
    backend = [requirement for requirement in requirements if requirement.startswith("yt-dlp")]
    assert len(backend) == 1
    assert "[default]" in backend[0]
    assert 'extra == "download"' in backend[0]
