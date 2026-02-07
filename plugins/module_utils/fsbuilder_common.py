# AIDEV-NOTE: Shared constants between action plugin and module.
# Both components import from here to stay in sync on valid states and categories.

from __future__ import annotations

VALID_STATES: list[str] = [
    "template",
    "copy",
    "directory",
    "exists",
    "touch",
    "absent",
    "link",
    "hard",
    "lineinfile",
    "blockinfile",
]

# States that produce file content (used by action plugin for template/copy preprocessing)
FILE_CONTENT_STATES: list[str] = [
    "template",
    "copy",
    "lineinfile",
    "blockinfile",
]

# States where 'validate' parameter is ignored (no file content produced)
NO_VALIDATE_STATES: list[str] = [
    "directory",
    "absent",
    "link",
    "hard",
    "exists",
    "touch",
]
