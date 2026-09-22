#!/usr/bin/env python3
"""
Canonical name mapping for MTG tournament participants.

The actual mapping data is NOT stored in this file (or anywhere in git) --
it lives in the git-ignored data/name_mapping.json, since it contains real
participant names (PII). This module just loads that file into the
NAME_MAP dict that the rest of the OCR pipeline imports.

To set this up:
  1. Copy data/name_mapping.example.json to data/name_mapping.json.
  2. Fill it in with your own "raw OCR string": "canonical name" entries
     (use `python -m src.ocr.analyze_names` to discover raw name strings).

If data/name_mapping.json doesn't exist yet, NAME_MAP is simply empty and
a warning is printed -- apply_name_mapping.py will then report every name
as unmapped, which is expected until you create the file.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME_MAPPING_PATH = REPO_ROOT / "data" / "name_mapping.json"
NAME_MAPPING_EXAMPLE_PATH = REPO_ROOT / "data" / "name_mapping.example.json"


def _load_name_map():
    if not NAME_MAPPING_PATH.exists():
        print(
            "WARNING: " + str(NAME_MAPPING_PATH) + " not found -- NAME_MAP is empty.\n"
            "Copy " + NAME_MAPPING_EXAMPLE_PATH.name + " to " + NAME_MAPPING_PATH.name +
            " and fill in your own name corrections."
        )
        return {}

    with open(NAME_MAPPING_PATH, encoding="utf-8") as f:
        data = json.load(f)

    return dict((k, v) for k, v in data.items() if not k.startswith("_comment"))


NAME_MAP = _load_name_map()
