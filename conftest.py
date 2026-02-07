"""Root conftest.py - sets up sys.path for Ansible module testing.

AIDEV-NOTE: This makes 'plugins.modules.fsbuilder' and
'ansible.module_utils.fsbuilder_common' importable during testing,
without requiring full collection installation.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path so 'plugins.modules.fsbuilder' imports work
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Add module_utils to the ansible.module_utils namespace so the fallback import works
module_utils_path = str(Path(__file__).parent / "plugins" / "module_utils")
if module_utils_path not in sys.path:
    sys.path.insert(0, module_utils_path)

# Also register under ansible.module_utils namespace
import ansible.module_utils  # noqa: E402

if (
    hasattr(ansible.module_utils, "__path__")
    and module_utils_path not in ansible.module_utils.__path__
):  # noqa: SIM102
    ansible.module_utils.__path__.insert(0, module_utils_path)  # type: ignore[union-attr]
