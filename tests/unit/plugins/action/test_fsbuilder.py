"""Unit tests for the fsbuilder action plugin.

AIDEV-NOTE: These tests mock the Ansible ActionBase infrastructure since the
action plugin runs on the controller and needs access to _task, _templar,
_connection, _find_needle, _transfer_file, and _execute_module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from plugins.action.fsbuilder import ActionModule


@pytest.fixture
def action_module() -> ActionModule:
    """Create an ActionModule instance with mocked dependencies."""
    # Mock the task
    task = MagicMock()
    task.args = {}
    task.loop = None
    task.loop_control = None
    task.async_val = 0
    task.environment = []

    # Mock the connection
    connection = MagicMock()
    shell = MagicMock()
    shell.tmpdir = "/tmp/.ansible_tmp"
    shell.join_path.side_effect = lambda *parts: "/".join(parts)
    connection._shell = shell

    # Mock the play context
    play_context = MagicMock()

    # Mock the loader (get_real_file returns the same path by default)
    loader = MagicMock()
    loader.get_real_file.side_effect = lambda path, **kw: path
    loader.cleanup_tmp_file.return_value = None

    # Mock the templar
    templar = MagicMock()
    templar.environment = MagicMock()
    templar.environment.loader = MagicMock()
    templar.environment.loader.searchpath = []

    # Mock shared_loader_obj
    shared_loader_obj = MagicMock()

    action = ActionModule(
        task=task,
        connection=connection,
        play_context=play_context,
        loader=loader,
        templar=templar,
        shared_loader_obj=shared_loader_obj,
    )

    return action


class TestLoopParameterMerging:
    """Test _merge_loop_params method."""

    def test_no_loop_returns_task_args(self, action_module: ActionModule) -> None:
        """Without loop, task args are returned unchanged."""
        action_module._task.args = {"dest": "/etc/myapp", "state": "directory", "mode": "0755"}
        action_module._task.loop = None

        result = action_module._merge_loop_params({})
        assert result == {"dest": "/etc/myapp", "state": "directory", "mode": "0755"}

    def test_loop_item_dict_merges_over_task_args(self, action_module: ActionModule) -> None:
        """Loop item dict values override task-level args."""
        action_module._task.args = {"owner": "root", "group": "myapp", "mode": "0644"}
        action_module._task.loop = "{{ items }}"

        task_vars = {"item": {"dest": "/etc/myapp", "state": "directory", "mode": "0755"}}
        result = action_module._merge_loop_params(task_vars)

        assert result["dest"] == "/etc/myapp"
        assert result["state"] == "directory"
        assert result["mode"] == "0755"  # Overridden by item
        assert result["owner"] == "root"  # From task defaults
        assert result["group"] == "myapp"  # From task defaults

    def test_task_defaults_used_when_item_omits_keys(self, action_module: ActionModule) -> None:
        """Task-level args used when item doesn't specify a key."""
        action_module._task.args = {"owner": "root", "mode": "0644"}
        action_module._task.loop = "{{ items }}"

        task_vars = {"item": {"dest": "/etc/myapp/file.txt"}}
        result = action_module._merge_loop_params(task_vars)

        assert result["dest"] == "/etc/myapp/file.txt"
        assert result["owner"] == "root"
        assert result["mode"] == "0644"

    def test_custom_loop_var(self, action_module: ActionModule) -> None:
        """Custom loop_var name from loop_control is respected."""
        action_module._task.args = {"owner": "root"}
        action_module._task.loop = "{{ items }}"
        action_module._task.loop_control = MagicMock()
        action_module._task.loop_control.loop_var = "my_item"

        task_vars = {"my_item": {"dest": "/etc/custom", "state": "touch"}}
        result = action_module._merge_loop_params(task_vars)

        assert result["dest"] == "/etc/custom"
        assert result["state"] == "touch"
        assert result["owner"] == "root"

    def test_non_dict_loop_item_not_merged(self, action_module: ActionModule) -> None:
        """Non-dict loop items are not merged (e.g., string items)."""
        action_module._task.args = {"dest": "/etc/myapp", "state": "directory"}
        action_module._task.loop = "{{ items }}"

        task_vars = {"item": "simple_string_value"}
        result = action_module._merge_loop_params(task_vars)

        assert result == {"dest": "/etc/myapp", "state": "directory"}


