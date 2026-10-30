import builtins
import json
import sys

import pytest
from PIL import Image, ImageChops

from youtube3 import artwork
from youtube3.cli import artwork_render


@pytest.fixture
def background(tmp_path):
    path = tmp_path / "base.png"
    Image.new("RGB", (300, 150), "navy").save(path)
    return path


@pytest.mark.parametrize(("preset", "size"), [("video", (1280, 720)), ("cover", (1280, 1280))])
@pytest.mark.parametrize("episode", [9, 10, 99, 100, 999, 1000])
def test_render_dimensions_visible_text_and_preserves_input(background, tmp_path, preset, size, episode):
    before = background.read_bytes()
    output = tmp_path / f"{preset}{episode}.png"
    artwork.render_thumbnail(background, output, preset=preset, episode=episode)
    with Image.open(output) as result:
        assert result.size == size
        difference = ImageChops.difference(result, Image.new("RGB", size, "navy"))
        bounds = difference.getbbox()
        assert bounds and 40 <= bounds[0] <= 50 and bounds[1] == 40
        assert bounds[2] > 60 and bounds[3] > 60
    assert background.read_bytes() == before
    with pytest.raises(artwork.ArtworkError, match="exists"):
        artwork.render_thumbnail(background, output, episode=episode)


@pytest.mark.parametrize("fit", ["cover", "contain", "stretch"])
def test_fit_policy_and_jpeg(background, tmp_path, fit):
    output = tmp_path / "out.jpg"
    artwork.render_thumbnail(background, output, size=(100, 100), fit=fit, position=(0, 0))
    with Image.open(output) as image:
        assert image.size == (100, 100)
        expected = (0, 0, 0) if fit == "contain" else (0, 0, 128)
        assert all(abs(a - b) <= 2 for a, b in zip(image.getpixel((50, 0)), expected, strict=True))


def test_center_crop_keeps_middle_and_removes_outer_stripes(tmp_path):
    background = tmp_path / "stripes.png"
    image = Image.new("RGB", (300, 100), "red")
    for x in range(100, 200):
        for y in range(100):
            image.putpixel((x, y), (0, 128, 0))
    image.save(background)
    output = tmp_path / "crop.png"
    artwork.render_thumbnail(background, output, size=(100, 100))
    with Image.open(output) as result:
        assert result.getpixel((50, 50)) == (0, 128, 0)
        assert result.getpixel((10, 50)) == (0, 128, 0)


@pytest.mark.parametrize("options", [
    {"font_size": 0}, {"position": (-1, 0)}, {"size": (0, 10)}, {"episode": -1},
    {"font": "missing-font.ttf"}, {"fit": "invalid"}, {"text": "too wide", "font_size": 2000},
    {"color": "badcolor"}, {"color": (256, 0, 0)},
])
def test_invalid_layout_is_actionable_and_creates_no_output(background, tmp_path, options):
    output = tmp_path / "out.png"
    with pytest.raises(artwork.ArtworkError):
        artwork.render_thumbnail(background, output, **options)
    assert not output.exists()


def test_input_and_output_cannot_be_same_even_with_overwrite(background):
    with pytest.raises(artwork.ArtworkError, match="differ"):
        artwork.render_thumbnail(background, background, overwrite=True)


def test_explicit_overwrite(background, tmp_path):
    output = tmp_path / "out.png"
    output.write_bytes(b"old")
    artwork.render_thumbnail(background, output, overwrite=True)
    with Image.open(output) as image:
        assert image.size == (1280, 720)


def test_render_cli_preview_no_generation(background, tmp_path, monkeypatch, capsys):
    output = tmp_path / "out.png"
    monkeypatch.setattr(sys, "argv", ["render", "--background", str(background), "--out", str(output), "--episode", "1000"])
    monkeypatch.setattr(artwork, "render_plan", lambda plan: pytest.fail("preview rendered"))
    artwork_render.main()
    assert '"text": "1000"' in capsys.readouterr().out
    assert not output.exists()


def test_optional_dependency_error_and_help_without_pillow(monkeypatch, capsys):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("PIL"):
            raise ImportError("not installed")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(artwork.ArtworkError, match="youtube3\\[artwork\\]"):
        artwork._pillow()
    monkeypatch.setattr(sys, "argv", ["render", "--help"])
    with pytest.raises(SystemExit) as result:
        artwork_render.main()
    assert result.value.code == 0
    assert "--preset" in capsys.readouterr().out


def test_legacy_config_mapping_and_digit_boundaries(background, tmp_path, monkeypatch):
    # Pillow ships a scalable default font; write its bundled bytes as a synthetic font fixture.
    from PIL import ImageFont
    # Capture the actual built-in TrueType font stream without selecting an owner's font.
    font = ImageFont.load_default(size=20)
    font_path = tmp_path / "font.ttf"
    font_path.write_bytes(font.font_bytes)
    config = {"orig_file": background.name, "output_dir": "rendered", "font": {
        "name": font_path.name, "size": 20, "color": {"r": 255, "g": 255, "b": 255}},
        "coords": {"x2": 20, "x3": 10, "y": 10}, "start_range": 98, "end_range": 100}
    path = tmp_path / "render.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)
    plans = artwork.legacy_plans(path)
    assert [plan["text"] for plan in plans] == ["99", "100"]
    assert [plan["position"][0] for plan in plans] == [20, 10]
    for plan in plans:
        output = artwork.render_plan(plan)
        with Image.open(output) as image:
            assert image.size == (1280, 720)
    assert (tmp_path / "rendered" / "thumbnail99.png").is_file()


def test_legacy_yaml_is_supported_and_invalid_config_is_actionable(background, tmp_path):
    import yaml
    path = tmp_path / "render.yaml"
    path.write_text(yaml.safe_dump({"orig_file": background.name}), encoding="utf-8")
    with pytest.raises(artwork.ArtworkError, match="configuration"):
        artwork.legacy_plans(path)
    path.write_text("font: [", encoding="utf-8")
    with pytest.raises(artwork.ArtworkError, match="YAML"):
        artwork.legacy_plans(path)


def test_missing_and_corrupt_backgrounds(tmp_path):
    source, output = tmp_path / "base.png", tmp_path / "out.png"
    with pytest.raises(artwork.ArtworkError, match="Background"):
        artwork.render_thumbnail(source, output)
    source.write_bytes(b"not an image")
    with pytest.raises(artwork.ArtworkError):
        artwork.render_thumbnail(source, output)
    assert not output.exists()
