#!/usr/bin/python

# AIDEV-NOTE: This is the remote-side module for fsbuilder.
# It handles all filesystem operations on the target host.
# Template rendering happens in the action plugin (controller-side) before this runs.

from __future__ import annotations

DOCUMENTATION = r"""
---
module: fsbuilder
short_description: Consolidate multiple filesystem operations into a single task
version_added: "0.1.0"
description:
  - Manages filesystem objects (files, directories, links) with a single task.
  - Supports template rendering (via action plugin), copy, mkdir, touch, rm,
    symlink, hardlink, lineinfile, and blockinfile operations.
  - Each invocation handles a single item (Ansible loop handles iteration).
options:
  dest:
    description: Target filesystem path.
    type: path
    required: true
  src:
    description:
      - Source file path. For copy/template states, the source file.
      - For link/hard states, the link target.
      - Mutually exclusive with C(content).
    type: path
  state:
    description: The desired filesystem state.
    type: str
    default: template
    choices:
      - template
      - copy
      - directory
      - exists
      - touch
      - absent
      - link
      - hard
      - lineinfile
      - blockinfile
  content:
    description:
      - Literal content to write to dest.
      - Mutually exclusive with C(src).
    type: str
  force:
    description: Force replacement of conflicting existing paths.
    type: bool
    default: false
  force_backup:
    description: When force is true, rename existing path instead of deleting.
    type: bool
    default: false
  backup:
    description: Create timestamped backup before overwriting.
    type: bool
    default: false
  remote_src:
    description: If true, src refers to a path on the remote host.
    type: bool
    default: false
  makedirs:
    description: Create parent directories if they don't exist.
    type: bool
    default: false
  validate:
    description:
      - Command to validate file before moving into place.
      - Must contain C(%s) placeholder for the temp file path.
    type: str
  recurse:
    description: For state=directory, apply attributes recursively.
    type: bool
    default: false
  follow:
    description: Follow symlinks when setting attributes.
    type: bool
    default: true
  access_time:
    description: For state=touch, set file access time (epoch or datetime string).
    type: str
  modification_time:
    description: For state=touch, set file modification time (epoch or datetime string).
    type: str
  creates:
    description: Skip this item if the specified path exists.
    type: path
  removes:
    description: Skip this item if the specified path does not exist.
    type: path
  on_error:
    description: Error handling strategy.
    type: str
    default: fail
    choices: [fail, continue]
  line:
    description: For state=lineinfile, the line to ensure present/absent.
    type: str
  regexp:
    description: For state=lineinfile, regex pattern to match.
    type: str
  insertafter:
    description: Insert after matching line. Special value EOF appends.
    type: str
  insertbefore:
    description: Insert before matching line. Special value BOF prepends.
    type: str
  line_state:
    description: For state=lineinfile, whether line should be present or absent.
    type: str
    default: present
    choices: [present, absent]
  block:
    description: For state=blockinfile, the block content.
    type: str
  marker:
    description: For state=blockinfile, marker template with {mark} placeholder.
    type: str
    default: "# {mark} MANAGED BLOCK"
  marker_begin:
    description: String to replace {mark} in opening marker.
    type: str
    default: BEGIN
  marker_end:
    description: String to replace {mark} in closing marker.
    type: str
    default: END
  block_state:
    description: For state=blockinfile, whether block should be present or absent.
    type: str
    default: present
    choices: [present, absent]
author:
  - Sean
"""

EXAMPLES = r"""
- name: Create a directory
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp
    state: directory
    mode: "0755"

- name: Write content to a file
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/config.ini
    state: copy
    content: |
      [main]
      setting = value

- name: Copy a file from the controller
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/static.dat
    state: copy

- name: Render a Jinja2 template (default state)
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/config.ini
    # state: template is the default; renders config.ini.j2

- name: Render an inline template
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/version.txt
    state: template
    content: "version={{ app_version }}"

- name: Create a symlink
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/current
    state: link
    src: /opt/myapp/releases/v2.1

- name: Create a hard link
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/hardlink.txt
    state: hard
    src: /etc/myapp/original.txt

- name: Ensure a file exists (empty if new)
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/flag
    state: exists

- name: Touch a file (always update timestamp)
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/.last-deploy
    state: touch

- name: Remove a file
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/legacy.conf
    state: absent

- name: Remove files matching a glob
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/myapp/conf.d/*.rpmsave
    state: absent

- name: Ensure a line is present in sshd_config
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/ssh/sshd_config
    state: lineinfile
    regexp: "^PermitRootLogin"
    line: "PermitRootLogin no"

- name: Manage a block in /etc/hosts
  linsomniac.fsbuilder.fsbuilder:
    dest: /etc/hosts
    state: blockinfile
    marker: "# {mark} ANSIBLE MANAGED - myapp"
    block: |
      192.168.1.10 app1.internal
      192.168.1.11 app2.internal

- name: Deploy myapp - comprehensive example with loop
  linsomniac.fsbuilder.fsbuilder:
    owner: root
    group: myapp
    mode: "0644"
  loop:
    - dest: /etc/myapp/conf.d
      state: directory
      mode: "0755"
    - dest: /etc/myapp/config.ini
      validate: "myapp --check-config %s"
      backup: true
    - dest: /etc/myapp/version.txt
      state: template
      content: "version={{ app_version }}"
    - dest: /etc/myapp/static.dat
      state: copy
    - dest: /etc/myapp/current
      state: link
      src: /opt/myapp/releases/v2.1
    - dest: /etc/myapp/.last-deploy
      state: touch
    - dest: /etc/myapp/legacy.conf
      state: absent
"""