class TestTemplateHandling:
    """Test template preprocessing in the action plugin."""

    def test_inline_content_template(self, action_module: ActionModule) -> None:
        """Inline content is rendered and state changed to copy."""
        action_module._templar.template.return_value = "rendered: hello world"
        action_module._task.loop = None

        action_module._task.args = {
            "dest": "/etc/myapp/version.txt",
            "state": "template",
            "content": "rendered: {{ var }}",
        }

        # Call the processing method directly
        args = action_module._task.args.copy()
        result = action_module._process_template_content(args, {"var": "hello world"})

        assert result["state"] == "copy"
        assert result["content"] == "rendered: hello world"
        action_module._templar.template.assert_called_once()

    def test_file_based_template_default_src(self, action_module: ActionModule) -> None:
        """Default src is basename(dest) + .j2."""
        action_module._templar.template.return_value = "rendered content"
        action_module._find_needle = MagicMock(return_value="/path/to/templates/config.ini.j2")
        action_module._task.get_search_path = MagicMock(return_value=["/path/to"])

        mock_file = MagicMock()
        mock_file.read.return_value = "template {{ var }}"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", return_value=mock_file):
            args = {"dest": "/etc/myapp/config.ini", "state": "template"}
            result = action_module._process_template_file(
                args, {"var": "value"}, args["dest"], None
            )

        # Should have searched for config.ini.j2
        action_module._find_needle.assert_called_once_with("templates", "config.ini.j2")
        # Vault support: get_real_file/cleanup_tmp_file called
        action_module._loader.get_real_file.assert_called_once()
        action_module._loader.cleanup_tmp_file.assert_called_once()
        assert result["state"] == "copy"
        assert result["content"] == "rendered content"
        assert "src" not in result

    def test_dest_ending_with_slash(self, action_module: ActionModule) -> None:
        """Dest ending with / gets src basename appended (minus .j2)."""
        action_module._templar.template.return_value = "content"
        action_module._find_needle = MagicMock(return_value="/path/to/templates/app.conf.j2")
        action_module._task.get_search_path = MagicMock(return_value=["/path/to"])

        mock_file = MagicMock()
        mock_file.read.return_value = "template"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", return_value=mock_file):
            args = {
                "dest": "/etc/myapp/",
                "state": "template",
                "src": "app.conf.j2",
            }
            result = action_module._process_template_file(args, {}, args["dest"], args["src"])

        assert result["dest"] == "/etc/myapp/app.conf"

    def test_content_and_src_together_raises_error(self, action_module: ActionModule) -> None:
        """content + src together raises AnsibleError."""
        from ansible.errors import AnsibleError

        args = {
            "dest": "/etc/file.txt",
            "state": "template",
            "content": "inline",
            "src": "file.j2",
        }
        with pytest.raises(AnsibleError, match="mutually exclusive"):
            action_module._process_template(args, {})


