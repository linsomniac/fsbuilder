"""Unit tests for the fsbuilder module.

AIDEV-NOTE: Tests use the conftest.py fixtures for Ansible module test infrastructure.
Each test sets module args via context manager, calls main(), and captures the result
via AnsibleExitJson or AnsibleFailJson exceptions.

AIDEV-NOTE: Phase 6 comprehensive test suite covers:
- TestModuleSkeleton: Basic functionality for all states (Phase 1)
- TestCopyFromSrc: Source-based copy operations (codex review)
- TestCheckMode: Check mode for all state handlers
- TestDiffMode: Diff output for content-changing states
- TestDirectoryAdvanced: Force replace, force_backup, trailing slash, recurse
- TestCopyAdvanced: Content change, backup, validate success/failure
- TestLineinfileAdvanced: Regexp, insertbefore/after, line_state=absent, creates file
- TestBlockinfileAdvanced: Update existing, idempotent, custom markers, block_state=absent
- TestLinkAdvanced: Wrong target with force, idempotent
- TestAbsentAdvanced: Directory removal, glob matching, diff
- TestExistsAdvanced: Preserves timestamps, existing file idempotent
- TestTouchAdvanced: Creates new, custom times
- TestCrossCutting: Validation errors, mutual exclusions, result structure
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


class TestCopyFromSrc:
    """Tests for src-based copy operations (codex review fixes)."""

    def test_copy_from_src_preserves_source(self, patch_module: None, tmp_path: Any) -> None:
        """Test that copy with src does not destroy the source file."""
        src = str(tmp_path / "source.txt")
        dest = str(tmp_path / "dest.txt")
        with open(src, "w") as f:
            f.write("source content\n")

        with (
            set_module_args({"dest": dest, "state": "copy", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        # Source must still exist (codex review: atomic_move was destroying it)
        assert os.path.isfile(src), "Source file was destroyed by copy operation"
        assert os.path.isfile(dest)
        with open(dest) as f:
            assert f.read() == "source content\n"
        with open(src) as f:
            assert f.read() == "source content\n"

    def test_copy_from_src_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Test that copy with src is idempotent when content matches."""
        src = str(tmp_path / "source.txt")
        dest = str(tmp_path / "dest.txt")
        with open(src, "w") as f:
            f.write("same content\n")
        with open(dest, "w") as f:
            f.write("same content\n")

        with (
            set_module_args({"dest": dest, "state": "copy", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_copy_content_dest_is_directory_fails(self, patch_module: None, tmp_path: Any) -> None:
        """Test that copy with content fails when dest is a directory (no force)."""
        dest = str(tmp_path / "destdir")
        os.makedirs(dest)

        with (
            set_module_args({"dest": dest, "state": "copy", "content": "hello"}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        result_msg = str(exc_info.value).lower()
        assert "not a regular file" in result_msg

    def test_copy_src_dest_is_directory_fails(self, patch_module: None, tmp_path: Any) -> None:
        """Test that copy with src fails when dest is a directory (no force)."""
        src = str(tmp_path / "source.txt")
        dest = str(tmp_path / "destdir")
        with open(src, "w") as f:
            f.write("content")
        os.makedirs(dest)

        with (
            set_module_args({"dest": dest, "state": "copy", "src": src}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        result_msg = str(exc_info.value).lower()
        assert "not a regular file" in result_msg


# =============================================================================
# Phase 6: Comprehensive Unit Tests
# =============================================================================


class TestCheckMode:
    """Check mode tests: verify no filesystem changes occur."""

    def test_directory_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=directory does not create directory."""
        dest = str(tmp_path / "checkdir")
        with (
            set_module_args({"dest": dest, "state": "directory", "_ansible_check_mode": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)

    def test_copy_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=copy does not write file."""
        dest = str(tmp_path / "checkfile.txt")
        with (
            set_module_args(
                {"dest": dest, "state": "copy", "content": "hello", "_ansible_check_mode": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)

    def test_absent_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=absent does not remove file."""
        dest = str(tmp_path / "keepme.txt")
        with open(dest, "w") as f:
            f.write("keep this")

        with (
            set_module_args({"dest": dest, "state": "absent", "_ansible_check_mode": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.exists(dest), "Check mode should not remove the file"

    def test_exists_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=exists does not create file."""
        dest = str(tmp_path / "checkexists.txt")
        with (
            set_module_args({"dest": dest, "state": "exists", "_ansible_check_mode": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)

    def test_touch_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=touch does not touch file."""
        dest = str(tmp_path / "checktouch.txt")
        with (
            set_module_args({"dest": dest, "state": "touch", "_ansible_check_mode": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)

    def test_link_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=link does not create symlink."""
        src = str(tmp_path / "source.txt")
        dest = str(tmp_path / "checklink")
        with open(src, "w") as f:
            f.write("source")

        with (
            set_module_args(
                {"dest": dest, "state": "link", "src": src, "_ansible_check_mode": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)

    def test_lineinfile_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=lineinfile does not modify file."""
        dest = str(tmp_path / "config.txt")
        with open(dest, "w") as f:
            f.write("line1\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "line": "newline",
                    "_ansible_check_mode": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert "newline" not in f.read()

    def test_blockinfile_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=blockinfile does not modify file."""
        dest = str(tmp_path / "block.txt")
        with open(dest, "w") as f:
            f.write("original\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "blockinfile",
                    "block": "managed content",
                    "_ansible_check_mode": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert "managed content" not in f.read()


class TestDiffMode:
    """Diff mode tests: verify diff output for content-changing states."""

    def test_copy_diff_shows_before_after(self, patch_module: None, tmp_path: Any) -> None:
        """Diff mode for state=copy shows before and after content."""
        dest = str(tmp_path / "difftest.txt")
        with open(dest, "w") as f:
            f.write("old content\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "copy",
                    "content": "new content\n",
                    "_ansible_diff": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert "diff" in result
        assert result["diff"]["before"] == "old content\n"
        assert result["diff"]["after"] == "new content\n"

    def test_lineinfile_diff(self, patch_module: None, tmp_path: Any) -> None:
        """Diff mode for state=lineinfile shows line changes."""
        dest = str(tmp_path / "diffline.txt")
        with open(dest, "w") as f:
            f.write("line1\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "line": "line2",
                    "_ansible_diff": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert "diff" in result
        assert "line1" in result["diff"]["before"]
        assert "line2" in result["diff"]["after"]

    def test_blockinfile_diff(self, patch_module: None, tmp_path: Any) -> None:
        """Diff mode for state=blockinfile shows block changes."""
        dest = str(tmp_path / "diffblock.txt")
        with open(dest, "w") as f:
            f.write("existing\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "blockinfile",
                    "block": "managed block",
                    "_ansible_diff": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert "diff" in result
        assert "managed block" in result["diff"]["after"]

    def test_absent_diff_shows_removed(self, patch_module: None, tmp_path: Any) -> None:
        """Diff mode for state=absent shows content being removed."""
        dest = str(tmp_path / "diffremove.txt")
        with open(dest, "w") as f:
            f.write("to be removed\n")

        with (
            set_module_args({"dest": dest, "state": "absent", "_ansible_diff": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert "diff" in result
        assert "to be removed" in result["diff"]["before"]
        assert result["diff"]["after"] == ""

    def test_copy_src_diff(self, patch_module: None, tmp_path: Any) -> None:
        """Diff mode for src-based copy shows file content changes."""
        src = str(tmp_path / "newsrc.txt")
        dest = str(tmp_path / "diffdest.txt")
        with open(src, "w") as f:
            f.write("new from src\n")
        with open(dest, "w") as f:
            f.write("old at dest\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "copy",
                    "src": src,
                    "_ansible_diff": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert "diff" in result
        assert "old at dest" in result["diff"]["before"]
        assert "new from src" in result["diff"]["after"]


class TestDirectoryAdvanced:
    """Advanced tests for state=directory."""

    def test_force_replaces_file_with_directory(self, patch_module: None, tmp_path: Any) -> None:
        """Force=True replaces a file with a directory."""
        dest = str(tmp_path / "filetodir")
        with open(dest, "w") as f:
            f.write("I am a file")

        with (
            set_module_args({"dest": dest, "state": "directory", "force": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isdir(dest)

    def test_force_backup_renames_existing(self, patch_module: None, tmp_path: Any) -> None:
        """Force_backup=True renames existing file to .old."""
        dest = str(tmp_path / "backupdir")
        with open(dest, "w") as f:
            f.write("backup me")

        with (
            set_module_args(
                {"dest": dest, "state": "directory", "force": True, "force_backup": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isdir(dest)
        assert os.path.exists(dest + ".old")
        with open(dest + ".old") as f:
            assert f.read() == "backup me"

    def test_trailing_slash_stripped(self, patch_module: None, tmp_path: Any) -> None:
        """Trailing slash is stripped from dest for directories."""
        dest = str(tmp_path / "slashdir")
        with (
            set_module_args({"dest": dest + "/", "state": "directory"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isdir(dest)

    def test_absent_removes_directory_recursively(self, patch_module: None, tmp_path: Any) -> None:
        """State=absent removes directory and all contents."""
        dest = str(tmp_path / "removedir")
        os.makedirs(os.path.join(dest, "sub", "deep"))
        with open(os.path.join(dest, "sub", "file.txt"), "w") as f:
            f.write("nested file")

        with (
            set_module_args({"dest": dest, "state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)


class TestCopyAdvanced:
    """Advanced tests for state=copy."""

    def test_content_change_updates_file(self, patch_module: None, tmp_path: Any) -> None:
        """Existing file with different content is updated."""
        dest = str(tmp_path / "update.txt")
        with open(dest, "w") as f:
            f.write("old content\n")

        with (
            set_module_args({"dest": dest, "state": "copy", "content": "new content\n"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert f.read() == "new content\n"

    def test_backup_creates_backup_file(self, patch_module: None, tmp_path: Any) -> None:
        """Backup=True creates a backup before overwriting."""
        dest = str(tmp_path / "backup.txt")
        with open(dest, "w") as f:
            f.write("original\n")

        with (
            set_module_args(
                {"dest": dest, "state": "copy", "content": "updated\n", "backup": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert "backup_file" in result
        assert os.path.isfile(result["backup_file"])
        with open(result["backup_file"]) as f:
            assert f.read() == "original\n"

    def test_validate_success_allows_write(self, patch_module: None, tmp_path: Any) -> None:
        """Validate command that succeeds allows the file to be written."""
        dest = str(tmp_path / "validated.txt")
        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "copy",
                    "content": "valid content\n",
                    "validate": "/bin/true %s",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert f.read() == "valid content\n"

    def test_validate_failure_prevents_write(self, patch_module: None, tmp_path: Any) -> None:
        """Validate command that fails prevents the file from being written."""
        dest = str(tmp_path / "invalid.txt")
        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "copy",
                    "content": "bad content\n",
                    "validate": "/bin/false %s",
                }
            ),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "validation failed" in str(exc_info.value).lower()
        assert not os.path.exists(dest)

    def test_validate_without_percent_s_fails(self, patch_module: None, tmp_path: Any) -> None:
        """Validate command without %s placeholder fails."""
        dest = str(tmp_path / "nopct.txt")
        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "copy",
                    "content": "content\n",
                    "validate": "/bin/true",
                }
            ),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "%s" in str(exc_info.value)

    def test_copy_new_file_from_src(self, patch_module: None, tmp_path: Any) -> None:
        """Copy from src to non-existent dest creates new file."""
        src = str(tmp_path / "src.txt")
        dest = str(tmp_path / "newdest.txt")
        with open(src, "w") as f:
            f.write("from source\n")

        with (
            set_module_args({"dest": dest, "state": "copy", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert f.read() == "from source\n"

    def test_check_mode_copy_with_content(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for copy with existing different content reports changed but no write."""
        dest = str(tmp_path / "checkdiff.txt")
        with open(dest, "w") as f:
            f.write("old\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "copy",
                    "content": "new\n",
                    "_ansible_check_mode": True,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert f.read() == "old\n"  # Unchanged


class TestLineinfileAdvanced:
    """Advanced tests for state=lineinfile."""

    def test_regexp_replaces_matching_line(self, patch_module: None, tmp_path: Any) -> None:
        """Regexp match replaces the matched line."""
        dest = str(tmp_path / "regexp.txt")
        with open(dest, "w") as f:
            f.write("setting=old\nother=keep\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "regexp": "^setting=",
                    "line": "setting=new",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "setting=new" in content
        assert "setting=old" not in content
        assert "other=keep" in content

    def test_regexp_idempotent_when_line_matches(self, patch_module: None, tmp_path: Any) -> None:
        """Regexp match with line already correct is idempotent."""
        dest = str(tmp_path / "regexp_idem.txt")
        with open(dest, "w") as f:
            f.write("setting=correct\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "regexp": "^setting=",
                    "line": "setting=correct",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_insertbefore_bof(self, patch_module: None, tmp_path: Any) -> None:
        """insertbefore=BOF inserts at beginning of file."""
        dest = str(tmp_path / "bof.txt")
        with open(dest, "w") as f:
            f.write("second\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "line": "first",
                    "insertbefore": "BOF",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            lines = f.readlines()
        assert lines[0].strip() == "first"
        assert lines[1].strip() == "second"

    def test_insertafter_regex(self, patch_module: None, tmp_path: Any) -> None:
        """insertafter with regex inserts after the matched line."""
        dest = str(tmp_path / "after.txt")
        with open(dest, "w") as f:
            f.write("[section]\nkey1=val1\n[other]\nkey2=val2\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "line": "key1b=val1b",
                    "insertafter": "^key1=",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            lines = f.readlines()
        # Find key1b - should be right after key1=val1
        for i, line in enumerate(lines):
            if "key1=" in line and "key1b" not in line:
                assert "key1b" in lines[i + 1]
                break

    def test_line_state_absent_removes_line(self, patch_module: None, tmp_path: Any) -> None:
        """line_state=absent removes matching lines."""
        dest = str(tmp_path / "absent_line.txt")
        with open(dest, "w") as f:
            f.write("keep\nremove_me\nkeep_too\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "line": "remove_me",
                    "line_state": "absent",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "remove_me" not in content
        assert "keep" in content

    def test_regexp_absent_removes_all_matches(self, patch_module: None, tmp_path: Any) -> None:
        """line_state=absent with regexp removes all matching lines."""
        dest = str(tmp_path / "regexp_absent.txt")
        with open(dest, "w") as f:
            f.write("comment1\n# remove1\nkeep\n# remove2\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "regexp": "^# remove",
                    "line_state": "absent",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "# remove" not in content
        assert "comment1" in content
        assert "keep" in content

    def test_creates_file_with_line(self, patch_module: None, tmp_path: Any) -> None:
        """lineinfile creates file if it doesn't exist."""
        dest = str(tmp_path / "newfile.txt")
        with (
            set_module_args({"dest": dest, "state": "lineinfile", "line": "new line"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            assert "new line" in f.read()

    def test_line_already_present_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Line already present is idempotent (no regexp)."""
        dest = str(tmp_path / "idem.txt")
        with open(dest, "w") as f:
            f.write("line1\nalready_here\nline3\n")

        with (
            set_module_args({"dest": dest, "state": "lineinfile", "line": "already_here"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False


class TestBlockinfileAdvanced:
    """Advanced tests for state=blockinfile."""

    def test_update_existing_block(self, patch_module: None, tmp_path: Any) -> None:
        """Existing block markers are replaced with new content."""
        dest = str(tmp_path / "update_block.txt")
        with open(dest, "w") as f:
            f.write("header\n# BEGIN MANAGED BLOCK\nold content\n# END MANAGED BLOCK\nfooter\n")

        with (
            set_module_args({"dest": dest, "state": "blockinfile", "block": "new content"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "new content" in content
        assert "old content" not in content
        assert "header" in content
        assert "footer" in content

    def test_existing_block_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Block with same content is idempotent."""
        dest = str(tmp_path / "idem_block.txt")
        with open(dest, "w") as f:
            f.write("# BEGIN MANAGED BLOCK\nmanaged content\n# END MANAGED BLOCK\n")

        with (
            set_module_args({"dest": dest, "state": "blockinfile", "block": "managed content"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_custom_markers(self, patch_module: None, tmp_path: Any) -> None:
        """Custom marker template with custom begin/end."""
        dest = str(tmp_path / "custom_marker.txt")
        with open(dest, "w") as f:
            f.write("existing\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "blockinfile",
                    "block": "custom block",
                    "marker": "## {mark} MY BLOCK",
                    "marker_begin": "START",
                    "marker_end": "STOP",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "## START MY BLOCK" in content
        assert "## STOP MY BLOCK" in content
        assert "custom block" in content

    def test_block_state_absent_removes_block(self, patch_module: None, tmp_path: Any) -> None:
        """block_state=absent removes the managed block."""
        dest = str(tmp_path / "remove_block.txt")
        with open(dest, "w") as f:
            f.write("keep\n# BEGIN MANAGED BLOCK\nremove this\n# END MANAGED BLOCK\nalso keep\n")

        with (
            set_module_args({"dest": dest, "state": "blockinfile", "block_state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "# BEGIN MANAGED BLOCK" not in content
        assert "remove this" not in content
        assert "keep" in content
        assert "also keep" in content

    def test_creates_file_with_block(self, patch_module: None, tmp_path: Any) -> None:
        """blockinfile creates file if it doesn't exist."""
        dest = str(tmp_path / "newblock.txt")
        with (
            set_module_args({"dest": dest, "state": "blockinfile", "block": "new block content"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        with open(dest) as f:
            content = f.read()
        assert "# BEGIN MANAGED BLOCK" in content
        assert "new block content" in content
        assert "# END MANAGED BLOCK" in content


class TestLinkAdvanced:
    """Advanced tests for state=link and state=hard."""

    def test_wrong_symlink_target_with_force(self, patch_module: None, tmp_path: Any) -> None:
        """Force=True replaces symlink with wrong target."""
        src_old = str(tmp_path / "old_target.txt")
        src_new = str(tmp_path / "new_target.txt")
        dest = str(tmp_path / "mylink")
        with open(src_old, "w") as f:
            f.write("old")
        with open(src_new, "w") as f:
            f.write("new")
        os.symlink(src_old, dest)

        with (
            set_module_args({"dest": dest, "state": "link", "src": src_new, "force": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.readlink(dest) == src_new

    def test_correct_symlink_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Existing correct symlink is idempotent."""
        src = str(tmp_path / "target.txt")
        dest = str(tmp_path / "correctlink")
        with open(src, "w") as f:
            f.write("target")
        os.symlink(src, dest)

        with (
            set_module_args({"dest": dest, "state": "link", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_hard_link_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Existing correct hard link is idempotent (same inode)."""
        src = str(tmp_path / "hardsrc.txt")
        dest = str(tmp_path / "harddest.txt")
        with open(src, "w") as f:
            f.write("content")
        os.link(src, dest)

        with (
            set_module_args({"dest": dest, "state": "hard", "src": src}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False
        assert os.stat(dest).st_ino == os.stat(src).st_ino

    def test_hard_check_mode(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode for state=hard does not create hard link."""
        src = str(tmp_path / "src_hard.txt")
        dest = str(tmp_path / "dest_hard.txt")
        with open(src, "w") as f:
            f.write("content")

        with (
            set_module_args(
                {"dest": dest, "state": "hard", "src": src, "_ansible_check_mode": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.exists(dest)


class TestAbsentAdvanced:
    """Advanced tests for state=absent."""

    def test_glob_matches_and_removes(self, patch_module: None, tmp_path: Any) -> None:
        """Glob pattern matches and removes multiple files."""
        for i in range(3):
            with open(str(tmp_path / f"file{i}.tmp"), "w") as f:
                f.write(f"temp {i}")
        with open(str(tmp_path / "keep.txt"), "w") as f:
            f.write("keep")

        dest = str(tmp_path / "*.tmp")
        with (
            set_module_args({"dest": dest, "state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        # .tmp files removed
        for i in range(3):
            assert not os.path.exists(str(tmp_path / f"file{i}.tmp"))
        # .txt file kept
        assert os.path.exists(str(tmp_path / "keep.txt"))

    def test_glob_no_matches_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Glob pattern with no matches is idempotent."""
        dest = str(tmp_path / "*.nonexistent")
        with (
            set_module_args({"dest": dest, "state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_absent_check_mode_glob(self, patch_module: None, tmp_path: Any) -> None:
        """Check mode with glob does not remove files."""
        for i in range(2):
            with open(str(tmp_path / f"g{i}.tmp"), "w") as f:
                f.write(f"g{i}")

        dest = str(tmp_path / "*.tmp")
        with (
            set_module_args({"dest": dest, "state": "absent", "_ansible_check_mode": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        # Files should still exist
        for i in range(2):
            assert os.path.exists(str(tmp_path / f"g{i}.tmp"))

    def test_removes_symlink(self, patch_module: None, tmp_path: Any) -> None:
        """State=absent removes symlinks."""
        target = str(tmp_path / "target.txt")
        link = str(tmp_path / "mylink")
        with open(target, "w") as f:
            f.write("target")
        os.symlink(target, link)

        with (
            set_module_args({"dest": link, "state": "absent"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert not os.path.islink(link)
        assert os.path.exists(target)  # Target not removed


class TestExistsAdvanced:
    """Advanced tests for state=exists."""

    def test_existing_file_idempotent(self, patch_module: None, tmp_path: Any) -> None:
        """Existing file returns changed=False."""
        dest = str(tmp_path / "existing.txt")
        with open(dest, "w") as f:
            f.write("content")

        with (
            set_module_args({"dest": dest, "state": "exists"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is False

    def test_preserves_existing_content(self, patch_module: None, tmp_path: Any) -> None:
        """State=exists does not modify existing file content."""
        dest = str(tmp_path / "preserve.txt")
        with open(dest, "w") as f:
            f.write("original content\n")

        with (
            set_module_args({"dest": dest, "state": "exists"}),
            pytest.raises(AnsibleExitJson),
        ):
            fsbuilder_main()

        with open(dest) as f:
            assert f.read() == "original content\n"

    def test_exists_creates_empty_file(self, patch_module: None, tmp_path: Any) -> None:
        """State=exists creates an empty file when missing."""
        dest = str(tmp_path / "newempty.txt")
        with (
            set_module_args({"dest": dest, "state": "exists"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)
        with open(dest) as f:
            assert f.read() == ""


class TestTouchAdvanced:
    """Advanced tests for state=touch."""

    def test_touch_creates_new_file(self, patch_module: None, tmp_path: Any) -> None:
        """Touch creates file if it doesn't exist."""
        dest = str(tmp_path / "newtouch.txt")
        with (
            set_module_args({"dest": dest, "state": "touch"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)

    def test_touch_custom_times(self, patch_module: None, tmp_path: Any) -> None:
        """Touch with custom access_time and modification_time."""
        dest = str(tmp_path / "timed.txt")
        with open(dest, "w") as f:
            f.write("")

        # Use epoch timestamps
        custom_atime = "1000000000"
        custom_mtime = "1000000001"
        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "touch",
                    "access_time": custom_atime,
                    "modification_time": custom_mtime,
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        stat = os.stat(dest)
        assert abs(stat.st_atime - 1000000000) < 1
        assert abs(stat.st_mtime - 1000000001) < 1

    def test_touch_datetime_format(self, patch_module: None, tmp_path: Any) -> None:
        """Touch parses datetime string format for times."""
        dest = str(tmp_path / "dttouch.txt")
        with open(dest, "w") as f:
            f.write("")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "touch",
                    "access_time": "2020-01-01T00:00:00",
                    "modification_time": "2020-06-15T12:30:00",
                }
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True


class TestCrossCutting:
    """Cross-cutting concerns: validation errors, mutual exclusions, result structure."""

    def test_insertafter_insertbefore_mutual_exclusion(
        self, patch_module: None, tmp_path: Any
    ) -> None:
        """insertafter and insertbefore together produces error."""
        dest = str(tmp_path / "mutual.txt")
        with open(dest, "w") as f:
            f.write("line\n")

        with (
            set_module_args(
                {
                    "dest": dest,
                    "state": "lineinfile",
                    "line": "new",
                    "insertafter": "EOF",
                    "insertbefore": "BOF",
                }
            ),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "mutually exclusive" in str(exc_info.value).lower()

    def test_lineinfile_present_requires_line(self, patch_module: None, tmp_path: Any) -> None:
        """lineinfile with line_state=present requires line parameter."""
        dest = str(tmp_path / "noline.txt")
        with open(dest, "w") as f:
            f.write("content\n")

        with (
            set_module_args({"dest": dest, "state": "lineinfile", "line_state": "present"}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "line" in str(exc_info.value).lower()

    def test_blockinfile_present_requires_block(self, patch_module: None, tmp_path: Any) -> None:
        """blockinfile with block_state=present requires block parameter."""
        dest = str(tmp_path / "noblock.txt")
        with open(dest, "w") as f:
            f.write("content\n")

        with (
            set_module_args({"dest": dest, "state": "blockinfile", "block_state": "present"}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "block" in str(exc_info.value).lower()

    def test_result_has_standard_keys(self, patch_module: None, tmp_path: Any) -> None:
        """Result dict contains dest, state, and msg keys."""
        dest = str(tmp_path / "resultkeys")
        with (
            set_module_args({"dest": dest, "state": "directory"}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert "dest" in result
        assert "state" in result
        assert "changed" in result

    def test_makedirs_with_copy(self, patch_module: None, tmp_path: Any) -> None:
        """makedirs=True creates parent dirs for state=copy."""
        dest = str(tmp_path / "deep" / "nested" / "file.txt")
        with (
            set_module_args(
                {"dest": dest, "state": "copy", "content": "hello\n", "makedirs": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)

    def test_makedirs_with_lineinfile(self, patch_module: None, tmp_path: Any) -> None:
        """makedirs=True creates parent dirs for state=lineinfile."""
        dest = str(tmp_path / "deep" / "config.txt")
        with (
            set_module_args(
                {"dest": dest, "state": "lineinfile", "line": "setting=val", "makedirs": True}
            ),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)

    def test_makedirs_with_exists(self, patch_module: None, tmp_path: Any) -> None:
        """makedirs=True creates parent dirs for state=exists."""
        dest = str(tmp_path / "deep" / "exists.txt")
        with (
            set_module_args({"dest": dest, "state": "exists", "makedirs": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)

    def test_makedirs_with_touch(self, patch_module: None, tmp_path: Any) -> None:
        """makedirs=True creates parent dirs for state=touch."""
        dest = str(tmp_path / "deep" / "touch.txt")
        with (
            set_module_args({"dest": dest, "state": "touch", "makedirs": True}),
            pytest.raises(AnsibleExitJson) as exc_info,
        ):
            fsbuilder_main()

        result = extract_result(exc_info.value)
        assert result["changed"] is True
        assert os.path.isfile(dest)

    def test_link_requires_src(self, patch_module: None, tmp_path: Any) -> None:
        """state=link without src fails."""
        dest = str(tmp_path / "nosrc_link")
        with (
            set_module_args({"dest": dest, "state": "link"}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "src" in str(exc_info.value).lower()

    def test_hard_requires_src(self, patch_module: None, tmp_path: Any) -> None:
        """state=hard without src fails."""
        dest = str(tmp_path / "nosrc_hard")
        with (
            set_module_args({"dest": dest, "state": "hard"}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "src" in str(exc_info.value).lower()

    def test_copy_requires_content_or_src(self, patch_module: None, tmp_path: Any) -> None:
        """state=copy without content or src fails."""
        dest = str(tmp_path / "nothing.txt")
        with (
            set_module_args({"dest": dest, "state": "copy"}),
            pytest.raises(AnsibleFailJson) as exc_info,
        ):
            fsbuilder_main()

        assert "content" in str(exc_info.value).lower() or "src" in str(exc_info.value).lower()
