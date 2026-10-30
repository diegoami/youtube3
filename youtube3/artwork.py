"""Local template rendering. Pillow and YAML support are optional and loaded on use."""

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile

PRESETS = {"video": (1280, 720), "cover": (1280, 1280)}


class ArtworkError(ValueError):
    """Invalid artwork inputs, layout or output destination."""


def _pillow():
    try:
        from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps
    except ImportError:
        raise ArtworkError('Rendering needs pip install "youtube3[artwork]"') from None
    return Image, ImageColor, ImageDraw, ImageFont, ImageOps


def _integer(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ArtworkError(f"{label} must be an integer >= {minimum}")
    return value


def save_bytes(path, data, *, overwrite=False):
    """Publish complete bytes; preserve existing files unless explicitly replacing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        with path.open("xb") as output:
            output.write(data)
    else:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def plan_thumbnail(background, output, *, text="", episode=None, font=None, font_size=64,
                   color="white", position=(40, 40), preset="video", size=None, fit="cover",
                   overwrite=False, legacy=False):
    """Validate a local rendering request without generating files or contacting YouTube.

    Positions are the top-left of visible text, in output pixels. Legacy mode
    draws in source pixels before stretching to the output size.
    """
    background, output = Path(background).expanduser().resolve(), Path(output).expanduser().absolute()
    if not background.is_file():
        raise ArtworkError(f"Background is not a file: {background}")
    if output.resolve() == background:
        raise ArtworkError("Output must differ from the background")
    if output.exists() and not overwrite:
        raise ArtworkError(f"Output exists: {output}; choose another path or explicitly overwrite")
    if output.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise ArtworkError("Output must have a .png, .jpg or .jpeg extension")
    if preset not in PRESETS:
        raise ArtworkError("Preset must be video or cover")
    size = size if size is not None else PRESETS[preset]
    if not isinstance(size, (tuple, list)) or len(size) != 2:
        raise ArtworkError("Size must contain width and height")
    for value in size:
        _integer(value, "Image dimension", 1)
        if value > 16384:
            raise ArtworkError("Image dimensions must not exceed 16384 pixels")
    if not isinstance(position, (tuple, list)) or len(position) != 2:
        raise ArtworkError("Position must contain x and y")
    for value in position:
        _integer(value, "Text position")
    _integer(font_size, "Font size", 1)
    if not isinstance(text, str):
        raise ArtworkError("Text must be a string")
    if episode is not None:
        _integer(episode, "Episode")
        text = text.replace("{episode}", f"{episode:02d}") if text else f"{episode:02d}"
    if font is not None and not Path(font).expanduser().is_file():
        raise ArtworkError(f"Font is not a file: {font}")
    if fit not in ("cover", "contain", "stretch"):
        raise ArtworkError("Fit must be cover, contain or stretch")
    if not isinstance(color, (str, tuple, list)):
        raise ArtworkError("Color must be a Pillow color name, hex color or RGB tuple")
    return dict(background=str(background), output=str(output), text=text,
                font=str(Path(font).expanduser().resolve()) if font else None, font_size=font_size,
                color=color, position=list(position), size=list(size), fit=fit,
                overwrite=overwrite, legacy=legacy)


def render_thumbnail(background, output, **options):
    """Render PNG/JPEG artwork, returning its path. Preserve inputs and outputs by default."""
    plan = plan_thumbnail(background, output, **options)
    Image, ImageColor, ImageDraw, ImageFont, ImageOps = _pillow()
    try:
        with Image.open(plan["background"]) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        size = tuple(plan["size"])

        def resize(image):
            if plan["fit"] == "cover":
                return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
            if plan["fit"] == "contain":
                return ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color="black")
            return image.resize(size, Image.Resampling.LANCZOS)

        if not plan["legacy"]:
            image = resize(image)
        font = (ImageFont.truetype(plan["font"], plan["font_size"]) if plan["font"]
                else ImageFont.load_default(size=plan["font_size"]))
        color = ImageColor.getrgb(plan["color"]) if isinstance(plan["color"], str) else tuple(plan["color"])
        if len(color) != 3 or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in color):
            raise ArtworkError("Color must contain three RGB values from 0 to 255")
        draw = ImageDraw.Draw(image)
        x, y = plan["position"]
        box = draw.multiline_textbbox((0, 0), plan["text"], font=font)
        if x + box[2] - box[0] > image.width or y + box[3] - box[1] > image.height:
            raise ArtworkError("Text does not fit; reduce font size, move text or increase dimensions")
        origin = (x, y) if plan["legacy"] else (x - box[0], y - box[1])
        draw.multiline_text(origin, plan["text"], fill=color, font=font)
        if plan["legacy"]:
            image = resize(image)
        data = BytesIO()
        image.save(data, format="PNG" if Path(output).suffix.lower() == ".png" else "JPEG")
        save_bytes(plan["output"], data.getvalue(), overwrite=plan["overwrite"])
    except (OSError, ValueError) as error:
        raise ArtworkError(str(error)) from None
    return Path(plan["output"])


def legacy_plans(config_path, *, overwrite=False):
    """Migrate the original generator's JSON/YAML config into explicit rendering plans.

    Keep its (start_range, end_range] numbering, x2/x3 coordinates, source-pixel
    font sizing, stretch and thumbnail<N>.png naming. Four-plus digits use x3.
    Relative paths are resolved next to the configuration, not the current cwd.
    """
    path = Path(config_path).expanduser().resolve()
    if path.suffix.lower() == ".json":
        config = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            import yaml
        except ImportError:
            raise ArtworkError('YAML configuration needs pip install "youtube3[artwork]"') from None
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ArtworkError("Invalid YAML configuration") from None
    try:
        def local(value):
            return (path.parent / value).resolve()
        font, coords = config["font"], config["coords"]
        color = tuple(font["color"][key] for key in ("r", "g", "b"))
        start = _integer(config.get("start_range", 0), "start_range")
        end = _integer(config.get("end_range", 1000), "end_range")
        if end <= start:
            raise ArtworkError("end_range must be greater than start_range")
        return [plan_thumbnail(local(config["orig_file"]), local(config["output_dir"]) / f"thumbnail{number}.png",
                               episode=number, font=local(font["name"]), font_size=font["size"], color=color,
                               position=(coords["x2"] if number < 100 else coords["x3"], coords["y"]),
                               fit="stretch", legacy=True, overwrite=overwrite)
                for number in range(start + 1, end + 1)]
    except (KeyError, TypeError) as error:
        raise ArtworkError(f"Invalid legacy configuration: {error}") from None


def render_plan(plan):
    """Render one serialized plan, validating it again before writing."""
    options = dict(plan)
    background, output = options.pop("background"), options.pop("output")
    return render_thumbnail(background, output, **options)
