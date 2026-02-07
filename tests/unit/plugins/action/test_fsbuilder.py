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

    # Mock the loader
    loader = MagicMock()

    # Mock the templar
    templar = MagicMock()

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
        action_module._templar.do_template.return_value = "rendered: hello world"
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
        action_module._templar.do_template.assert_called_once()

    def test_file_based_template_default_src(self, action_module: ActionModule) -> None:
        """Default src is basename(dest) + .j2."""
        action_module._templar.do_template.return_value = "rendered content"
        action_module._find_needle = MagicMock(return_value="/path/to/templates/config.ini.j2")

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
        assert result["state"] == "copy"
        assert result["content"] == "rendered content"
        assert "src" not in result

    def test_dest_ending_with_slash(self, action_module: ActionModule) -> None:
        """Dest ending with / gets src basename appended (minus .j2)."""
        action_module._templar.do_template.return_value = "content"
        action_module._find_needle = MagicMock(return_value="/path/to/templates/app.conf.j2")

        mock_file = MagicMock()
        mock_file.read.return_value = "template"
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", return_value=mock_file):
            args = {"dest": "/etc/myapp/", "state": "template", "src": "app.conf.j2"}
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