class TestCopyFileTransfer:
    """Test copy file transfer preprocessing."""

    def test_content_copy_passes_through(self, action_module: ActionModule) -> None:
        """Copy with content passes through without file transfer."""
        args = {"dest": "/etc/file.txt", "state": "copy", "content": "hello"}
        result = action_module._process_copy(args, {})

        assert result["content"] == "hello"
        assert result["state"] == "copy"

    def test_remote_src_passes_through(self, action_module: ActionModule) -> None:
        """Copy with remote_src=True passes through."""
        args = {
            "dest": "/etc/file.txt",
            "state": "copy",
            "src": "/remote/path/file.txt",
            "remote_src": True,
        }
        result = action_module._process_copy(args, {})

        assert result["src"] == "/remote/path/file.txt"
        # _transfer_file should NOT have been called
        action_module._connection._shell.join_path.assert_not_called()

    def test_controller_file_transfer(self, action_module: ActionModule) -> None:
        """Copy with controller src triggers file transfer."""
        action_module._find_needle = MagicMock(return_value="/local/files/myfile.txt")
        action_module._transfer_file = MagicMock()
        action_module._fixup_perms2 = MagicMock()

        args = {
            "dest": "/etc/myapp/myfile.txt",
            "state": "copy",
            "src": "myfile.txt",
        }
        result = action_module._process_copy(args, {})

        action_module._find_needle.assert_called_once_with("files", "myfile.txt")
        action_module._transfer_file.assert_called_once()
        action_module._fixup_perms2.assert_called_once()
        # Vault support: get_real_file/cleanup_tmp_file called
        action_module._loader.get_real_file.assert_called_once()
        action_module._loader.cleanup_tmp_file.assert_called_once()
        # src should now be the remote temp path
        assert result["src"] != "myfile.txt"

    def test_copy_default_src_from_dest(self, action_module: ActionModule) -> None:
        """When src is not specified, it's derived from dest basename."""
        action_module._find_needle = MagicMock(return_value="/local/files/config.ini")
        action_module._transfer_file = MagicMock()
        action_module._fixup_perms2 = MagicMock()

        args = {"dest": "/etc/myapp/config.ini", "state": "copy"}
        action_module._process_copy(args, {})

        action_module._find_needle.assert_called_once_with("files", "config.ini")


class TestRunDispatch:
    """Test the run() method dispatches correctly per state."""

    def test_run_template_dispatches_to_process_template(self, action_module: ActionModule) -> None:
        """run() with state=template calls _process_template."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "template",
            "content": "{{ var }}",
        }
        action_module._task.loop = None
        action_module._templar.template.return_value = "rendered"
        action_module._execute_module = MagicMock(return_value={"changed": True})

        result = action_module.run(task_vars={})

        # _execute_module should receive state=copy (template converts to copy)
        call_args = action_module._execute_module.call_args
        assert call_args.kwargs["module_args"]["state"] == "copy"
        assert call_args.kwargs["module_args"]["content"] == "rendered"
        assert result == {"changed": True}

    def test_run_directory_passes_through(self, action_module: ActionModule) -> None:
        """run() with state=directory passes args through unchanged."""
        action_module._task.args = {
            "dest": "/etc/myapp",
            "state": "directory",
            "mode": "0755",
        }
        action_module._task.loop = None
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        call_args = action_module._execute_module.call_args
        assert call_args.kwargs["module_args"]["state"] == "directory"
        assert call_args.kwargs["module_args"]["dest"] == "/etc/myapp"

    def test_run_copy_with_content_passes_through(self, action_module: ActionModule) -> None:
        """run() with state=copy and content passes through."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "copy",
            "content": "hello",
        }
        action_module._task.loop = None
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        call_args = action_module._execute_module.call_args
        assert call_args.kwargs["module_args"]["state"] == "copy"
        assert call_args.kwargs["module_args"]["content"] == "hello"