RETURN = r"""
changed:
  description: Whether any change was made.
  type: bool
  returned: always
dest:
  description: The target path.
  type: str
  returned: always
state:
  description: The state that was applied.
  type: str
  returned: always
diff:
  description: Before/after diff when diff mode is enabled.
  type: dict
  returned: when diff mode is on and content changed
backup_file:
  description: Path to backup file if backup was created.
  type: str
  returned: when backup is created
msg:
  description: Human-readable result message.
  type: str
  returned: always
"""

import contextlib  # noqa: E402
import glob  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

# AIDEV-NOTE: We import constants from module_utils. For collection usage,
# Ansible resolves this via the collection namespace. For role-level usage,
# the module_utils path must be on sys.path (handled by Ansible's loader).
try:
    from ansible_collections.linsomniac.fsbuilder.plugins.module_utils.fsbuilder_common import (
        NO_VALIDATE_STATES,
        VALID_STATES,
    )
except ImportError:
    # Fallback for role-level or direct testing
    from ansible.module_utils.fsbuilder_common import (  # type: ignore[no-redef]
        NO_VALIDATE_STATES,
        VALID_STATES,
    )


def build_argument_spec() -> dict[str, Any]:
    """Build the argument spec for the fsbuilder module."""
    return {
        "dest": {"type": "path", "required": True},
        "src": {"type": "path"},
        "state": {
            "type": "str",
            "default": "template",
            "choices": VALID_STATES,
        },
        "content": {"type": "str"},
        "force": {"type": "bool", "default": False},
        "force_backup": {"type": "bool", "default": False},
        "backup": {"type": "bool", "default": False},
        "remote_src": {"type": "bool", "default": False},
        "makedirs": {"type": "bool", "default": False},
        "validate": {"type": "str"},
        "recurse": {"type": "bool", "default": False},
        "follow": {"type": "bool", "default": True},
        "access_time": {"type": "str"},
        "modification_time": {"type": "str"},
        "creates": {"type": "path"},
        "removes": {"type": "path"},
        "on_error": {
            "type": "str",
            "default": "fail",
            "choices": ["fail", "continue"],
        },
        # lineinfile parameters
        "line": {"type": "str"},
        "regexp": {"type": "str"},
        "insertafter": {"type": "str"},
        "insertbefore": {"type": "str"},
        "line_state": {
            "type": "str",
            "default": "present",
            "choices": ["present", "absent"],
        },
        # blockinfile parameters
        "block": {"type": "str"},
        "marker": {"type": "str", "default": "# {mark} MANAGED BLOCK"},
        "marker_begin": {"type": "str", "default": "BEGIN"},
        "marker_end": {"type": "str", "default": "END"},
        "block_state": {
            "type": "str",
            "default": "present",
            "choices": ["present", "absent"],
        },
    }


