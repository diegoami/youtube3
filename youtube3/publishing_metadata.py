"""Validated named metadata options; no arbitrary API body passthrough."""

import argparse
import re

SNIPPET_FIELDS = {"default_language": "defaultLanguage", "default_audio_language": "defaultAudioLanguage", "category_id": "categoryId"}
STATUS_FIELDS = {"made_for_kids": "selfDeclaredMadeForKids", "license": "license", "embeddable": "embeddable",
                 "public_stats_viewable": "publicStatsViewable", "contains_synthetic_media": "containsSyntheticMedia"}
FIELDS = set(SNIPPET_FIELDS) | set(STATUS_FIELDS)


def parts(options):
    if set(options) - FIELDS:
        raise ValueError("Unknown publishing metadata option")
    snippet, status = {}, {}
    for field, value in options.items():
        if value is None:
            continue
        if field == "license":
            if value not in ("youtube", "creativeCommon"):
                raise ValueError("license must be youtube or creativeCommon")
        elif field == "category_id":
            if not isinstance(value, str) or not value.isascii() or not value.isdigit():
                raise ValueError("category_id must be a numeric string")
        elif field in ("default_language", "default_audio_language"):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value):
                raise ValueError(f"{field} must be a language tag such as en or en-US")
        elif not isinstance(value, bool):
            raise ValueError(f"{field} must be true or false")
        target, mapping = (snippet, SNIPPET_FIELDS) if field in SNIPPET_FIELDS else (status, STATUS_FIELDS)
        target[mapping[field]] = value
    return snippet, status


def add_arguments(parser, *, default=None):
    parser.add_argument("--default-language")
    parser.add_argument("--default-audio-language")
    parser.add_argument("--license", choices=("youtube", "creativeCommon"))
    for field in ("made_for_kids", "embeddable", "public_stats_viewable", "contains_synthetic_media", "notify_subscribers"):
        parser.add_argument("--" + field.replace("_", "-"), action=argparse.BooleanOptionalAction, default=default)
