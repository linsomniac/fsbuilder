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

# AIDEV-NOTE: ansible-core 2.20+ requires trust_as_template() to mark file
# content for Jinja2 rendering. Older versions (2.15-2.19) render templates
# without this wrapper. Import conditionally for backward compatibility.
try:
    from ansible.template import trust_as_template
except ImportError:

    def trust_as_template(s: str) -> str:  # type: ignore[misc]
        return s


class ActionModule(ActionBase):
    """Controller-side action plugin for fsbuilder.

    AIDEV-NOTE: This plugin intercepts the task before the module runs on the
    remote host. It handles:
    1. Loop parameter merging (item values override task defaults)
    2. Template rendering (file-based and inline)
    3. Copy file transfer (controller -> remote)
    4. Per-item 'when' evaluation
    5. Per-item handler notification collection
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

        # Step 2: Evaluate per-item 'when' condition
        # AIDEV-NOTE: Per-item 'when' is a fsbuilder-specific parameter that
        # allows conditional execution within loop items. This is separate from
        # Ansible's native task-level 'when' which is handled by the executor.
        when_expr = module_args.pop("when", None)
        if when_expr is not None and not self._evaluate_when(when_expr, task_vars):
            return {
                "changed": False,
                "skipped": True,
                "skip_reason": "Per-item when condition evaluated to False",
            }

        # Step 3: Extract per-item notify before passing to module
        item_notify = module_args.pop("notify", None)

        # Step 4: Determine effective state and preprocess
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

        # Step 5: Execute the module on the remote host
        # AIDEV-NOTE: Use self._task.action to preserve the module name from
        # the task context. When installed as a collection, Ansible sets this
        # to the FQCN (linsomniac.fsbuilder.fsbuilder). When used via role-level
        # library/, it's just "fsbuilder". This avoids breaking role-level usage.
        result: dict[str, Any] = self._execute_module(
            module_name=self._task.action,
            module_args=module_args,
            task_vars=task_vars,
        )

        # Step 6: Collect per-item handler notifications
        self._collect_notifications(result, item_notify)

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

        # AIDEV-NOTE: Use get_real_file() for vault-encrypted file support.
        # This decrypts vault files to a temp location; cleanup_tmp_file()
        # removes the decrypted temp when done.
        real_path = self._loader.get_real_file(source_path)
        try:
            with open(real_path) as f:
                template_data = trust_as_template(f.read())
        finally:
            self._loader.cleanup_tmp_file(real_path)

        # Configure templar for template rendering options
        # AIDEV-NOTE: We use self._templar which has access to all task_vars
        # including facts, inventory variables, group_vars, host_vars, etc.
        self._templar.available_variables = task_vars

        # AIDEV-NOTE: Configure template search paths so that Jinja2
        # {% include %} and {% import %} directives resolve relative to the
        # template's directory and Ansible's search paths.
        searchpath = self._task.get_search_path()
        searchpath.insert(0, os.path.dirname(source_path))
        self._templar.environment.loader.searchpath = searchpath

        # AIDEV-NOTE: Template rendering options (trim_blocks, lstrip_blocks,
        # newline_sequence, output_encoding) are currently stripped and not
        # applied to the Jinja2 environment. Full support would require
        # creating a new templar environment with these overrides, similar to
        # ansible.builtin.template's approach. This is a known limitation.
        # Render the template
        try:
            rendered = self._templar.template(
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
        for key in (
            "newline_sequence",
            "trim_blocks",
            "lstrip_blocks",
            "output_encoding",
        ):
            args.pop(key, None)

        return args

    def _process_template_content(
        self, args: dict[str, Any], task_vars: dict[str, Any]
    ) -> dict[str, Any]:
        """Render an inline content string as a Jinja2 template."""
        content = args.get("content", "")

        self._templar.available_variables = task_vars

        try:
            rendered = self._templar.template(
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

        # AIDEV-NOTE: Use get_real_file() for vault-encrypted file support.
        real_path = self._loader.get_real_file(source_path)
        try:
            # Transfer the file to a temporary location on the remote host
            tmp_src = self._connection._shell.join_path(
                self._connection._shell.tmpdir, os.path.basename(src)
            )
            self._transfer_file(real_path, tmp_src)
            self._fixup_perms2((tmp_src,))
        finally:
            self._loader.cleanup_tmp_file(real_path)

        # Update src to point to the remote temp path
        args["src"] = tmp_src

        return args

    # AIDEV-NOTE: SECURITY: Per-item 'when' values are treated as trusted input,
    # consistent with Ansible's native task-level 'when'. They have full access
    # to task_vars via the Templar. Ansible playbooks are trusted code -- there
    # is no sandboxing or input sanitization layer.
    def _evaluate_when(self, when_expr: bool | str | list[str], task_vars: dict[str, Any]) -> bool:
        """Evaluate a per-item 'when' condition.

        AIDEV-NOTE: This evaluates when expressions using Ansible's Templar,
        similar to how the task executor evaluates task-level 'when'. Accepts:
        - bool: short-circuit (when: true / when: false in YAML)
        - str: evaluate as Jinja2 expression
        - list[str]: AND-evaluate all expressions (Ansible convention)

        Returns True if the item should be executed, False if it should be skipped.
        """
        # Short-circuit for boolean values (YAML `when: true` / `when: false`)
        if isinstance(when_expr, bool):
            return when_expr

        # List form: AND-evaluate all expressions (Ansible convention)
        if isinstance(when_expr, list):
            return all(self._evaluate_when(expr, task_vars) for expr in when_expr)

        # String expression: evaluate via Templar
        self._templar.available_variables = task_vars

        try:
            expr = str(when_expr).strip()
            if not expr.startswith("{{"):
                expr = "{{ " + expr + " }}"

            result = self._templar.template(expr)

            # Boolean coercion: handle string representations
            if isinstance(result, bool):
                return result
            if isinstance(result, str):
                lower = result.strip().lower()
                if lower in ("true", "yes", "1"):
                    return True
                if lower in ("false", "no", "0", ""):
                    return False
            # For non-empty values, treat as truthy
            return bool(result)

        except Exception as e:
            # Truncate expression in error messages to avoid leaking secrets
            expr_display = str(when_expr)[:80]
            raise AnsibleError(
                f"fsbuilder: per-item 'when' evaluation failed: {expr_display}: {e}"
            ) from e

    def _collect_notifications(self, result: dict[str, Any], item_notify: Any) -> None:
        """Collect per-item handler notifications and merge into task notify.

        AIDEV-NOTE: This merges per-item notify values with the task-level
        notify list. Only items that actually changed trigger notifications.
        The task executor reads self._task.notify after the action plugin
        returns to determine which handlers to notify.
        """
        if item_notify is None:
            return

        # Only notify if the item actually changed
        if not result.get("changed", False):
            return

        # Normalize notify to a list with strict type validation
        if isinstance(item_notify, str):
            notify_list = [item_notify]
        elif isinstance(item_notify, list):
            # Validate all elements are strings
            for handler in item_notify:
                if not isinstance(handler, str):
                    raise AnsibleError(
                        f"fsbuilder: 'notify' list elements must be strings, "
                        f"got {type(handler).__name__}"
                    )
            notify_list = item_notify
        else:
            raise AnsibleError(
                f"fsbuilder: 'notify' must be a string or list of strings, "
                f"got {type(item_notify).__name__}"
            )

        # Get existing task-level notify (may be None, str, or list)
        task_notify = getattr(self._task, "notify", None) or []
        if isinstance(task_notify, str):
            task_notify = [task_notify]

        # Merge and deduplicate while preserving order
        merged: list[str] = list(task_notify)
        for handler in notify_list:
            if handler not in merged:
                merged.append(handler)

        # Update task notify
        self._task.notify = merged
