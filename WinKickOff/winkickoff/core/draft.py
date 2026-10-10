"""The draft of the open profile (1.4.0-rc.2): unsaved changes written next to the program every minute and on close, so
that closing the window never loses them and needs no question. The next start opens the draft with its changes still
unsaved (dirty); saving the profile, opening another one or dropping the changes deletes it.

The draft is `draft.json` in the program folder: an envelope {"format": "winkickoff-draft", "version": 1, "path",
"saved", "profile"} around the profile as Profile.to_dict writes it, read back as strictly as a profile file.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.catalog import Catalog
from winkickoff.core.profile import PROFILE_MAX_BYTES, Profile, _now

DRAFT_FILE = "draft.json"
FORMAT = "winkickoff-draft"
VERSION = 1


def draft_path(root: Path) -> Path:
    return root / DRAFT_FILE


def _envelope(profile: Profile, catalog: Catalog) -> dict[str, Any]:
    return {"format": FORMAT, "version": VERSION, "path": str(profile.path or ""), "profile": profile.to_dict(catalog)}


def draft_text(profile: Profile, catalog: Catalog) -> str:
    """The content of the draft of a profile without its time: what decides whether a new draft is worth writing."""
    return json.dumps(_envelope(profile, catalog), ensure_ascii=False)


def save_draft(root: Path, profile: Profile, catalog: Catalog) -> None:
    """Write the draft through a temporary file, so that a failed write never leaves half of one. Raises OSError."""
    envelope = _envelope(profile, catalog)
    envelope["saved"] = _now()
    data = jsonfile.without_surrogates(json.dumps(envelope, ensure_ascii=False, indent=1) + "\n").replace("\n", "\r\n")
    path = draft_path(root)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(data.encode("utf-8"))
        os.replace(temporary, path)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def load_draft(root: Path, catalog: Catalog) -> tuple[Profile, list[str]] | None:
    """The profile of the draft with its warnings, or None when there is no draft. Raises ValueError for a damaged one."""
    path = draft_path(root)
    if not path.is_file():
        return None
    data = jsonfile.read(path, file_limit=PROFILE_MAX_BYTES, json_limit=PROFILE_MAX_BYTES, nulls=True)
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("profile"), dict):
        raise ValueError(f"{path.name}: not a draft of WinKickOff")
    profile, warnings = Profile.from_dict(data["profile"], catalog)
    original = data.get("path")
    profile.path = Path(original) if isinstance(original, str) and original else None
    return profile, warnings


def drop_draft(root: Path) -> None:
    with contextlib.suppress(OSError):
        draft_path(root).unlink(missing_ok=True)
