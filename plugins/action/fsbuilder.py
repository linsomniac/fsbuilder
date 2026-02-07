#!/usr/bin/python

# AIDEV-NOTE: Action plugin for fsbuilder - runs on the Ansible controller.
# Handles template rendering, file transfer, loop parameter merging,
# and per-item when evaluation before delegating to the remote module.

from __future__ import annotations

from typing import Any

from ansible.plugins.action import ActionBase


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

        # Phase 1: pass-through stub - just execute the module with current args
        module_args = self._task.args.copy()

        result: dict[str, Any] = self._execute_module(
            module_name="fsbuilder",
            module_args=module_args,
            task_vars=task_vars,
        )

        return result
