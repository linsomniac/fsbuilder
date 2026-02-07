"""Unit tests for the fsbuilder module.

AIDEV-NOTE: Tests use the conftest.py fixtures for Ansible module test infrastructure.
Each test sets module args via context manager, calls main(), and captures the result
via AnsibleExitJson or AnsibleFailJson exceptions.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from plugins.modules.fsbuilder import main as fsbuilder_main
from tests.unit.conftest import AnsibleExitJson, AnsibleFailJson, extract_result, set_module_args


class TestModuleSkeleton:
    """Phase 1: Verify the module skeleton works."""

    def test_directory_state_creates_dir(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=directory creates a directory."""
        dest = str(tmp_path / "testdir")
        with (
            set_module_args({"dest": dest, "state": "directory"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isdir(dest)

    def test_directory_state_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=directory is idempotent for existing directories."""
        dest = str(tmp_path / "existingdir")
        os.makedirs(dest)
        with (
            set_module_args({"dest": dest, "state": "directory"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False
        assert os.path.isdir(dest)

    def test_copy_with_content(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=copy with content writes a file."""
        dest = str(tmp_path / "testfile.txt")
        with (
            set_module_args({"dest": dest, "state": "copy", "content": "hello world\n"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)
        with open(dest) as f:
            assert f.read() == "hello world\n"

    def test_copy_content_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=copy with same content is idempotent."""
        dest = str(tmp_path / "testfile.txt")
        with open(dest, "w") as f:
            f.write("hello world\n")

        with (
            set_module_args({"dest": dest, "state": "copy", "content": "hello world\n"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_absent_removes_file(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=absent removes a file."""
        dest = str(tmp_path / "removeme.txt")
        with open(dest, "w") as f:
            f.write("delete me")

        with (
            set_module_args({"dest": dest, "state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)

    def test_absent_nonexistent_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=absent for nonexistent path is idempotent."""
        dest = str(tmp_path / "nonexistent.txt")
        with (
            set_module_args({"dest": dest, "state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_exists_creates_file(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=exists creates an empty file."""
        dest = str(tmp_path / "existsfile.txt")
        with (
            set_module_args({"dest": dest, "state": "exists"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)

    def test_touch_always_changed(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=touch always reports changed."""
        dest = str(tmp_path / "touchfile.txt")
        with open(dest, "w") as f:
            f.write("")

        with (
            set_module_args({"dest": dest, "state": "touch"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True

    def test_link_creates_symlink(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=link creates a symlink."""
        src = str(tmp_path / "source.txt")
        dest = str(tmp_path / "mylink")
        with open(src, "w") as f:
            f.write("source content")

        with (
            set_module_args({"dest": dest, "state": "link", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.islink(dest)
        assert os.readlink(dest) == src

    def test_hard_creates_hardlink(self, patch_module: None, tmp_path: Any) -> None:
        """Test that state=hard creates a hard link."""
        src = str(tmp_path / "source.txt")
        dest = str(tmp_path / "hardlink.txt")
        with open(src, "w") as f:
            f.write("source content")

        with (
            set_module_args({"dest": dest, "state": "hard", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)
        assert os.stat(dest).st_ino == os.stat(src).st_ino

    def test_content_and_src_mutually_exclusive(self, patch_module: None, tmp_path: Any) -> None:
        """Test that content and src together causes an error."""
        dest = str(tmp_path / "test.txt")
        src = str(tmp_path / "src.txt")
        with (
            set_module_args({"dest": dest, "state": "copy", "content": "hello", "src": src}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "mutually exclusive" in str(exc_info.value).lower()

    def test_creates_skips_when_exists(self, patch_module: None, tmp_path: Any) -> None:
        """Test that 'creates' parameter skips when path exists."""
        dest = str(tmp_path / "output.txt")
        creates_path = str(tmp_path / "flag.txt")
        with open(creates_path, "w") as f:
            f.write("exists")

        with (
            set_module_args(
                {"dest": dest, "state": "copy", "content": "hello", "creates": creates_path}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result.get("skipped") is True
        assert not os.path.exists(dest)

    def test_removes_skips_when_not_exists(self, patch_module: None, tmp_path: Any) -> None:
        """Test that 'removes' parameter skips when path does not exist."""
        dest = str(tmp_path / "output.txt")
        with open(dest, "w") as f:
            f.write("content")

        with (
            set_module_args(
                {"dest": dest, "state": "absent", "removes": str(tmp_path / "nonexistent")}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result.get("skipped") is True
        assert os.path.exists(dest)  # Not removed

    def test_makedirs_creates_parents(self, patch_module: None, tmp_path: Any) -> None:
        """Test that makedirs creates parent directories."""
        dest = str(tmp_path / "deep" / "nested" / "dir")
        with (
            set_module_args({"dest": dest, "state": "directory", "makedirs": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isdir(dest)

    def test_lineinfile_add_line(self, patch_module: None, tmp_path: Any) -> None:
        """Test that lineinfile adds a line to a file."""
        dest = str(tmp_path / "config.txt")
        with open(dest, "w") as f:
            f.write("line1\nline2\n")

        with (
            set_module_args({"dest": dest, "state": "lineinfile", "line": "line3"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "line3" in content

    def test_blockinfile_add_block(self, patch_module: None, tmp_path: Any) -> None:
        """Test that blockinfile adds a block to a file."""
        dest = str(tmp_path / "config.txt")
        with open(dest, "w") as f:
            f.write("existing content\n")

        with (
            set_module_args(
                {"dest": dest, "state": "blockinfile", "block": "new line 1\nnew line 2\n"}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "# BEGIN MANAGED BLOCK" in content
        assert "new line 1" in content
        assert "# END MANAGED BLOCK" in content
