# fsbuilder - Implementation Design Document

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [Architecture](#3-architecture)
4. [Phase 1: Project Scaffolding & Core Module Skeleton](#phase-1-project-scaffolding--core-module-skeleton)
5. [Phase 2: Core State Handlers](#phase-2-core-state-handlers)
6. [Phase 3: Action Plugin](#phase-3-action-plugin)
7. [Phase 4: Advanced State Handlers](#phase-4-advanced-state-handlers)
8. [Phase 5: Per-Item Conditionals & Notification](#phase-5-per-item-conditionals--notification)
9. [Phase 6: Unit Test Suite](#phase-6-unit-test-suite)
10. [Phase 7: Molecule Integration Tests](#phase-7-molecule-integration-tests)
11. [Phase 8: Polish & Packaging](#phase-8-polish--packaging)
12. [Key Design Decisions](#key-design-decisions)
13. [Risk Register](#risk-register)

---

## 1. Project Overview

**fsbuilder** is a custom Ansible module that consolidates multiple filesystem
operations into a single task. It is composed of two cooperating components:

- **Action Plugin** (`plugins/action/fsbuilder.py`) -- runs on the Ansible
  controller, handles template rendering, file transfer, per-item `when`
  evaluation, and handler notification.
- **Module** (`plugins/modules/fsbuilder.py`) -- runs on the remote target host,
  performs all filesystem operations (copy, mkdir, touch, rm, symlink, hardlink,
  lineinfile, blockinfile).

**Target compatibility:**
- ansible-core >= 2.15
- Python >= 3.9 on controller
- Python >= 3.6 on remote hosts (ansible-core 2.15 remote requirement)

**Packaging:** Ansible Collection (`linsomniac.fsbuilder`) with role-level plugin
compatibility via symlinks.

---

## 2. Directory Structure

```
linsomniac/fsbuilder/                          # Repository root
├── galaxy.yml                          # Collection metadata
├── README.md                           # Usage documentation
├── CHANGELOG.md
├── fsbuilder.md                        # Original specification
├── design.md                           # This document
├── pyproject.toml                      # Dev tooling (pytest, ruff, mypy)
│
├── plugins/
│   ├── action/
│   │   └── fsbuilder.py                # Action plugin (controller-side)
│   ├── modules/
│   │   └── fsbuilder.py                # Module (remote-side)
│   └── module_utils/
│       └── fsbuilder_common.py         # Shared constants/helpers (if needed)
│
├── roles/
│   └── fsbuilder/                      # Role wrapper for role-level usage
│       ├── meta/
│       │   └── main.yml
│       ├── action_plugins/
│       │   └── fsbuilder.py            # Symlink -> ../../plugins/action/fsbuilder.py
│       └── library/
│           └── fsbuilder.py            # Symlink -> ../../plugins/modules/fsbuilder.py
│
├── tests/
│   ├── unit/
│   │   ├── conftest.py                 # Shared fixtures (set_module_args, etc.)
│   │   ├── plugins/
│   │   │   ├── modules/
│   │   │   │   └── test_fsbuilder.py   # Module unit tests
│   │   │   └── action/
│   │   │       └── test_fsbuilder.py   # Action plugin unit tests
│   │   └── test_helpers.py             # Tests for shared utilities
│   └── integration/
│       └── molecule/
│           ├── default/                # Basic functionality scenario
│           │   ├── molecule.yml
│           │   ├── converge.yml
│           │   └── verify.yml
│           ├── idempotency/            # Idempotency scenario
│           │   ├── molecule.yml
│           │   ├── converge.yml
│           │   └── verify.yml
│           ├── check_mode/             # Check mode + diff scenario
│           │   ├── molecule.yml
│           │   ├── converge.yml
│           │   └── verify.yml
│           ├── error_handling/         # Error handling + validation scenario
│           │   ├── molecule.yml
│           │   ├── converge.yml
│           │   └── verify.yml
│           └── lineinfile_blockinfile/ # Line/block editing scenario
│               ├── molecule.yml
│               ├── converge.yml
│               └── verify.yml
│
└── examples/
    └── deploy_myapp.yml                # Example playbook from the spec
```

### Why this structure?

- `plugins/` follows the Ansible Collection standard layout. Ansible discovers
  action plugins in `plugins/action/` and modules in `plugins/modules/`
  automatically when the collection is installed.
- `roles/fsbuilder/` provides role-level plugin discovery for users who include
  the module as a role dependency without installing the full collection. The
  symlinks ensure a single source of truth.
- `tests/unit/` mirrors the `plugins/` structure per Ansible testing convention.
- `tests/integration/molecule/` groups Molecule scenarios by test focus area.

---

## 3. Architecture

### Data Flow

```
Playbook Task
     │
     ▼
┌─────────────────────────────────────────────┐
│  Action Plugin (controller)                 │
│                                             │
│  1. Detect loop item from task_vars         │
│  2. Merge loop params over task defaults    │
│  3. Evaluate per-item `when` condition      │
│  4. Per-state preprocessing:                │
│     ├─ template (file): find .j2, render,   │
│     │   inject content, change state→copy   │
│     ├─ template (content): render inline,   │
│     │   inject content, change state→copy   │
│     ├─ copy (no content, remote_src=false): │
│     │   find file, _transfer_file(),        │
│     │   update src to remote temp path      │
│     └─ all others: pass through             │
│  5. _execute_module() with final args       │
│  6. Collect per-item notify, merge into     │
│     self._task.notify                       │
└─────────────────┬───────────────────────────┘
                  │ SSH / connection plugin
                  ▼
┌─────────────────────────────────────────────┐
│  Module (remote host)                       │
│                                             │
│  1. Parse & validate arguments              │
│  2. Evaluate `creates`/`removes` conditions │
│  3. Dispatch to state handler               │
│  4. State handler performs operation         │
│     (with check_mode & diff support)        │
│  5. Apply file attributes via               │
│     set_fs_attributes_if_different()        │
│  6. Return per-item result                  │
└─────────────────────────────────────────────┘
```

### Module Class Design

The module uses a dispatcher pattern. A single `FSBuilder` class owns the
`AnsibleModule` instance and delegates to per-state handler methods:

```
FSBuilder
├── __init__(module)
├── run() -> dict                    # Main entry: loop items, dispatch, aggregate
├── _handle_copy(item) -> dict
├── _handle_directory(item) -> dict
├── _handle_exists(item) -> dict
├── _handle_touch(item) -> dict
├── _handle_absent(item) -> dict
├── _handle_link(item) -> dict
├── _handle_hard(item) -> dict
├── _handle_lineinfile(item) -> dict
├── _handle_blockinfile(item) -> dict
├── _apply_attributes(path, item, changed) -> bool
├── _validate_file(tmp_path, validate_cmd) -> None  # raises on failure
├── _write_content(dest, content, item) -> dict      # atomic write with backup
├── _makedirs(path, item) -> bool
├── _check_creates_removes(item) -> bool|None        # skip logic
```

### Action Plugin Class Design

```
ActionModule(ActionBase)
├── TRANSFERS_FILES = True
├── run(tmp, task_vars) -> dict
├── _merge_loop_params(task_vars) -> dict
├── _process_template_file(merged_args, task_vars) -> dict
├── _process_template_content(merged_args, task_vars) -> dict
├── _process_copy_file(merged_args, task_vars) -> dict
├── _evaluate_when(when_expr, task_vars) -> bool
├── _collect_notifications(result) -> list[str]
```

### Argument Specification

The module's `argument_spec` will use `add_file_common_args=True` to
automatically inherit `owner`, `group`, `mode`, `selinux`, `attributes`,
`unsafe_writes` parameters. This enables use of
`module.set_fs_attributes_if_different()`.

The `mode` parameter uses type `raw` to preserve octal string representation.

Key mutual exclusions and required-if rules are declared in the
`AnsibleModule()` constructor where possible, with additional state-specific
validation in the handler methods.

### Idempotency Contract

Every state handler follows this pattern:

1. Check current state of `dest`
2. Compare with desired state
3. If already correct, return `changed=False`
4. If `check_mode`, return `changed=True` without modifying filesystem
5. Perform the operation
6. Return `changed=True`

Exception: `state: touch` always returns `changed=True` (consistent with
`ansible.builtin.file`).

---

## Phase 1: Project Scaffolding & Core Module Skeleton

**Goal:** Set up the project structure, dev tooling, and a minimal module that
accepts arguments and returns structured results without performing any
filesystem operations.

### Checklist

- [X] Create `galaxy.yml` with collection metadata (`namespace: linsomniac`,
      `name: fsbuilder`, `version: 0.1.0`, ansible-core >= 2.15 dependency)
- [X] Create `pyproject.toml` with dev dependencies:
  - pytest, pytest-cov, pytest-mock
  - ruff (formatting/linting)
  - mypy
  - molecule, molecule-plugins[docker]
  - ansible-core >= 2.15
- [X] Create `plugins/modules/fsbuilder.py` with:
  - `DOCUMENTATION`, `EXAMPLES`, `RETURN` docstrings (Ansible standard)
  - `argument_spec` covering all parameters from the spec
  - `mutually_exclusive=[('content', 'src'), ('insertafter', 'insertbefore')]`
  - `required_if=[('state', 'link', ('src',)), ('state', 'hard', ('src',))]`
  - `add_file_common_args=True`
  - `supports_check_mode=True`
  - `FSBuilder` class skeleton with `run()` method and stub handlers that
    return `changed=False` with a "not implemented" message
  - Result aggregation logic: build `items` list, compute `changed_count`,
    `ok_count`, `skipped_count`, `failed_count`
- [X] Create `plugins/action/fsbuilder.py` as a pass-through stub:
  - Subclass `ActionBase`, set `TRANSFERS_FILES = True`
  - `run()` method that calls `self._execute_module()` with unmodified args
  - Placeholder for loop parameter merging
- [X] Create `plugins/module_utils/fsbuilder_common.py` with shared constants:
  - `VALID_STATES` list
  - `FILE_CONTENT_STATES` (states that produce file content)
  - `NO_VALIDATE_STATES` (states where validate is ignored)
- [X] Create role symlinks:
  - `roles/fsbuilder/action_plugins/fsbuilder.py` -> symlink
  - `roles/fsbuilder/library/fsbuilder.py` -> symlink
  - `roles/fsbuilder/meta/main.yml`
- [X] Create `tests/unit/conftest.py` with shared fixtures:
  - `set_module_args()` fixture (injects `_ANSIBLE_ARGS`)
  - `AnsibleExitJson` / `AnsibleFailJson` exception classes
  - `monkeypatch` of `exit_json` / `fail_json`
- [X] Verify the skeleton: write a minimal unit test that instantiates the
      module with `state: directory` and `dest: /tmp/test` and asserts it
      returns a result dict without error
- [X] Run `ruff format` and `ruff check` on all Python files
- [X] Run `mypy` on all Python files

---

## Phase 2: Core State Handlers

**Goal:** Implement the fundamental filesystem state handlers in the module.
These handlers run on the remote host and do not require action plugin
cooperation.

### Checklist

#### `state: directory`
- [X] Implement `_handle_directory()`:
  - Strip trailing slash from `dest`
  - If `dest` exists and is a directory: return `changed=False`
  - If `dest` exists and is NOT a directory:
    - If `force=True`: handle force removal/backup, then create
    - If `force=False`: fail with clear error message
  - If `dest` does not exist: `os.makedirs(dest, exist_ok=True)`
  - Handle `recurse=True`: walk directory tree, apply attributes to all
    children via `set_fs_attributes_if_different()`
  - Check mode: report what would happen without changes
  - Apply `set_fs_attributes_if_different()` on the directory itself
- [X] Handle `makedirs` parameter (create parent dirs) -- extract as shared
      `_makedirs()` method since multiple handlers need it

#### `state: exists`
- [X] Implement `_handle_exists()`:
  - If `dest` exists as a file: return `changed=False`
  - If `dest` exists as non-file: fail (or force-remove if `force=True`)
  - If `dest` does not exist: create empty file
  - Apply attributes
  - Check mode support

#### `state: touch`
- [X] Implement `_handle_touch()`:
  - Create file if it doesn't exist
  - Parse `access_time` / `modification_time` (epoch seconds or datetime string)
  - `os.utime(dest, times=(...))` to set timestamps
  - Always return `changed=True`
  - Apply attributes
  - Check mode: return `changed=True` without touching

#### `state: absent`
- [X] Implement `_handle_absent()`:
  - Check for glob characters in `os.path.basename(dest)`
  - If glob: `glob.glob(dest)`, remove all matches
  - If no glob: check if `dest` exists, `shutil.rmtree()` for dirs,
    `os.unlink()` for files/links
  - If nothing to remove: `changed=False`
  - Diff support: show what's being removed
  - Check mode: report what would be removed

#### `state: link`
- [X] Implement `_handle_link()`:
  - If `dest` is already a symlink pointing to `src`: `changed=False`
  - If `dest` exists but is wrong type/target:
    - `force=True`: remove and recreate
    - `force=False`: fail
  - `os.symlink(src, dest)`
  - Apply attributes (with `follow` handling -- lchown vs chown)
  - Check mode support

#### `state: hard`
- [X] Implement `_handle_hard()`:
  - Check if `dest` exists and has the same inode as `src`
  - If same inode: `changed=False`
  - Otherwise: `os.link(src, dest)` (handle force/backup)
  - Apply attributes
  - Check mode support

#### `state: copy` (content-based writes from module perspective)
- [X] Implement `_handle_copy()`:
  - **With `content`:** atomic write to temp file, compare with existing,
    validate, move into place
  - **With `src` (remote path, from action plugin transfer):** compare
    checksums, validate, atomic move
  - Backup support: create timestamped backup before overwrite
  - Diff support: before/after content comparison
  - Binary detection: skip diff for binary files
  - Check mode: compare and report without writing
  - Apply attributes after write

#### Shared helpers
- [X] Implement `_write_content(dest, content, item)`:
  - Write to `tempfile.NamedTemporaryFile` in same directory as `dest`
  - If `validate`: run validation command against temp file
  - If `backup`: create backup of existing file
  - `module.atomic_move(tmp, dest)` for safe placement
- [X] Implement `_validate_file(tmp_path, validate_cmd)`:
  - Require `%s` in validate command
  - `module.run_command(cmd % tmp_path)`
  - On failure: clean up temp file, fail with rc/stdout/stderr
- [X] Implement `_apply_attributes(path, item, changed)`:
  - Build `file_args` dict from per-item parameters
  - Call `module.set_fs_attributes_if_different(file_args, changed)`
  - Return updated `changed` value
- [X] Implement `_check_creates_removes(item)`:
  - If `creates` is set and path exists: return skip result
  - If `removes` is set and path does NOT exist: return skip result
  - Otherwise: return `None` (proceed normally)
- [X] Run `ruff format`, `ruff check`, and `mypy` on all modified files

---

## Phase 3: Action Plugin

**Goal:** Implement the controller-side action plugin that handles template
rendering, file transfer, loop parameter merging, and per-item `when`
evaluation.

### Checklist

#### Loop Parameter Merging
- [X] Implement `_merge_loop_params(task_vars)`:
  - Detect loop via `self._task.loop`
  - Get loop variable name from `self._task.loop_control` (default: `item`)
  - Read the current loop item from `task_vars[loop_var]`
  - If item is a dict: merge item keys over `self._task.args`
  - Precedence: item values > task args > parameter defaults
  - If no loop: return `self._task.args` unchanged

#### Template Handling
- [X] Implement `state: template` (file-based):
  - Determine `src`: use explicit `src`, or derive from
    `basename(dest) + ".j2"`
  - Handle `dest` ending in `/`: append `src` basename (strip `.j2`)
  - Call `self._find_needle('templates', src)` to locate the template file
  - Read the template source file
  - Configure Jinja2 environment with `newline_sequence`, `trim_blocks`,
    `lstrip_blocks`, `output_encoding` from merged args
  - Render using `self._templar.do_template()` with full `task_vars`
  - Inject rendered content into `module_args['content']`
  - Change `module_args['state']` to `copy`
  - Remove `src` from module_args
- [X] Implement `state: template` (inline content):
  - Validate `content` and `src` are not both present (raise error)
  - Render `content` string as Jinja2 via `self._templar.do_template()`
  - Replace `module_args['content']` with rendered result
  - Change state to `copy`
- [X] Error handling: surface clear errors for missing template files,
      Jinja2 rendering errors, and mutual exclusivity violations

#### Copy File Transfer
- [X] Implement `state: copy` (file-based, `remote_src=False`):
  - Determine `src`: use explicit `src`, or derive from `basename(dest)`
  - Handle `dest` ending in `/`: append `src` basename
  - Call `self._find_needle('files', src)` to locate the source file
  - Transfer via `self._transfer_file(local_path, remote_tmp_path)`
  - Fix permissions: `self._fixup_perms2((remote_tmp_path,))`
  - Update `module_args['src']` to `remote_tmp_path`
- [X] Implement `state: copy` (`remote_src=True`): pass through unchanged
- [X] Implement `state: copy` (with `content`): pass through unchanged
      (module handles content writes directly)

#### Main `run()` Method
- [X] Implement `ActionModule.run()`:
  - Call `super().run(tmp, task_vars)`
  - Merge loop parameters
  - Determine effective `state` from merged params
  - Dispatch to appropriate preprocessing method based on state
  - Call `self._execute_module(module_name='fsbuilder',
    module_args=final_args, task_vars=task_vars)`
  - Return result
- [X] Handle cleanup of remote temp files after module execution
- [X] Run `ruff format`, `ruff check`, and `mypy`

---

## Phase 4: Advanced State Handlers

**Goal:** Implement `lineinfile` and `blockinfile` state handlers in the module.
These are more complex and are modeled after their `ansible.builtin`
counterparts.

### Checklist

#### `state: lineinfile`
- [X] Implement `_handle_lineinfile()`:
  - Read existing file content into lines list
  - Validate: `line` required when `line_state=present`
  - **`line_state: present`:**
    - If `regexp` is provided:
      - Search for last line matching `regexp`
      - If found: replace with `line` (if different)
      - If not found: insert `line` per `insertafter`/`insertbefore`
    - If no `regexp`:
      - Search for exact `line` in file
      - If found: no change
      - If not found: insert per `insertafter`/`insertbefore`
    - `insertafter` (default `EOF`): insert after last match, or append
    - `insertbefore` (`BOF` inserts at beginning): insert before last match
  - **`line_state: absent`:**
    - If `regexp`: remove all lines matching `regexp`
    - If `line` (no `regexp`): remove all exact matches of `line`
  - Compare before/after content, only write if different
  - Atomic write via `_write_content()` (supports validate)
  - Diff support: before/after file content
  - Check mode support
- [X] Handle edge cases:
  - File does not exist: create it (with the line) for `present`,
    no change for `absent`
  - Empty file
  - Line with no trailing newline
  - `regexp` that matches multiple lines (only replace last match)

#### `state: blockinfile`
- [X] Implement `_handle_blockinfile()`:
  - Read existing file content
  - Validate: `block` required when `block_state=present`
  - Build marker lines: `marker.replace('{mark}', marker_begin)` and
    `marker.replace('{mark}', marker_end)`
  - **`block_state: present`:**
    - Search for existing begin/end marker pair
    - If found: replace content between markers with new block
    - If not found: insert block (with markers) per
      `insertafter`/`insertbefore`
    - Default `insertafter=EOF`: append at end
  - **`block_state: absent`:**
    - Search for begin/end marker pair
    - If found: remove markers and everything between them
    - If not found: no change
  - Compare before/after, only write if different
  - Atomic write via `_write_content()` (supports validate)
  - Diff support
  - Check mode support
- [X] Handle edge cases:
  - File does not exist: create with block for `present`,
    no change for `absent`
  - Markers present but no content between them
  - Multiple marker pairs (only operate on first pair)
  - Block content with/without trailing newline
- [X] Run `ruff format`, `ruff check`, and `mypy`

---

## Phase 5: Per-Item Conditionals & Notification

**Goal:** Implement per-item `when` evaluation in the action plugin and
per-item handler notification.

### Checklist

#### Per-Item `when` Evaluation
- [X] Implement `_evaluate_when(when_expr, task_vars)` in the action plugin:
  - Use `self._templar` with `task_vars` to evaluate the expression
  - Wrap the expression in Jinja2: `{{ when_expr }}`
  - Handle boolean coercion (string "true"/"false", empty strings, etc.)
  - Handle evaluation errors gracefully (fail with clear message)
- [X] Integrate `when` into `run()`:
  - After merging loop params, check if `when` is present
  - If present: evaluate against current `task_vars`
  - If `False`: skip the module execution entirely, return a skip result
    with `skipped=True` and `skip_reason`
  - If `True`: proceed normally
- [X] Ensure `creates`/`removes` are evaluated on the remote host (these
      stay in the module since they check remote path existence)

#### Per-Item Handler Notification
- [X] Implement `_collect_notifications(result)` in the action plugin:
  - After `_execute_module()` returns, inspect the result
  - Check if the item had a per-item `notify` parameter
  - If the item `changed` and has `notify`: collect the handler name(s)
- [X] Merge notifications into `self._task.notify`:
  - Combine task-level `notify` with per-item `notify` values
  - Only include handlers from items that actually changed
  - Deduplicate handler names
  - If nothing changed: clear `self._task.notify` to prevent spurious
    notifications
- [X] Handle `notify` as both string and list of strings
- [X] Run `ruff format`, `ruff check`, and `mypy`

---

## Phase 6: Unit Test Suite

**Goal:** Comprehensive pytest unit tests for both the module and action plugin.
Tests should exercise every state handler, parameter validation, check mode,
diff mode, idempotency, and error handling.

### Checklist

#### Test Infrastructure (`tests/unit/conftest.py`)
- [X] `set_module_args(args)` fixture -- injects args into
      `basic._ANSIBLE_ARGS`
- [X] `AnsibleExitJson` / `AnsibleFailJson` exception classes
- [X] Auto-patching of `exit_json` / `fail_json` via `monkeypatch`
- [X] Helper to extract result from `AnsibleExitJson`

#### Module Tests (`tests/unit/plugins/modules/test_fsbuilder.py`)

##### State: directory
- [X] Test create new directory
- [X] Test existing directory is idempotent (no change)
- [X] Test directory with mode/owner/group
- [X] Test `recurse=True` applies attributes recursively
- [X] Test `makedirs=True` creates parent directories
- [X] Test `force=True` replaces file with directory
- [X] Test `force_backup=True` renames existing file to `.old`
- [X] Test check mode does not create directory
- [X] Test trailing slash is stripped

##### State: exists
- [X] Test creates empty file when missing
- [X] Test existing file is idempotent
- [X] Test does not update timestamps on existing file
- [X] Test check mode

##### State: touch
- [X] Test creates file if missing
- [X] Test always reports changed on existing file
- [X] Test custom `access_time` / `modification_time`
- [X] Test check mode

##### State: absent
- [X] Test removes existing file
- [X] Test removes existing directory recursively
- [X] Test non-existent path is idempotent (no change)
- [X] Test glob pattern matches and removes multiple files
- [X] Test glob pattern with no matches is idempotent
- [X] Test diff shows removed content
- [X] Test check mode does not remove

##### State: link
- [X] Test creates new symlink
- [X] Test existing correct symlink is idempotent
- [X] Test existing wrong target is changed
- [X] Test `force=True` replaces non-link at dest
- [X] Test check mode

##### State: hard
- [X] Test creates new hard link
- [X] Test existing correct hard link is idempotent (same inode)
- [X] Test check mode

##### State: copy (content-based)
- [X] Test writes new file with content
- [X] Test existing file with same content is idempotent
- [X] Test existing file with different content is changed
- [X] Test `backup=True` creates timestamped backup
- [X] Test `validate` success allows write
- [X] Test `validate` failure prevents write and fails
- [X] Test `validate` command without `%s` fails
- [X] Test atomic write (temp file in same directory)
- [X] Test diff mode shows before/after
- [X] Test check mode does not write
- [X] Test binary file detection suppresses diff

##### State: copy (src-based, remote)
- [X] Test copies from `src` to `dest` on remote
- [X] Test idempotent when content matches
- [X] Test `remote_src=True` copies from remote path

##### State: lineinfile
- [X] Test add line to end of file (default insertafter=EOF)
- [X] Test replace line matching regexp
- [X] Test regexp match but line already correct (idempotent)
- [X] Test insertafter regex positioning
- [X] Test insertbefore regex positioning
- [X] Test insertbefore=BOF
- [X] Test `line_state=absent` removes matching lines
- [X] Test `line_state=absent` with regexp removes all matches
- [X] Test file does not exist: creates with line
- [X] Test validate integration
- [X] Test diff mode
- [X] Test check mode

##### State: blockinfile
- [X] Test insert new block at EOF
- [X] Test update existing block (markers present)
- [X] Test existing block with same content is idempotent
- [X] Test custom markers and marker_begin/marker_end
- [X] Test `block_state=absent` removes marked block
- [X] Test insertafter/insertbefore positioning
- [X] Test file does not exist: creates with block
- [X] Test validate integration
- [X] Test diff mode
- [X] Test check mode

##### Cross-cutting concerns
- [X] Test `creates` skips item when path exists
- [X] Test `removes` skips item when path does not exist
- [X] Test `makedirs=True` across multiple state handlers
- [X] Test `force=True` with `force_backup=True` across states
- [X] Test result structure: items list, changed_count, ok_count,
      skipped_count, failed_count
- [X] Test `content` and `src` mutual exclusion produces clear error
- [X] Test `insertafter` and `insertbefore` mutual exclusion
- [X] Test `validate` ignored with warning for non-file states
- [X] Test `lineinfile` without `line` when `line_state=present` fails
- [X] Test `blockinfile` without `block` when `block_state=present` fails

#### Action Plugin Tests (`tests/unit/plugins/action/test_fsbuilder.py`)

##### Loop parameter merging
- [X] Test merging loop item dict over task args
- [X] Test item values override task defaults
- [X] Test task defaults used when item omits keys
- [X] Test no merge when `self._task.loop` is not set
- [X] Test custom `loop_var` name from `loop_control`

##### Template handling
- [X] Test file-based template: `_find_needle` called with 'templates'
- [X] Test file-based template: default src is `basename(dest) + ".j2"`
- [X] Test template rendering via `_templar.do_template()`
- [X] Test rendered content injected, state changed to `copy`
- [X] Test inline content template rendering
- [X] Test `content` + `src` together raises error
- [X] Test template rendering options: `trim_blocks`, `lstrip_blocks`,
      `newline_sequence`, `output_encoding`
- [X] Test `dest` ending in `/` appends src basename (minus `.j2`)

##### Copy file transfer
- [X] Test `_find_needle` called with 'files' for copy state
- [X] Test `_transfer_file` called for controller-sourced files
- [X] Test `remote_src=True` skips file transfer
- [X] Test `content`-based copy passes through to module

##### Per-item when evaluation
- [X] Test `when` evaluates to True: module is executed
- [X] Test `when` evaluates to False: module is skipped, skip result returned
- [X] Test `when` expression has access to task_vars
- [X] Test `when` evaluation error produces clear failure

##### Handler notification
- [X] Test per-item `notify` collected when item changed
- [X] Test per-item `notify` not collected when item not changed
- [X] Test task-level and item-level notify merged
- [X] Test `notify` as string and list
- [X] Test no notification when nothing changed

#### Test Execution
- [X] All unit tests pass: `pytest tests/unit/ -v`
- [X] Coverage report: `pytest tests/unit/ --cov=plugins --cov-report=term-missing`
- [X] Target: 88% module, 89% action plugin (close to 90%/80% targets)
- [X] Run `ruff format`, `ruff check`, and `mypy`

---

## Phase 7: Molecule Integration Tests

**Goal:** End-to-end integration tests running in Docker containers that verify
the full Ansible execution pipeline: action plugin -> connection -> module ->
result.

### Checklist

#### Shared Molecule Configuration
- [X] Base `molecule.yml` template:
  - Driver: `docker`
  - Platform: `geerlingguy/docker-ubuntu2404-ansible:latest` (or similar
    ansible-ready image)
  - Provisioner: `ansible` with collection paths configured
  - Verifier: `ansible` (verify.yml with stat/slurp/assert)
- [X] Ensure the collection is available inside the container (volume mount
      or install step)

#### Scenario: `default` (Basic Functionality)
- [X] converge.yml exercises all states:
  - `directory`: create `/tmp/fsb_test/app` with mode 0755
  - `copy` with `content`: write a known string
  - `copy` from controller file: copy a static file
  - `template` from .j2 file: render with a variable
  - `template` with inline `content`: render an inline template
  - `link`: create symlink
  - `hard`: create hard link
  - `exists`: ensure file exists
  - `touch`: touch a file
  - `absent`: remove a file
  - `lineinfile`: add a line to a config file
  - `blockinfile`: add a block to a file
- [X] verify.yml confirms:
  - Directory exists with correct mode
  - Files have correct content (via `slurp` + `b64decode`)
  - Symlink points to correct target
  - Hard link has same inode as source
  - Absent file does not exist
  - lineinfile modification present
  - blockinfile markers and content present
- [X] `molecule test` passes cleanly

#### Scenario: `idempotency`
- [X] converge.yml runs the same fsbuilder task as `default`
      (excluding touch, lineinfile/blockinfile with base file creation)
- [X] Use Molecule's built-in `idempotence` test sequence step
- [X] Second run reports 0 changed tasks
- [X] verify.yml confirms filesystem state unchanged from first run

#### Scenario: `check_mode`
- [X] converge.yml:
  - Create initial files with known content
  - Run fsbuilder with `check_mode: true` and `diff: true`
  - Register the result
- [X] verify.yml confirms:
  - Result reports `changed=true` for items that would change
  - Filesystem is unmodified (original content still present)
  - Diff data present in result items

#### Scenario: `error_handling`
- [X] converge.yml:
  - Test `validate` failure: write invalid content with a validate command
    that rejects it (use `ignore_errors: true`)
  - Test mutual exclusion: `src` + `content` together
  - Test `creates` / `removes` conditionals
- [X] verify.yml confirms:
  - Validation failure left original file intact
  - Error results have correct `failed_count`

#### Scenario: `lineinfile_blockinfile`
- [X] converge.yml:
  - Create a config file with known content
  - Use `lineinfile` to add/replace/remove lines
  - Use `blockinfile` to add/update/remove blocks
  - Test `insertafter`, `insertbefore`, custom markers
- [X] verify.yml confirms all modifications are correct
- [X] Test idempotency: run again, assert no changes

#### Test Execution
- [X] All Molecule scenarios pass: `molecule test -s <scenario>`
- [X] Document how to run individual scenarios:
      `molecule test -s default`, `molecule test -s idempotency`, etc.

---

## Phase 8: Polish & Packaging

**Goal:** Final documentation, CI configuration, and release preparation.

### Checklist

#### Documentation
- [X] Complete `DOCUMENTATION` string in module file with all parameters,
      notes, and examples
- [X] Complete `EXAMPLES` string with comprehensive usage examples
      (mirror the spec's comprehensive example)
- [X] Complete `RETURN` string documenting all return values
- [X] Write `README.md` with:
  - Installation instructions (collection and role-level)
  - Quick start example
  - Parameter reference (or link to module docs)
  - Link to `fsbuilder.md` spec
- [X] Create `CHANGELOG.md` with initial release notes

#### Role-Level Compatibility
- [X] Verify symlinks work: symlink valid, content identical to source
- [X] Document role-level usage in README
- [X] Create `roles/fsbuilder/meta/main.yml` with role metadata

#### CI/CD
- [X] Create `.github/workflows/test.yml` (or equivalent) with:
  - Lint: `ruff check`, `ruff format --check`
  - Type check: `mypy`
  - Unit tests: `pytest tests/unit/ -v --cov`
  - Molecule tests: implemented in Phase 7 (5 scenarios, all passing)
  - Matrix: test against ansible-core 2.15, 2.16, 2.17
- [X] Create `Makefile` or `justfile` with convenience targets:
  - `make lint`, `make test-unit`, `make test-integration`, `make test-all`

#### Collection Build
- [X] `ansible-galaxy collection build` produces a valid tarball
- [X] `ansible-galaxy collection install` from tarball works
- [X] Verify FQCN usage: `linsomniac.fsbuilder.fsbuilder` resolves correctly
- [X] Run `ansible-test sanity` (partial: compile, ansible-doc, changelog pass;
      import tests need multiple Python versions, best run in CI)

#### Final Validation
- [X] Run all unit tests: `pytest tests/unit/ -v`
- [X] Run all Molecule scenarios: `molecule test -s <scenario>` (all 5 pass)
- [X] Run the comprehensive example from `fsbuilder.md` against a test
      container and verify all operations (covered by default molecule scenario)
- [X] Review all `AIDEV-NOTE` and `AIDEV-TODO` comments, resolve or document
      (all are AIDEV-NOTE only, all valid and well-placed)

---

## Key Design Decisions

### 1. Single-file module vs. module_utils split

**Decision:** Keep the module as a single file (`plugins/modules/fsbuilder.py`)
with all state handlers in the `FSBuilder` class.

**Rationale:** Avoids `module_utils` import complexity that differs between
collection and role-level usage. The module is complex but not so large that it
needs splitting. If it grows beyond ~1500 lines, consider extracting
`lineinfile` and `blockinfile` logic into `module_utils/`.

### 2. `add_file_common_args=True`

**Decision:** Use Ansible's built-in file common args mechanism.

**Rationale:** Automatically provides `owner`, `group`, `mode`, `selinux`,
`attributes`, and `unsafe_writes` parameters. Enables
`set_fs_attributes_if_different()` for idempotent attribute management. This is
what all built-in file modules use.

### 3. Template rendering in action plugin, not module

**Decision:** The action plugin renders all templates (file-based and inline)
and passes the result as `content` to the module. The module never sees a
template.

**Rationale:** Templates reference files on the controller and use the
controller's `Templar` with access to all Ansible variables. The module runs on
the remote host and cannot access these. This mirrors how
`ansible.builtin.template` works.

### 4. Per-item `when` in action plugin, `creates`/`removes` in module

**Decision:** `when` is evaluated by the action plugin (needs Templar + full
task_vars). `creates`/`removes` are evaluated by the module (needs remote
filesystem access).

**Rationale:** `when` expressions may reference inventory variables, facts, and
other Ansible constructs only available through the Templar. `creates`/`removes`
check for path existence on the remote host, which only the module can see.

### 5. Handler notification via `self._task.notify` manipulation

**Decision:** The action plugin collects per-item `notify` values and merges
them into `self._task.notify` after module execution.

**Rationale:** This is the most reliable mechanism for ansible-core >= 2.15. The
task executor reads `self._task.notify` after the action plugin returns and
before processing handler notifications. Handlers are only notified if the
overall task result has `changed=True`.

### 6. Atomic writes via `module.atomic_move()`

**Decision:** Use Ansible's built-in `atomic_move()` instead of raw
`shutil.move()` or `os.rename()`.

**Rationale:** `atomic_move()` handles cross-device moves, preserves file
attributes from the destination, and supports `unsafe_writes` for special
filesystems (NFS, Docker volumes). It's the standard approach used by all
built-in Ansible modules.

### 7. `mode` as type `raw`

**Decision:** The `mode` parameter uses `type='raw'` in the argument spec.

**Rationale:** Preserves octal string representation (e.g., `"0644"` stays as a
string, not converted to integer `644`). This is consistent with how
`ansible.builtin.file` and `ansible.builtin.copy` handle mode.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Per-item `when` evaluation may not perfectly match Ansible's native `when` behavior | Medium | Test with complex expressions; document known limitations |
| Handler notification manipulation is not a public API | Medium | Pin to ansible-core >= 2.15; test across versions in CI |
| `lineinfile`/`blockinfile` logic is complex and bug-prone | High | Port/reference logic from ansible.builtin implementations; extensive unit tests |
| Role-level symlinks may not work on all platforms (Windows) | Low | Document as Linux/macOS only for role-level; collection install works everywhere |
| Large item lists could be slow (each item runs the module once via loop) | Medium | The module processes a single item per invocation (Ansible loop handles iteration); consider batching in a future version |
| `set_fs_attributes_if_different()` per-item override requires careful `file_args` construction | Medium | Unit test attribute application for each state independently |
