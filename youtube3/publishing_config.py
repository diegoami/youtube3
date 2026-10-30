"""Explicit local publishing configuration, independent of OAuth credential files."""

from copy import deepcopy
import json
from pathlib import Path
import re
import string

SCHEMA = "youtube3.publishing-presets.v1"
FIELDS = {"profile", "expected_channel_id", "title", "description", "tags", "thumbnail", "privacy", "publish_at",
          "category_id", "made_for_kids", "retries", "variables", "title_template", "description_template", "thumbnail_template"}
TEXT_FIELDS = {"profile", "expected_channel_id", "title", "description", "thumbnail", "publish_at", "category_id",
               "title_template", "description_template", "thumbnail_template"}


class ConfigurationError(ValueError):
    """Invalid publishing settings; messages never echo whole configuration files."""


def read_document(path):
    path = Path(path).expanduser().resolve()
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ConfigurationError("Configuration exceeds 2 MiB")
    text = path.read_text(encoding="utf-8")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if not isinstance(key, str):
                raise ConfigurationError("Configuration keys must be strings")
            if key in result:
                raise ConfigurationError("Duplicate configuration key")
            result[key] = value
        return result

    try:
        if path.suffix.lower() == ".json":
            result = json.loads(text, object_pairs_hook=unique)
        elif path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                raise ConfigurationError('YAML configuration needs pip install "youtube3[publishing]"') from None

            class Loader(yaml.SafeLoader):
                pass

            def mapping(loader, node):
                loader.flatten_mapping(node)
                return unique((loader.construct_object(k), loader.construct_object(v)) for k, v in node.value)

            Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
            try:
                result = yaml.load(text, Loader=Loader)
            except yaml.YAMLError:
                raise ConfigurationError("Invalid YAML configuration") from None
        else:
            raise ConfigurationError("Configuration must be JSON or YAML")
    except (json.JSONDecodeError, UnicodeError):
        raise ConfigurationError("Invalid configuration document") from None
    if not isinstance(result, dict):
        raise ConfigurationError("Configuration must be an object")
    return result


def validate_settings(settings):
    if not isinstance(settings, dict) or any(not isinstance(key, str) or key not in FIELDS for key in settings):
        raise ConfigurationError("Unknown publishing setting; see documented configuration fields")
    for field in TEXT_FIELDS:
        if settings.get(field) is not None and not isinstance(settings[field], str):
            raise ConfigurationError(f"{field} must be a string or null")
    if "privacy" in settings and settings["privacy"] not in (None, "private", "unlisted", "public"):
        raise ConfigurationError("privacy must be private, unlisted, public or null")
    if settings.get("made_for_kids") is not None and not isinstance(settings["made_for_kids"], bool):
        raise ConfigurationError("made_for_kids must be true, false or null")
    if settings.get("tags") is not None and (not isinstance(settings["tags"], list) or
            any(not isinstance(tag, str) for tag in settings["tags"])):
        raise ConfigurationError("tags must be a list of strings or null")
    if "retries" in settings and (isinstance(settings["retries"], bool) or not isinstance(settings["retries"], int)
                                   or not 0 <= settings["retries"] <= 10):
        raise ConfigurationError("retries must be an integer from 0 to 10")
    variables = settings.get("variables", {})
    if not isinstance(variables, dict) or any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_]\w*", key)
            or not isinstance(value, (str, int)) or isinstance(value, bool) for key, value in variables.items()):
        raise ConfigurationError("variables must map simple names to strings or integers")
    for field in ("title", "description", "thumbnail"):
        if field in settings and field + "_template" in settings:
            raise ConfigurationError(f"Choose {field} or {field}_template within a single settings layer")
    return settings


def settings_layer(settings, base_dir=None):
    """Normalize paths at their defining layer, preserving a template's origin."""
    result = deepcopy(validate_settings(settings))
    if base_dir is not None:
        for field in ("thumbnail", "thumbnail_template"):
            if result.get(field) is not None:
                value = Path(result[field]).expanduser()
                result[field] = str(value if value.is_absolute() else Path(base_dir) / value)
    return result


def preset_layers(path, name):
    document = read_document(path)
    if set(document) - {"schema", "defaults", "presets"} or document.get("schema") != SCHEMA:
        raise ConfigurationError("Unsupported publishing presets schema/fields")
    if not isinstance(document.get("presets"), dict) or name not in document["presets"]:
        raise ConfigurationError("Selected publishing preset does not exist")
    root = Path(path).expanduser().resolve().parent
    return [settings_layer(document.get("defaults", {}), root), settings_layer(document["presets"][name], root)]


def resolve_settings(*layers, context=None):
    """Resolve left-to-right precedence, then expand only explicitly templated fields."""
    merged = {}
    for layer in layers:
        layer = settings_layer(layer)
        variables = {**merged.get("variables", {}), **layer.get("variables", {})}
        for field in ("title", "description", "thumbnail"):
            if field in layer:
                merged.pop(field + "_template", None)
            if field + "_template" in layer:
                merged.pop(field, None)
        merged.update(layer)
        if variables:
            merged["variables"] = variables
    values = {**merged.pop("variables", {}), **(context or {})}
    formatter = string.Formatter()
    for field in ("title", "description", "thumbnail"):
        template = merged.pop(field + "_template", None)
        if template is None:
            continue
        try:
            for _, name, spec, conversion in formatter.parse(template):
                if name is None:
                    continue
                if not re.fullmatch(r"[A-Za-z_]\w*", name) or conversion or (spec and not re.fullmatch(r"0?[1-9][0-9]{0,2}d", spec)):
                    raise ConfigurationError("Templates support simple {name} fields and bounded integer formats such as {episode:03d}")
                if name not in values:
                    raise ConfigurationError(f"Missing template variable: {name}")
            merged[field] = formatter.vformat(template, (), values)
        except ConfigurationError:
            raise
        except (ValueError, TypeError, KeyError):
            raise ConfigurationError(f"Invalid {field} template or variable type") from None
    if merged.get("thumbnail") is not None:
        merged["thumbnail"] = str(Path(merged["thumbnail"]).expanduser().resolve())
    return validate_settings(merged)


def resolve_preset(path, name, *, overrides=None, context=None):
    return resolve_settings(*preset_layers(path, name), overrides or {}, context=context)


def check_destination(client, settings):
    expected = settings.get("expected_channel_id")
    if expected is not None and client.signed_in_channel()["id"] != expected:
        raise ConfigurationError("Selected channel differs from the preset's expected channel ID")
