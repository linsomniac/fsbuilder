"""Shared test fixtures for fsbuilder unit tests.

AIDEV-NOTE: This provides the standard Ansible module testing infrastructure.
Uses ansible.module_utils.testing.patch_module_args which handles the serialization
profile correctly for ansible-core >= 2.20.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from ansible.module_utils.testing import patch_module_args


class AnsibleExitJson(Exception):
    """Exception raised when module calls exit_json."""

    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs
        super().__init__(str(kwargs))


class AnsibleFailJson(Exception):
    """Exception raised when module calls fail_json."""

    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs
        super().__init__(str(kwargs))


@contextmanager
def set_module_args(args: dict[str, Any]) -> Iterator[None]:
    """Context manager to inject module arguments for testing.

    AIDEV-NOTE: Uses Ansible's official patch_module_args helper which properly
    handles the serialization profile required by ansible-core >= 2.20.
    """
    if "_ansible_remote_tmp" not in args:
        args["_ansible_remote_tmp"] = "/tmp"
    if "_ansible_keep_remote_files" not in args:
        args["_ansible_keep_remote_files"] = False

    with patch_module_args(args):
        yield


def extract_result(exc: AnsibleExitJson) -> dict[str, Any]:
    """Extract the result dict from an AnsibleExitJson exception."""
    return exc.kwargs


@pytest.fixture
def patch_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch AnsibleModule.exit_json and fail_json to raise exceptions.

    This allows tests to capture the module's output without it calling sys.exit().
    """

    def exit_json_side_effect(self: Any, **kwargs: Any) -> None:
        raise AnsibleExitJson(kwargs)

    def fail_json_side_effect(self: Any, **kwargs: Any) -> None:
        kwargs.setdefault("failed", True)
        raise AnsibleFailJson(kwargs)

    monkeypatch.setattr(
        "ansible.module_utils.basic.AnsibleModule.exit_json",
        exit_json_side_effect,
    )
    monkeypatch.setattr(
        "ansible.module_utils.basic.AnsibleModule.fail_json",
        fail_json_side_effect,
    )


@pytest.fixture
def mock_module() -> MagicMock:
    """Create a mock AnsibleModule for testing individual handler methods."""
    module = MagicMock()
    module.check_mode = False
    module._diff = False
    module.params = {}
    return module