class TestWhenEvaluation:
    """Test per-item 'when' condition evaluation."""

    def test_when_true_executes_module(self, action_module: ActionModule) -> None:
        """When expression evaluates to True: module is executed."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "when": "True",
        }
        action_module._task.loop = None
        action_module._templar.do_template.return_value = "True"
        action_module._execute_module = MagicMock(return_value={"changed": True})

        result = action_module.run(task_vars={})

        action_module._execute_module.assert_called_once()
        assert result == {"changed": True}

    def test_when_false_skips_module(self, action_module: ActionModule) -> None:
        """When expression evaluates to False: module is skipped."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "when": "False",
        }
        action_module._task.loop = None
        action_module._templar.do_template.return_value = "False"
        action_module._execute_module = MagicMock()

        result = action_module.run(task_vars={})

        action_module._execute_module.assert_not_called()
        assert result["skipped"] is True
        assert result["changed"] is False

    def test_when_has_access_to_task_vars(self, action_module: ActionModule) -> None:
        """When expression can access task_vars."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "when": "my_var == 'yes'",
        }
        action_module._task.loop = None
        action_module._templar.do_template.return_value = "True"
        action_module._execute_module = MagicMock(return_value={"changed": True})

        result = action_module.run(task_vars={"my_var": "yes"})

        action_module._execute_module.assert_called_once()
        assert result["changed"] is True

    def test_when_evaluation_error_raises(self, action_module: ActionModule) -> None:
        """When expression evaluation error produces clear failure."""
        from ansible.errors import AnsibleError

        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "when": "undefined_var",
        }
        action_module._task.loop = None
        action_module._templar.do_template.side_effect = Exception("undefined")

        with pytest.raises(AnsibleError, match="when.*evaluation failed"):
            action_module.run(task_vars={})

    def test_when_not_passed_to_module(self, action_module: ActionModule) -> None:
        """'when' is stripped from module_args before passing to module."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "when": "True",
        }
        action_module._task.loop = None
        action_module._templar.do_template.return_value = "True"
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        call_args = action_module._execute_module.call_args
        assert "when" not in call_args.kwargs["module_args"]

    def test_evaluate_when_boolean_coercion(self, action_module: ActionModule) -> None:
        """Boolean string values are properly coerced."""
        action_module._templar.do_template.return_value = "yes"
        assert action_module._evaluate_when("some_expr", {}) is True

        action_module._templar.do_template.return_value = "no"
        assert action_module._evaluate_when("some_expr", {}) is False

        action_module._templar.do_template.return_value = ""
        assert action_module._evaluate_when("some_expr", {}) is False

        action_module._templar.do_template.return_value = True
        assert action_module._evaluate_when("some_expr", {}) is True

        action_module._templar.do_template.return_value = False
        assert action_module._evaluate_when("some_expr", {}) is False

    def test_when_bool_true_shortcircuits(self, action_module: ActionModule) -> None:
        """Boolean True value short-circuits without Templar evaluation."""
        assert action_module._evaluate_when(True, {}) is True
        action_module._templar.do_template.assert_not_called()

    def test_when_bool_false_shortcircuits(self, action_module: ActionModule) -> None:
        """Boolean False value short-circuits without Templar evaluation."""
        assert action_module._evaluate_when(False, {}) is False
        action_module._templar.do_template.assert_not_called()

    def test_when_list_and_evaluates_all(self, action_module: ActionModule) -> None:
        """List of when expressions are AND-evaluated."""
        # Both True -> True
        action_module._templar.do_template.return_value = "True"
        assert action_module._evaluate_when(["expr1", "expr2"], {}) is True

    def test_when_list_short_circuits_on_false(self, action_module: ActionModule) -> None:
        """List of when expressions short-circuits on first False."""
        action_module._templar.do_template.side_effect = ["True", "False"]
        assert action_module._evaluate_when(["expr1", "expr2"], {}) is False


class TestHandlerNotification:
    """Test per-item handler notification collection."""

    def test_notify_collected_when_changed(self, action_module: ActionModule) -> None:
        """Per-item notify is collected when item changed."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": "restart myapp",
        }
        action_module._task.loop = None
        action_module._task.notify = None
        action_module._templar.do_template.return_value = "True"
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        assert action_module._task.notify is not None
        assert "restart myapp" in action_module._task.notify

    def test_notify_not_collected_when_not_changed(self, action_module: ActionModule) -> None:
        """Per-item notify is NOT collected when item did not change."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": "restart myapp",
        }
        action_module._task.loop = None
        action_module._task.notify = None
        action_module._execute_module = MagicMock(return_value={"changed": False})

        action_module.run(task_vars={})

        # notify should remain None (not set)
        assert action_module._task.notify is None

    def test_notify_as_list(self, action_module: ActionModule) -> None:
        """Per-item notify can be a list of handler names."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": ["restart myapp", "reload nginx"],
        }
        action_module._task.loop = None
        action_module._task.notify = None
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        assert action_module._task.notify is not None
        assert "restart myapp" in action_module._task.notify
        assert "reload nginx" in action_module._task.notify

    def test_notify_merged_with_task_notify(self, action_module: ActionModule) -> None:
        """Per-item notify is merged with existing task-level notify."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": "restart myapp",
        }
        action_module._task.loop = None
        action_module._task.notify = ["reload config"]
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        assert "reload config" in action_module._task.notify
        assert "restart myapp" in action_module._task.notify

    def test_notify_deduplicates(self, action_module: ActionModule) -> None:
        """Duplicate handler names are deduplicated."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": "restart myapp",
        }
        action_module._task.loop = None
        action_module._task.notify = ["restart myapp"]
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        assert action_module._task.notify.count("restart myapp") == 1

    def test_notify_not_passed_to_module(self, action_module: ActionModule) -> None:
        """'notify' is stripped from module_args before passing to module."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": "restart myapp",
        }
        action_module._task.loop = None
        action_module._task.notify = None
        action_module._execute_module = MagicMock(return_value={"changed": True})

        action_module.run(task_vars={})

        call_args = action_module._execute_module.call_args
        assert "notify" not in call_args.kwargs["module_args"]

    def test_notify_invalid_type_raises(self, action_module: ActionModule) -> None:
        """Invalid notify type raises AnsibleError."""
        from ansible.errors import AnsibleError

        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "directory",
            "notify": 42,
        }
        action_module._task.loop = None
        action_module._task.notify = None
        action_module._execute_module = MagicMock(return_value={"changed": True})

        with pytest.raises(AnsibleError, match="notify.*must be a string or list"):
            action_module.run(task_vars={})


