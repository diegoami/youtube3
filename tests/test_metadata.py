from importlib.metadata import metadata


def test_the_license_published_for_1_2_5_is_kept():
    # Reads the installed metadata: reinstall after editing pyproject.toml.
    meta = metadata("youtube3")

    assert meta["License"] == "BSD License"
    assert "License :: OSI Approved :: BSD License" in meta.get_all("Classifier")
