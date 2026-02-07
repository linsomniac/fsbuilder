#!/usr/bin/python

# AIDEV-NOTE: Action plugin for fsbuilder - runs on the Ansible controller.
# Handles template rendering, file transfer, loop parameter merging,
# and per-item when evaluation before delegating to the remote module.
#
# AIDEV-NOTE: Key architectural insight: templates live on the controller,
# modules run on the remote host. This plugin bridges that gap by rendering
# templates and transferring files before the module executes.

from __future__ import annotations

import os
from typing import Any

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    """Controller-side action plugin for fsbuilder.

    AIDEV-NOTE: This plugin intercepts the task before the module runs on the
    remote host. It handles:
    1. Loop parameter merging (item values override task defaults)
    2. Template rendering (file-based and inline)
    3. Copy file transfer (controller -> remote)
    4. Per-item 'when' evaluation (Phase 5)
    5. Per-item handler notification collection (Phase 5)
    """

    TRANSFERS_FILES = True

    def run(
        self, tmp: str | None = None, task_vars: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Main entry point for the action plugin."""
        super().run(tmp, task_vars)
        task_vars = task_vars or {}

        # Step 1: Merge loop parameters
        module_args = self._merge_loop_params(task_vars)

        # Step 2: Determine effective state and preprocess
        state = module_args.get("state", "template")

        try:
            if state == "template":
                module_args = self._process_template(module_args, task_vars)
            elif state == "copy":
                module_args = self._process_copy(module_args, task_vars)
            # All other states pass through unchanged
        except AnsibleError:
            raise
        except Exception as e:
            raise AnsibleError(f"fsbuilder action plugin error: {e}") from e

        # Step 3: Execute the module on the remote host
        result: dict[str, Any] = self._execute_module(
            module_name="fsbuilder",
            module_args=module_args,
            task_vars=task_vars,
        )

        return result

    def _merge_loop_params(self, task_vars: dict[str, Any]) -> dict[str, Any]:
        """Merge loop item parameters over task-level defaults.

        AIDEV-NOTE: When Ansible runs a task with `loop:`, each iteration
        sets the loop variable (default: `item`) in task_vars. If the loop
        item is a dict, its keys override the task-level args. This gives
        per-item override semantics described in the spec.

        Precedence (highest first):
        1. Per-item (loop) values
        2. Explicitly-set task-level values
        3. Parameter defaults
        """
        module_args: dict[str, Any] = self._task.args.copy()

        # Only merge if we're actually in a loop
        if not getattr(self._task, "loop", None):
            return module_args

        # Determine loop variable name
        loop_var = "item"
        loop_control = getattr(self._task, "loop_control", None)
        if loop_control and hasattr(loop_control, "loop_var") and loop_control.loop_var:
            loop_var = loop_control.loop_var

        # Get the current loop item from task_vars
        loop_item = task_vars.get(loop_var)
        if loop_item is None:
            return module_args

        # Only merge if the loop item is a dict
        if isinstance(loop_item, dict):
            # Item values override task-level args
            module_args.update(loop_item)

        return module_args

    def _process_template(
        self, module_args: dict[str, Any], task_vars: dict[str, Any]
    ) -> dict[str, Any]:
        """Process state=template: render template and convert to copy.

        Handles two cases:
        1. File-based template: find .j2 file, render, inject as content
        2. Inline content template: render content string as Jinja2
        """
        args = module_args.copy()
        dest = args.get("dest", "")
        src = args.get("src")
        content = args.get("content")

        if content is not None and src is not None:
            raise AnsibleError(
                "fsbuilder: 'content' and 'src' are mutually exclusive for state=template"
            )

        if content is not None:
            # Inline content template rendering
            return self._process_template_content(args, task_vars)
        else:
            # File-based template rendering
            return self._process_template_file(args, task_vars, dest, src)

    def _process_template_file(
        self,
        args: dict[str, Any],
        task_vars: dict[str, Any],
        dest: str,
        src: str | None,
    ) -> dict[str, Any]:
        """Render a file-based Jinja2 template.

        AIDEV-NOTE: This mirrors how ansible.builtin.template works:
        1. Find the .j2 file on the controller
        2. Read and render it with the Templar
        3. Inject rendered content, change state to copy
        """
        # Determine src: explicit or derive from dest basename + .j2
        if not src:
            src = os.path.basename(dest)
            if not src.endswith(".j2"):
                src = src + ".j2"

        # Handle dest ending in '/': append src basename (strip .j2)
        if dest.endswith("/") or dest.endswith(os.sep):
            basename = os.path.basename(src)
            if basename.endswith(".j2"):
                basename = basename[:-3]
            dest = dest + basename
            args["dest"] = dest

        # Find the template file using Ansible's search paths
        try:
            source_path = self._find_needle("templates", src)
        except AnsibleError as e:
            raise AnsibleError(
                f"fsbuilder: template file not found: '{src}' (searched in templates/ directories)"
            ) from e

        # Read the template source
        with open(source_path) as f:
            template_data = f.read()

        # Configure templar for template rendering options
        # AIDEV-NOTE: We use self._templar which has access to all task_vars
        # including facts, inventory variables, group_vars, host_vars, etc.
        self._templar.available_variables = task_vars

        # Render the template
        try:
            rendered = self._templar.do_template(
                template_data,
                preserve_trailing_newlines=True,
                escape_backslashes=False,
            )
        except Exception as e:
            raise AnsibleError(f"fsbuilder: template rendering failed for '{src}': {e}") from e

        # Inject rendered content and change state to copy
        args["content"] = rendered
        args["state"] = "copy"
        args.pop("src", None)
        # Remove template-specific args that the module doesn't need
        for key in ("newline_sequence", "trim_blocks", "lstrip_blocks", "output_encoding"):
            args.pop(key, None)

        return args

    def _process_template_content(
        self, args: dict[str, Any], task_vars: dict[str, Any]
    ) -> dict[str, Any]:
        """Render an inline content string as a Jinja2 template."""
        content = args.get("content", "")

        self._templar.available_variables = task_vars

        try:
            rendered = self._templar.do_template(
                content,
                preserve_trailing_newlines=True,
                escape_backslashes=False,
            )
        except Exception as e:
            raise AnsibleError(f"fsbuilder: inline template rendering failed: {e}") from e

        args["content"] = rendered
        args["state"] = "copy"
        # Remove template-specific args
        for key in ("newline_sequence", "trim_blocks", "lstrip_blocks", "output_encoding"):
            args.pop(key, None)

        return args

    def _process_copy(
        self, module_args: dict[str, Any], task_vars: dict[str, Any]
    ) -> dict[str, Any]:
        """Process state=copy: transfer files from controller if needed.

        Three cases:
        1. content provided: pass through (module handles content writes)
        2. remote_src=True: pass through (src is already a remote path)
        3. src provided, remote_src=False: transfer from controller to remote
        """
        args = module_args.copy()
        content = args.get("content")
        src = args.get("src")
        remote_src = args.get("remote_src", False)
        dest = args.get("dest", "")

        # Case 1: content-based copy, no file transfer needed
        if content is not None:
            return args

        # Case 2: remote_src, no controller-side handling needed
        if remote_src:
            return args

        # Case 3: controller file -> remote transfer
        if src is None:
            # Derive src from dest basename
            src = os.path.basename(dest)

        # Handle dest ending in '/': append src basename
        if dest.endswith("/") or dest.endswith(os.sep):
            dest = dest + os.path.basename(src)
            args["dest"] = dest

        # Find the source file using Ansible's search paths
        try:
            source_path = self._find_needle("files", src)
        except AnsibleError as e:
            raise AnsibleError(
                f"fsbuilder: source file not found: '{src}' (searched in files/ directories)"
            ) from e

        # Transfer the file to a temporary location on the remote host
        tmp_src = self._connection._shell.join_path(
            self._connection._shell.tmpdir, os.path.basename(src)
        )
        self._transfer_file(source_path, tmp_src)
        self._fixup_perms2((tmp_src,))

        # Update src to point to the remote temp path
        args["src"] = tmp_src

        return args