class TestTemplateRenderingOptions:
    """Test template rendering options are stripped before passing to module."""

    def test_template_options_stripped_from_file_template(
        self, action_module: ActionModule
    ) -> None:
        """Template rendering options are stripped from module args for file templates."""
        action_module._templar.template.return_value = "rendered content"
        action_module._find_needle = MagicMock(return_value="/path/to/templates/config.j2")
        action_module._task.get_search_path = MagicMock(return_value=["/path/to"])

        mock_file = MagicMock()
        mock_file.read.return_value = "template {{ var }}"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        from unittest.mock import patch

        with patch("builtins.open", return_value=mock_file):
            args = {
                "dest": "/etc/myapp/config",
                "state": "template",
                "trim_blocks": True,
                "lstrip_blocks": True,
                "newline_sequence": "\r\n",
                "output_encoding": "utf-8",
            }
            result = action_module._process_template_file(args, {}, args["dest"], None)

        # Template-specific options should be stripped
        assert "trim_blocks" not in result
        assert "lstrip_blocks" not in result
        assert "newline_sequence" not in result
        assert "output_encoding" not in result
        # Content should be injected and state changed to copy
        assert result["state"] == "copy"
        assert result["content"] == "rendered content"

    def test_template_options_stripped_from_inline_template(
        self, action_module: ActionModule
    ) -> None:
        """Template rendering options are stripped from module args for inline templates."""
        action_module._templar.template.return_value = "rendered inline"

        args = {
            "dest": "/etc/myapp/version.txt",
            "state": "template",
            "content": "version={{ app_version }}",
            "trim_blocks": False,
            "lstrip_blocks": False,
            "newline_sequence": "\n",
            "output_encoding": "utf-8",
        }
        result = action_module._process_template_content(args, {"app_version": "1.0"})

        # Template-specific options should be stripped
        assert "trim_blocks" not in result
        assert "lstrip_blocks" not in result
        assert "newline_sequence" not in result
        assert "output_encoding" not in result
        assert result["state"] == "copy"
        assert result["content"] == "rendered inline"

    def test_template_options_do_not_break_run(self, action_module: ActionModule) -> None:
        """Template options in task args don't cause errors during run()."""
        action_module._task.args = {
            "dest": "/etc/file.txt",
            "state": "template",
            "content": "{{ var }}",
            "trim_blocks": True,
            "lstrip_blocks": True,
            "newline_sequence": "\n",
            "output_encoding": "utf-8",
        }
        action_module._task.loop = None
        action_module._templar.template.return_value = "rendered"
        action_module._execute_module = MagicMock(return_value={"changed": True})

        result = action_module.run(task_vars={"var": "value"})

        # Should succeed without errors
        assert result == {"changed": True}
        # Module should NOT receive template-specific args
        call_args = action_module._execute_module.call_args
        module_args = call_args.kwargs["module_args"]
        assert "trim_blocks" not in module_args
        assert "lstrip_blocks" not in module_args
        assert "newline_sequence" not in module_args
        assert "output_encoding" not in module_args