class FSBuilder:
    """Main class that dispatches to per-state handler methods.

    AIDEV-NOTE: Each handler follows the idempotency contract:
    1. Check current state
    2. Compare with desired state
    3. If correct, return changed=False
    4. If check_mode, return changed=True without modifying
    5. Perform operation, return changed=True
    """

    # Map state names to handler methods
    STATE_HANDLERS: dict[str, str] = {
        "copy": "_handle_copy",
        "template": "_handle_copy",  # Action plugin converts template -> copy
        "directory": "_handle_directory",
        "exists": "_handle_exists",
        "touch": "_handle_touch",
        "absent": "_handle_absent",
        "link": "_handle_link",
        "hard": "_handle_hard",
        "lineinfile": "_handle_lineinfile",
        "blockinfile": "_handle_blockinfile",
    }

    def __init__(self, module: AnsibleModule) -> None:
        self.module = module

    def run(self) -> dict[str, Any]:
        """Main entry point: dispatch to the appropriate state handler."""
        params = self.module.params
        state = params["state"]
        dest = params["dest"]
        validate = params.get("validate")

        # Warn if validate is set for states that don't produce files
        if validate and state in NO_VALIDATE_STATES:
            self.module.warn(
                f"'validate' is ignored for state '{state}' (only applies to file-content states)"
            )

        # Check creates/removes conditionals
        skip_result = self._check_creates_removes(params)
        if skip_result is not None:
            return skip_result

        # Dispatch to handler
        handler_name = self.STATE_HANDLERS.get(state)
        if handler_name is None:
            self.module.fail_json(msg=f"Unknown state: {state}", dest=dest, state=state)
            return {}  # unreachable

        handler = getattr(self, handler_name)  # type: ignore[arg-type]
        result: dict[str, Any] = handler(params)

        # Ensure standard fields are present
        result.setdefault("dest", dest)
        result.setdefault("state", state)
        result.setdefault("msg", "")

        return result

    def _check_creates_removes(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Check creates/removes conditionals. Returns skip result or None."""
        creates = params.get("creates")
        removes = params.get("removes")
        dest = params["dest"]
        state = params["state"]

        if creates and os.path.exists(creates):
            return {
                "dest": dest,
                "state": state,
                "changed": False,
                "skipped": True,
                "skip_reason": f"'creates' path exists: {creates}",
                "msg": f"Skipped: '{creates}' exists",
            }

        if removes and not os.path.exists(removes):
            return {
                "dest": dest,
                "state": state,
                "changed": False,
                "skipped": True,
                "skip_reason": f"'removes' path does not exist: {removes}",
                "msg": f"Skipped: '{removes}' does not exist",
            }

        return None

    def _apply_attributes(self, path: str, params: dict[str, Any], changed: bool) -> bool:
        """Apply file attributes (owner, group, mode) using Ansible's built-in mechanism."""
        file_args = self.module.load_file_common_arguments(params)
        file_args["path"] = path
        result: bool = self.module.set_fs_attributes_if_different(file_args, changed)
        return result

    def _makedirs(self, path: str, params: dict[str, Any]) -> bool:
        """Create parent directories if makedirs=True.

        Returns True if directories were created.
        """
        if not params.get("makedirs"):
            return False

        parent = os.path.dirname(path)
        if os.path.isdir(parent):
            return False

        if self.module.check_mode:
            return True

        os.makedirs(parent, mode=0o0755, exist_ok=True)

        # Apply owner/group to created parents if specified
        owner = params.get("owner")
        group = params.get("group")
        if owner or group:
            self.module.set_owner_if_different(parent, owner, False)
            self.module.set_group_if_different(parent, group, False)

        return True

    def _validate_file(self, tmp_path: str, validate_cmd: str) -> None:
        """Run a validation command against a temp file. Fails module on error."""
        if "%s" not in validate_cmd:
            self.module.fail_json(msg=f"validate command must contain %s: {validate_cmd}")

        cmd = validate_cmd % tmp_path
        rc, stdout, stderr = self.module.run_command(cmd)
        if rc != 0:
            # Clean up temp file before failing
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            self.module.fail_json(
                msg=f"Validation failed: {cmd}",
                rc=rc,
                stdout=stdout,
                stderr=stderr,
            )

    def _write_content(
        self,
        dest: str,
        content: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomic write: write to temp, validate, backup, move into place.

        Returns a result dict with changed, diff, backup_file keys.
        """
        result: dict[str, Any] = {"changed": False, "dest": dest}

        # Compare with existing content
        content_bytes = content.encode("utf-8")
        if os.path.isfile(dest):
            with open(dest, "rb") as f:
                existing = f.read()
            if existing == content_bytes:
                return result  # No change needed

        result["changed"] = True

        # Diff support
        if self.module._diff:
            before = ""
            if os.path.isfile(dest):
                try:
                    with open(dest, errors="surrogateescape") as f:
                        before = f.read()
                except Exception:
                    before = "<binary or unreadable>"
            result["diff"] = {
                "before": before,
                "after": content,
                "before_header": dest,
                "after_header": dest,
            }

        if self.module.check_mode:
            return result

        # Write to temp file in same directory as dest
        dest_dir = os.path.dirname(dest) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dest_dir)
        try:
            os.write(fd, content_bytes)
            os.close(fd)

            # Validate if requested
            validate = params.get("validate")
            if validate:
                self._validate_file(tmp_path, validate)

            # Backup if requested
            if params.get("backup") and os.path.isfile(dest):
                result["backup_file"] = self.module.backup_local(dest)

            # Atomic move
            self.module.atomic_move(tmp_path, dest)
        except Exception:
            # Clean up temp on failure
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

        return result

    def _force_remove(self, dest: str, params: dict[str, Any]) -> None:
        """Handle force removal with optional backup."""
        if params.get("force_backup"):
            backup_dest = dest + ".old"
            if os.path.exists(backup_dest):
                backup_dest = f"{dest}.old.{int(time.time())}"
            os.rename(dest, backup_dest)
        else:
            if os.path.isdir(dest) and not os.path.islink(dest):
                shutil.rmtree(dest)
            else:
                os.unlink(dest)

    # -- State handlers (stubs for Phase 1, implemented in Phase 2+) --

    def _handle_copy(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: copy (and template after action plugin conversion).

        AIDEV-NOTE: The 'remote_src' parameter is handled by the action plugin
        (Phase 3). When remote_src=False, the action plugin transfers the file
        to a temp path on the remote host and updates 'src' to that temp path.
        When remote_src=True, the action plugin passes 'src' through unchanged.
        By the time this handler runs, 'src' always refers to a remote path.
        """
        dest = params["dest"]
        content = params.get("content")
        src = params.get("src")

        if content is not None and src is not None:
            self.module.fail_json(
                msg="'content' and 'src' are mutually exclusive",
                dest=dest,
                state=params["state"],
            )

        self._makedirs(dest, params)

        # Handle dest conflicts for content-based writes
        if content is not None and os.path.exists(dest) and not os.path.isfile(dest):
            if not params.get("force"):
                self.module.fail_json(
                    msg=f"Destination exists but is not a regular file: {dest}. Use force=true.",
                    dest=dest,
                    state=params["state"],
                )
            if not self.module.check_mode:
                self._force_remove(dest, params)

        if content is not None:
            # Content-based write
            result = self._write_content(dest, content, params)
            if not self.module.check_mode:
                result["changed"] = self._apply_attributes(dest, params, result["changed"])
            result["msg"] = "content updated" if result["changed"] else "content already correct"
            return result

        if src is not None:
            # Source-based copy (src is a remote path at this point)
            return self._copy_from_src(dest, src, params)

        self.module.fail_json(
            msg="Either 'content' or 'src' must be provided for state=copy",
            dest=dest,
            state=params["state"],
        )
        return {}  # unreachable, satisfies type checker

    def _copy_from_src(self, dest: str, src: str, params: dict[str, Any]) -> dict[str, Any]:
        """Copy from a source file (remote path) to dest.

        AIDEV-NOTE: We copy src to a temp file first, then atomic_move the temp
        to dest. This preserves the source file (important for remote_src=true).
        When the action plugin transfers a file, src is already a temp path that
        can be moved directly -- but we still copy-then-move for safety.
        """
        result: dict[str, Any] = {"changed": False, "dest": dest}

        if not os.path.exists(src):
            self.module.fail_json(msg=f"Source file not found: {src}", dest=dest)

        # Handle dest conflicts (e.g., dest is a directory or symlink)
        if os.path.exists(dest) and not os.path.isfile(dest):
            if not params.get("force"):
                self.module.fail_json(
                    msg=f"Destination exists but is not a regular file: {dest}. Use force=true.",
                    dest=dest,
                    state=params["state"],
                )
            if not self.module.check_mode:
                self._force_remove(dest, params)

        # Compare checksums
        src_checksum = self.module.sha256(src)
        if os.path.isfile(dest):
            dest_checksum = self.module.sha256(dest)
            if src_checksum == dest_checksum:
                # Content matches, just check attributes
                result["changed"] = self._apply_attributes(dest, params, False)
                result["msg"] = "file already correct"
                return result

        result["changed"] = True

        # Diff support
        if self.module._diff:
            before = ""
            after = ""
            try:
                if os.path.isfile(dest):
                    with open(dest, errors="surrogateescape") as f:
                        before = f.read()
                with open(src, errors="surrogateescape") as f:
                    after = f.read()
            except Exception:
                before = "<binary or unreadable>"
                after = "<binary or unreadable>"
            result["diff"] = {
                "before": before,
                "after": after,
                "before_header": dest,
                "after_header": dest,
            }

        if self.module.check_mode:
            result["msg"] = "file would be updated"
            return result

        # Copy src to a temp file to avoid destroying the source
        dest_dir = os.path.dirname(dest) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dest_dir)
        try:
            os.close(fd)
            shutil.copy2(src, tmp_path)

            # Validate against the temp copy if requested
            validate = params.get("validate")
            if validate:
                self._validate_file(tmp_path, validate)

            # Backup if requested
            if params.get("backup") and os.path.isfile(dest):
                result["backup_file"] = self.module.backup_local(dest)

            # Atomic move temp -> dest (preserves src)
            self.module.atomic_move(tmp_path, dest)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

        result["changed"] = self._apply_attributes(dest, params, result["changed"])
        result["msg"] = "file updated"
        return result

    def _handle_directory(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: directory."""
        dest = params["dest"].rstrip("/")
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "directory"}

        self._makedirs(dest, params)

        if os.path.isdir(dest) and not os.path.islink(dest):
            # Directory already exists
            result["changed"] = self._apply_attributes(dest, params, False)

            # Handle recurse
            if params.get("recurse"):
                for root, dirs, files in os.walk(dest):
                    for d in dirs:
                        dpath = os.path.join(root, d)
                        result["changed"] = self._apply_attributes(dpath, params, result["changed"])
                    for f in files:
                        fpath = os.path.join(root, f)
                        result["changed"] = self._apply_attributes(fpath, params, result["changed"])

            result["msg"] = (
                "directory attributes changed" if result["changed"] else "directory already exists"
            )
            return result

        if os.path.exists(dest) or os.path.islink(dest):
            # Something exists but it's not a directory
            if not params.get("force"):
                self.module.fail_json(
                    msg=f"Path exists but is not a directory: {dest}. Use force=true to replace.",
                    dest=dest,
                    state="directory",
                )
            if not self.module.check_mode:
                self._force_remove(dest, params)

        result["changed"] = True
        if self.module.check_mode:
            result["msg"] = "directory would be created"
            return result

        os.makedirs(dest, exist_ok=True)
        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "directory created"
        return result

    def _handle_exists(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: exists - ensure file exists, create empty if missing."""
        dest = params["dest"]
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "exists"}

        self._makedirs(dest, params)

        if os.path.isfile(dest) and not os.path.islink(dest):
            result["changed"] = self._apply_attributes(dest, params, False)
            result["msg"] = "file already exists"
            return result

        if (os.path.exists(dest) or os.path.islink(dest)) and not os.path.isfile(dest):
            if not params.get("force"):
                self.module.fail_json(
                    msg=f"Path exists but is not a regular file: {dest}. Use force=true.",
                    dest=dest,
                    state="exists",
                )
            if not self.module.check_mode:
                self._force_remove(dest, params)

        result["changed"] = True
        if self.module.check_mode:
            result["msg"] = "file would be created"
            return result

        # Create empty file
        with open(dest, "a"):
            pass

        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "file created"
        return result

    def _handle_touch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: touch - always reports changed."""
        dest = params["dest"]
        result: dict[str, Any] = {"changed": True, "dest": dest, "state": "touch"}

        self._makedirs(dest, params)

        if self.module.check_mode:
            result["msg"] = "file would be touched"
            return result

        # Create if doesn't exist
        if not os.path.exists(dest):
            with open(dest, "a"):
                pass

        # Parse times
        atime = self._parse_time(params.get("access_time"))
        mtime = self._parse_time(params.get("modification_time"))

        now = time.time()
        if atime is None:
            atime = now
        if mtime is None:
            mtime = now

        os.utime(dest, (atime, mtime))

        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "file touched"
        return result

    def _parse_time(self, time_str: str | None) -> float | None:
        """Parse a time string as epoch seconds or datetime."""
        if time_str is None:
            return None
        try:
            return float(time_str)
        except ValueError:
            pass
        # Try common datetime formats
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(time_str, fmt)
                return dt.timestamp()
            except ValueError:
                continue
        self.module.fail_json(msg=f"Cannot parse time value: {time_str}")
        return None  # unreachable

    def _handle_absent(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: absent - remove file/directory, supports globs."""
        dest = params["dest"]
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "absent"}

        basename = os.path.basename(dest)
        # Check for glob characters
        has_glob = any(c in basename for c in ("*", "?", "["))

        if has_glob:
            matches = glob.glob(dest)
            if not matches:
                result["msg"] = "no paths matched glob pattern"
                return result

            result["changed"] = True

            if self.module._diff:
                result["diff"] = {
                    "before": "\n".join(matches) + "\n",
                    "after": "",
                    "before_header": f"glob: {dest}",
                    "after_header": f"glob: {dest}",
                }

            if self.module.check_mode:
                result["msg"] = f"{len(matches)} path(s) would be removed"
                return result

            for path in matches:
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.unlink(path)

            result["msg"] = f"{len(matches)} path(s) removed"
            return result

        # Non-glob removal
        if not os.path.exists(dest) and not os.path.islink(dest):
            result["msg"] = "path does not exist"
            return result

        result["changed"] = True

        if self.module._diff:
            before_content = ""
            if os.path.isfile(dest):
                try:
                    with open(dest, errors="surrogateescape") as f:
                        before_content = f.read()
                except Exception:
                    before_content = "<binary or unreadable>"
            elif os.path.isdir(dest):
                try:
                    entries = os.listdir(dest)
                    before_content = "\n".join(entries) + "\n" if entries else ""
                except Exception:
                    before_content = "<unreadable>"
            result["diff"] = {
                "before": before_content,
                "after": "",
                "before_header": dest,
                "after_header": dest,
            }

        if self.module.check_mode:
            result["msg"] = "path would be removed"
            return result

        if os.path.isdir(dest) and not os.path.islink(dest):
            shutil.rmtree(dest)
        else:
            os.unlink(dest)

        result["msg"] = "path removed"
        return result

    def _handle_link(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: link - create symbolic link."""
        dest = params["dest"]
        src: str | None = params.get("src")
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "link"}

        if not src:
            self.module.fail_json(msg="'src' is required for state=link", dest=dest, state="link")
            return {}  # unreachable

        self._makedirs(dest, params)

        # Check if correct symlink already exists
        if os.path.islink(dest):
            current_target = os.readlink(dest)
            if current_target == src:
                result["changed"] = self._apply_attributes(dest, params, False)
                result["msg"] = "symlink already correct"
                return result

        # Something exists at dest but it's wrong
        if os.path.exists(dest) or os.path.islink(dest):
            if not params.get("force"):
                self.module.fail_json(
                    msg=f"Path exists at {dest} but is not the correct symlink. Use force=true.",
                    dest=dest,
                    state="link",
                )
            result["changed"] = True
            if not self.module.check_mode:
                self._force_remove(dest, params)
        else:
            result["changed"] = True

        if self.module.check_mode:
            result["msg"] = "symlink would be created"
            return result

        os.symlink(src, dest)
        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "symlink created"
        return result

    def _handle_hard(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: hard - create hard link."""
        dest = params["dest"]
        src: str | None = params.get("src")
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "hard"}

        if not src:
            self.module.fail_json(msg="'src' is required for state=hard", dest=dest, state="hard")
            return {}  # unreachable

        self._makedirs(dest, params)

        # Check if dest exists and is already a hard link to src
        if (
            os.path.exists(dest)
            and os.path.exists(src)
            and os.stat(dest).st_ino == os.stat(src).st_ino
        ):
            result["changed"] = self._apply_attributes(dest, params, False)
            result["msg"] = "hard link already correct"
            return result

        if os.path.exists(dest) or os.path.islink(dest):
            if not params.get("force"):
                self.module.fail_json(
                    msg=f"Path exists at {dest} but is not the correct hard link. Use force=true.",
                    dest=dest,
                    state="hard",
                )
            result["changed"] = True
            if not self.module.check_mode:
                if params.get("backup") and os.path.isfile(dest):
                    result["backup_file"] = self.module.backup_local(dest)
                self._force_remove(dest, params)
        else:
            result["changed"] = True

        if not os.path.exists(src):
            self.module.fail_json(msg=f"Source file does not exist: {src}", dest=dest, state="hard")

        if self.module.check_mode:
            result["msg"] = "hard link would be created"
            return result

        os.link(src, dest)
        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "hard link created"
        return result

    def _handle_lineinfile(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: lineinfile."""
        dest = params["dest"]
        line = params.get("line")
        regexp = params.get("regexp")
        insertafter = params.get("insertafter")
        insertbefore = params.get("insertbefore")
        line_state = params.get("line_state", "present")
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "lineinfile"}

        # Validation
        if insertafter is not None and insertbefore is not None:
            self.module.fail_json(
                msg="'insertafter' and 'insertbefore' are mutually exclusive",
                dest=dest,
                state="lineinfile",
            )

        if line_state == "present" and line is None:
            self.module.fail_json(
                msg="'line' is required when line_state=present",
                dest=dest,
                state="lineinfile",
            )

        if line_state == "absent" and line is None and regexp is None:
            self.module.fail_json(
                msg="'line' or 'regexp' is required when line_state=absent",
                dest=dest,
                state="lineinfile",
            )

        self._makedirs(dest, params)

        # Read existing content
        lines: list[str] = []
        if os.path.isfile(dest):
            with open(dest, errors="surrogateescape") as f:
                lines = f.readlines()
        elif line_state == "absent":
            # File doesn't exist, nothing to remove
            result["msg"] = "file does not exist, nothing to remove"
            return result

        original_lines = list(lines)

        if line_state == "present":
            lines = self._lineinfile_present(lines, line, regexp, insertafter, insertbefore)
        else:
            lines = self._lineinfile_absent(lines, line, regexp)

        # Compare
        if lines == original_lines:
            result["changed"] = self._apply_attributes(dest, params, False)
            result["msg"] = "line already correct"
            return result

        new_content = "".join(lines)
        old_content = "".join(original_lines)

        result["changed"] = True

        if self.module._diff:
            result["diff"] = {
                "before": old_content,
                "after": new_content,
                "before_header": dest,
                "after_header": dest,
            }

        if self.module.check_mode:
            result["msg"] = "line would be updated"
            return result

        write_result = self._write_content(dest, new_content, params)
        result.update({k: v for k, v in write_result.items() if k != "changed"})
        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "line updated"
        return result

    def _lineinfile_present(
        self,
        lines: list[str],
        line: str | None,
        regexp: str | None,
        insertafter: str | None,
        insertbefore: str | None,
    ) -> list[str]:
        """Handle lineinfile present logic. Returns modified lines."""
        assert line is not None  # validated before calling

        # Ensure line has newline
        line_with_nl = line + "\n" if not line.endswith("\n") else line

        if regexp:
            pattern = re.compile(regexp)
            # Find last match
            last_match_idx = None
            for i, existing_line in enumerate(lines):
                if pattern.search(existing_line):
                    last_match_idx = i

            if last_match_idx is not None:
                # Replace the matched line
                if lines[last_match_idx].rstrip("\n\r") != line.rstrip("\n\r"):
                    lines[last_match_idx] = line_with_nl
                return lines
            # No match found, fall through to insert logic

        else:
            # No regexp - check if exact line exists
            for existing_line in lines:
                if existing_line.rstrip("\n\r") == line.rstrip("\n\r"):
                    return lines  # Already present

        # Insert the line
        if insertbefore is not None:
            if insertbefore == "BOF":
                lines.insert(0, line_with_nl)
            else:
                pattern = re.compile(insertbefore)
                last_match_idx = None
                for i, existing_line in enumerate(lines):
                    if pattern.search(existing_line):
                        last_match_idx = i
                if last_match_idx is not None:
                    lines.insert(last_match_idx, line_with_nl)
                else:
                    lines.append(line_with_nl)
        elif insertafter is not None and insertafter != "EOF":
            pattern = re.compile(insertafter)
            last_match_idx = None
            for i, existing_line in enumerate(lines):
                if pattern.search(existing_line):
                    last_match_idx = i
            if last_match_idx is not None:
                lines.insert(last_match_idx + 1, line_with_nl)
            else:
                lines.append(line_with_nl)
        else:
            # Default: EOF
            # Ensure file ends with newline before appending
            if lines and not lines[-1].endswith("\n"):
                lines[-1] = lines[-1] + "\n"
            lines.append(line_with_nl)

        return lines

    def _lineinfile_absent(
        self,
        lines: list[str],
        line: str | None,
        regexp: str | None,
    ) -> list[str]:
        """Handle lineinfile absent logic. Returns modified lines."""
        if regexp:
            pattern = re.compile(regexp)
            return [ln for ln in lines if not pattern.search(ln)]
        elif line is not None:
            return [ln for ln in lines if ln.rstrip("\n\r") != line.rstrip("\n\r")]
        return lines

    def _handle_blockinfile(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle state: blockinfile."""
        dest = params["dest"]
        block = params.get("block")
        marker = params.get("marker", "# {mark} MANAGED BLOCK")
        marker_begin = params.get("marker_begin", "BEGIN")
        marker_end = params.get("marker_end", "END")
        block_state = params.get("block_state", "present")
        insertafter = params.get("insertafter")
        insertbefore = params.get("insertbefore")
        result: dict[str, Any] = {"changed": False, "dest": dest, "state": "blockinfile"}

        # Validation
        if insertafter is not None and insertbefore is not None:
            self.module.fail_json(
                msg="'insertafter' and 'insertbefore' are mutually exclusive",
                dest=dest,
                state="blockinfile",
            )

        if block_state == "present" and block is None:
            self.module.fail_json(
                msg="'block' is required when block_state=present",
                dest=dest,
                state="blockinfile",
            )

        self._makedirs(dest, params)

        begin_marker = marker.replace("{mark}", marker_begin)
        end_marker = marker.replace("{mark}", marker_end)

        # Read existing content
        lines: list[str] = []
        if os.path.isfile(dest):
            with open(dest, errors="surrogateescape") as f:
                lines = f.readlines()
        elif block_state == "absent":
            result["msg"] = "file does not exist, nothing to remove"
            return result

        original_lines = list(lines)

        if block_state == "present":
            lines = self._blockinfile_present(
                lines, block or "", begin_marker, end_marker, insertafter, insertbefore
            )
        else:
            lines = self._blockinfile_absent(lines, begin_marker, end_marker)

        # Compare
        if lines == original_lines:
            result["changed"] = self._apply_attributes(dest, params, False)
            result["msg"] = "block already correct"
            return result

        new_content = "".join(lines)
        old_content = "".join(original_lines)

        result["changed"] = True

        if self.module._diff:
            result["diff"] = {
                "before": old_content,
                "after": new_content,
                "before_header": dest,
                "after_header": dest,
            }

        if self.module.check_mode:
            result["msg"] = "block would be updated"
            return result

        write_result = self._write_content(dest, new_content, params)
        result.update({k: v for k, v in write_result.items() if k != "changed"})
        result["changed"] = self._apply_attributes(dest, params, True)
        result["msg"] = "block updated"
        return result

    def _blockinfile_present(
        self,
        lines: list[str],
        block: str,
        begin_marker: str,
        end_marker: str,
        insertafter: str | None,
        insertbefore: str | None,
    ) -> list[str]:
        """Handle blockinfile present logic. Returns modified lines."""
        # Ensure block has trailing newline
        if block and not block.endswith("\n"):
            block = block + "\n"

        # Build the full block with markers
        block_lines = [
            begin_marker + "\n",
            *block.splitlines(True),
            end_marker + "\n",
        ]

        # Find existing markers
        begin_idx = None
        end_idx = None
        for i, line in enumerate(lines):
            if line.rstrip("\n\r") == begin_marker:
                begin_idx = i
            if line.rstrip("\n\r") == end_marker and begin_idx is not None:
                end_idx = i
                break  # Use first pair

        if begin_idx is not None and end_idx is not None:
            # Replace existing block
            lines[begin_idx : end_idx + 1] = block_lines
            return lines

        # Insert new block
        if insertbefore is not None:
            if insertbefore == "BOF":
                lines[0:0] = block_lines
            else:
                pattern = re.compile(insertbefore)
                last_match_idx = None
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        last_match_idx = i
                if last_match_idx is not None:
                    lines[last_match_idx:last_match_idx] = block_lines
                else:
                    # No match, append at end
                    if lines and not lines[-1].endswith("\n"):
                        lines[-1] = lines[-1] + "\n"
                    lines.extend(block_lines)
        elif insertafter is not None and insertafter != "EOF":
            pattern = re.compile(insertafter)
            last_match_idx = None
            for i, line in enumerate(lines):
                if pattern.search(line):
                    last_match_idx = i
            if last_match_idx is not None:
                lines[last_match_idx + 1 : last_match_idx + 1] = block_lines
            else:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] = lines[-1] + "\n"
                lines.extend(block_lines)
        else:
            # Default: EOF
            if lines and not lines[-1].endswith("\n"):
                lines[-1] = lines[-1] + "\n"
            lines.extend(block_lines)

        return lines

    def _blockinfile_absent(
        self,
        lines: list[str],
        begin_marker: str,
        end_marker: str,
    ) -> list[str]:
        """Handle blockinfile absent logic. Returns modified lines."""
        begin_idx = None
        end_idx = None
        for i, line in enumerate(lines):
            if line.rstrip("\n\r") == begin_marker:
                begin_idx = i
            if line.rstrip("\n\r") == end_marker and begin_idx is not None:
                end_idx = i
                break

        if begin_idx is not None and end_idx is not None:
            del lines[begin_idx : end_idx + 1]

        return lines


def main() -> None:
    """Module entry point."""
    module = AnsibleModule(
        argument_spec=build_argument_spec(),
        add_file_common_args=True,
        supports_check_mode=True,
        mutually_exclusive=[
            ("content", "src"),
            ("insertafter", "insertbefore"),
        ],
        required_if=[
            ("state", "link", ("src",)),
            ("state", "hard", ("src",)),
        ],
    )

    fsb = FSBuilder(module)

    try:
        result = fsb.run()
    except Exception as e:
        module.fail_json(msg=f"Unexpected error: {e}", exception=str(e))
        return  # unreachable

    module.exit_json(**result)


if __name__ == "__main__":
    main()
