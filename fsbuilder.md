# fsbuilder - Ansible Filesystem Swiss Army Knife

## Overview

`fsbuilder` is a custom Ansible module that consolidates multiple filesystem
operations (template, copy, mkdir, touch, rm) into a single task. Instead of
writing separate `ansible.builtin.template`, `ansible.builtin.copy`,
`ansible.builtin.file` tasks, you define a single `fsbuilder` task with
top-level defaults and a loop of items that each declare their destination,
state, and any overrides.

## Architecture: Two-Part Design (Module + Action Plugin)

The implementation is split into two cooperating pieces:

| Component | File | Runs On |
|-----------|------|---------|
| **Action Plugin** | `action_plugins/fsbuilder.py` | Ansible control machine |
| **Module** | `library/fsbuilder` | Remote target host |

This split is critical. Ansible modules execute on the **remote host**, but
template source files and `files/` source files live on the **control
machine**. The module alone cannot access them.

### The Template Trick (Action Plugin)

This is the key architectural insight. A normal Ansible module runs on the
remote host and has no access to files on the control machine. Templates live
in `roles/<role>/templates/` on the control machine. So how does `fsbuilder`
render templates?

**The action plugin intercepts the task before the module runs.** Here is what
it does for each state:

#### `state: template` (the default)

1. The action plugin runs on the control machine and determines the `src`
   (defaulting to `basename(dest) + ".j2"` if not specified).
2. It uses Ansible's built-in `_find_needle("templates", src)` to locate the
   template file in the standard Ansible search paths (role `templates/`
   directory, playbook-relative paths, etc.).
3. It reads the template file and renders it using Ansible's own `Templar`
   class, which has access to all task variables (`task_vars`), including
   facts, inventory variables, group_vars, host_vars, etc.
4. **The rendered content is injected into the module arguments as `content`,
   and the state is changed to `copy`.** The `src` argument is removed.
5. The module then runs on the remote host as a simple content-write operation
   -- it never needs to see the original `.j2` file.

This approach mirrors how Ansible's own `template` module works internally:
the template action plugin renders on the controller, then transfers the
result to the remote host.

#### `state: copy` (without `content`)

1. The action plugin locates the source file using
   `_find_needle("files", src)`.
2. It transfers the file to a temporary location on the remote host using
   Ansible's `_transfer_file()` method.
3. The module args are updated so `src` points to the remote temp path.
4. The module then copies from the temp path to the final destination.

This avoids encoding issues that would arise from reading file content into a
module argument string.

#### All other states (`directory`, `exists`, `absent`) and `content`-based copies

These don't require files from the control machine, so the action plugin
passes them straight through to the module without modification.

## Module Internals (library/fsbuilder)

The module itself is a Python class `FSBuilder` that handles the on-target
operations:

### States

| State | Behavior |
|-------|----------|
| `template` | Default. Render a Jinja2 template to `dest`. (In practice the action plugin pre-renders this, so the module receives it as a copy-with-content.) |
| `copy` | Copy a file or write `content` to `dest`. |
| `directory` | Ensure `dest` exists as a directory (`mkdir -p`). |
| `exists` | Ensure `dest` exists as a file. Creates an empty file if missing (like `touch`). |
| `absent` | Remove `dest` (file or directory, recursively). |

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dest` | (required) | Target path. If it ends with `/`, the `src` basename is appended (stripping `.j2` for templates). |
| `src` | auto | Source file. Defaults to `basename(dest) + ".j2"` for templates, `basename(dest)` for copy. |
| `state` | `template` | Operation type (see table above). |
| `owner` | - | File/directory owner. |
| `group` | - | File/directory group. |
| `mode` | - | File/directory permissions (e.g. `"0644"`, `"a=rX,u+w"`). |
| `content` | - | For copy: literal string content to write instead of using a `src` file. |
| `force` | `false` | If true and `dest` exists in a conflicting form (e.g. a directory where you want a file), remove or rename it before proceeding. |
| `force_backup` | `false` | When `force` is true: if `force_backup` is true, rename the existing path to `dest.old` (or `dest.old.<timestamp>`) instead of deleting it. If `force_backup` is false, `rm -rf` the existing path. |
| `backup` | `false` | Create a timestamped backup of the existing file before overwriting. |
| `notify` | - | Handler to notify if the item changed (passed through loop items). |
| `when` | - | Per-item conditional expression. Evaluated like Ansible's `when:`. Items that evaluate to false are skipped. |

### Loop and Parameter Merging

The module supports a pattern where top-level task parameters serve as
defaults, and per-item loop values override them:

```yaml
- name: Deploy config files
  fsbuilder:
    owner: root
    group: myapp
    mode: "0644"
  loop:
    - dest: /etc/myapp
      state: directory
      mode: "0755"          # overrides the task-level "0644"
    - dest: /etc/myapp/config.ini
      # uses default state=template, renders config.ini.j2
    - dest: /etc/myapp/data.conf
      state: copy
    - dest: /etc/myapp/debug.ini
      when: '"dev" in group_names'
```

**Automatic loop variable access:** The action plugin receives `task_vars` in
its `run()` method, which already contains the current loop item (as `item` or
whatever name `loop_control.loop_var` specifies). The plugin reads the loop
item directly from `task_vars` — no explicit `loop_item: "{{ item }}"` parameter
is needed. The plugin detects the loop variable name via
`self._task.loop_control` and only merges when `self._task.loop` is set,
preventing accidental merges from outer-scope variables.

The `_merge_loop_params()` function handles this: loop item values override
task-level values when the task-level value is `None`, empty, or still at its
default. Explicitly-set task-level params take priority over loop item values.

The action plugin also performs its own merge of loop parameters so that it can
determine `state`, `src`, and `dest` before the module runs.

### Idempotency

All operations are idempotent:

- **template/copy**: Content is compared before writing. If the destination
  already has the correct content, no change is made.
- **directory**: `os.makedirs(exist_ok=True)` -- no error if it already exists.
- **exists**: Only creates the file if it doesn't already exist.
- **absent**: Only acts if the path exists.

File attribute changes (owner, group, mode) are handled by Ansible's built-in
`set_fs_attributes_if_different()`, which is also idempotent.

### Atomic Writes

Template and copy-with-content operations write to a temporary file in the
same directory as the destination, then atomically move it into place using
`shutil.move()`. This prevents partial writes from leaving a corrupted file.

### When Conditions

Per-item `when` conditions are evaluated using Jinja2 with available system
facts. This allows conditional processing of individual items within a single
loop, without needing separate tasks.

### Check Mode

The module supports Ansible's `--check` (dry run) mode. All state handlers
check `self.module.check_mode` and return early with the expected change
status without modifying the filesystem.

## File Layout

```
action_plugins/
  fsbuilder.py        # Action plugin (runs on controller)
library/
  fsbuilder           # Module (runs on target host)
```
