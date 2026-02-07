# fsbuilder - Ansible Filesystem Swiss Army Knife

## Overview

`fsbuilder` is a custom Ansible module that consolidates multiple filesystem
operations (template, copy, mkdir, touch, rm, symlink, hardlink, line/block
editing) into a single task. Instead of writing separate
`ansible.builtin.template`, `ansible.builtin.copy`, `ansible.builtin.file`,
`ansible.builtin.lineinfile`, or `ansible.builtin.blockinfile` tasks, you
define a single `fsbuilder` task with top-level defaults and a loop of items
that each declare their destination, state, and any overrides.

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

There are two sub-cases depending on whether `content` is provided:

**Without `content` (the common case):**

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

**With `content` (inline template string):**

1. If both `content` and `src` are provided, the action plugin raises an
   error: `content` and `src` are mutually exclusive.
2. If only `content` is provided, the action plugin renders the `content`
   string as a Jinja2 template using Ansible's `Templar` (same variable
   access as file-based templates).
3. The rendered result replaces `content` in the module arguments, the state
   is changed to `copy`, and the module writes it to `dest`.

This allows small inline templates without requiring a separate `.j2` file:

```yaml
- dest: /etc/myapp/version.txt
  state: template
  content: "version={{ app_version }}\nbuilt={{ ansible_date_time.iso8601 }}\n"
```

#### `state: copy` (without `content`)

1. If `remote_src` is true, the action plugin skips controller-side file
   handling entirely and passes the `src` path straight through to the module,
   which copies from one remote path to another.
2. Otherwise, the action plugin locates the source file using
   `_find_needle("files", src)`.
3. It transfers the file to a temporary location on the remote host using
   Ansible's `_transfer_file()` method.
4. The module args are updated so `src` points to the remote temp path.
5. The module then copies from the temp path to the final destination.

This avoids encoding issues that would arise from reading file content into a
module argument string.

#### All other states (`directory`, `exists`, `absent`, `link`, `hard`, `touch`, `lineinfile`, `blockinfile`) and `content`-based copies

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
| `directory` | Ensure `dest` exists as a directory (`mkdir -p`). Trailing slashes on `dest` are stripped (they are not meaningful for this state). |
| `exists` | Ensure `dest` exists as a file. Creates an empty file if missing (like `touch` but only if absent). Does not update timestamps on an existing file. |
| `touch` | Ensure `dest` exists as a file **and** update its mtime/atime to the current time (or to `access_time`/`modification_time` if specified). Always reports changed. |
| `absent` | Remove `dest` (file or directory, recursively). Supports glob patterns in the basename (see Glob Patterns below). |
| `link` | Create a symbolic link at `dest` pointing to `src`. |
| `hard` | Create a hard link at `dest` pointing to `src`. |
| `lineinfile` | Ensure a particular line is present (or absent) in a file. See Line/Block Editing below. |
| `blockinfile` | Ensure a block of text delimited by markers is present (or absent) in a file. See Line/Block Editing below. |

### Parameters

#### Core Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dest` | (required) | Target path. If it ends with `/`, the `src` basename is appended (stripping `.j2` for templates). For `state: directory`, a trailing slash is stripped and ignored. |
| `src` | auto | Source file. Defaults to `basename(dest) + ".j2"` for templates, `basename(dest)` for copy. For `link`/`hard`, specifies the link target. Mutually exclusive with `content`. |
| `state` | `template` | Operation type (see table above). |
| `content` | - | Literal string content to write instead of using a `src` file. For `state: template`, the string is rendered as a Jinja2 template. For `state: copy`, it is written verbatim. Mutually exclusive with `src`. |

#### Ownership and Permissions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `owner` | - | File/directory owner. |
| `group` | - | File/directory group. |
| `mode` | - | File/directory permissions (e.g. `"0644"`, `"a=rX,u+w"`). |
| `recurse` | `false` | For `state: directory`: apply `owner`, `group`, and `mode` recursively to all existing contents of the directory. |
| `follow` | `true` | Whether to follow symlinks when setting attributes. If false, attributes are set on the link itself (where supported by the OS). |

#### File Handling

| Parameter | Default | Description |
|-----------|---------|-------------|
| `force` | `false` | If true and `dest` exists in a conflicting form (e.g. a directory where you want a file), remove or rename it before proceeding. No special handling for mount points -- if the OS returns an error, that error is surfaced directly. |
| `force_backup` | `false` | When `force` is true: if `force_backup` is true, rename the existing path to `dest.old` (or `dest.old.<timestamp>`) instead of deleting it. If `force_backup` is false, `rm -rf` the existing path. |
| `backup` | `false` | Create a timestamped backup of the existing file before overwriting. |
| `remote_src` | `false` | For `state: copy`: if true, the `src` path refers to a file on the remote host rather than the controller. The action plugin skips file transfer and the module copies directly on the remote host. |
| `makedirs` | `false` | If true, automatically create parent directories of `dest` if they don't exist (respecting `owner`/`group` of the item if set, with mode `0755`). Eliminates the need for a separate `state: directory` item for the parent path. |
| `validate` | - | A command to run to validate the file before moving it into place. The command receives the path to a temporary file via `%s`. If the command returns non-zero, the module fails and does not replace the destination. Essential for safety with config files. |

Example using `validate`:

```yaml
- dest: /etc/sudoers.d/myapp
  validate: "visudo -cf %s"
- dest: /etc/nginx/conf.d/myapp.conf
  validate: "nginx -t -c %s"
- dest: /etc/fstab
  validate: "mount -fav -T %s"
```

#### Template Rendering Controls

These parameters apply when `state: template` is used:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `newline_sequence` | `"\n"` | Line ending sequence to use in the rendered output. Options: `"\n"`, `"\r\n"`, `"\r"`. |
| `trim_blocks` | `true` | If true, the first newline after a block tag (`{% %}`) is removed. |
| `lstrip_blocks` | `true` | If true, leading whitespace before a block tag is stripped. |
| `output_encoding` | `"utf-8"` | Character encoding for the rendered output. |

#### Timestamps

| Parameter | Default | Description |
|-----------|---------|-------------|
| `access_time` | - | For `state: touch`: set the file's access time. Accepts epoch seconds or a datetime string. If omitted, uses the current time. |
| `modification_time` | - | For `state: touch`: set the file's modification time. Accepts epoch seconds or a datetime string. If omitted, uses the current time. |

#### Conditionals

| Parameter | Default | Description |
|-----------|---------|-------------|
| `when` | - | Per-item conditional expression. Evaluated like Ansible's `when:`. Items that evaluate to false are skipped. |
| `creates` | - | Skip this item if the specified path already exists on the remote host. |
| `removes` | - | Skip this item if the specified path does **not** exist on the remote host. |

#### Notification

| Parameter | Default | Description |
|-----------|---------|-------------|
| `notify` | - | Handler to notify if the item changed (passed through loop items). |

#### Error Handling

| Parameter | Default | Description |
|-----------|---------|-------------|
| `on_error` | `fail` | Controls behavior when a single item fails. `fail` (default): the entire task fails immediately. `continue`: the failing item is recorded as failed but processing continues with the remaining items. A summary of failures is reported at the end, and the task is marked failed if any item failed. |

### Line/Block Editing

#### `state: lineinfile`

Ensures a specific line is present (or absent) in a file. Modeled after
`ansible.builtin.lineinfile`.

| Parameter | Description |
|-----------|-------------|
| `line` | The line to ensure is present. Required when not removing. |
| `regexp` | A regex pattern. If the line matching this pattern exists, it is replaced with `line`. If no match is found, `line` is appended (or inserted per `insertafter`/`insertbefore`). |
| `insertafter` | Insert `line` after the last line matching this regex. Special value `EOF` (default) appends to the end. |
| `insertbefore` | Insert `line` before the last line matching this regex. Special value `BOF` inserts at the beginning. Mutually exclusive with `insertafter`. |
| `line_state` | `present` or `absent`. If `absent`, lines matching `regexp` (or matching `line` exactly) are removed. |

```yaml
- dest: /etc/ssh/sshd_config
  state: lineinfile
  regexp: "^PermitRootLogin"
  line: "PermitRootLogin no"
  validate: "sshd -t -f %s"
```

#### `state: blockinfile`

Ensures a block of text delimited by marker lines is present (or absent) in a
file. Modeled after `ansible.builtin.blockinfile`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `block` | (required) | The multi-line text to insert between the markers. |
| `marker` | `"# {mark} MANAGED BLOCK"` | Marker template. `{mark}` is replaced by `marker_begin`/`marker_end`. |
| `marker_begin` | `BEGIN` | String that replaces `{mark}` in the opening marker. |
| `marker_end` | `END` | String that replaces `{mark}` in the closing marker. |
| `insertafter` | `EOF` | Insert the block after the last line matching this regex. |
| `insertbefore` | - | Insert the block before the last line matching this regex. |
| `block_state` | `present` | `present` or `absent`. If `absent`, the marked block is removed. |

```yaml
- dest: /etc/hosts
  state: blockinfile
  marker: "# {mark} ANSIBLE MANAGED - myapp"
  block: |
    192.168.1.10 app1.internal
    192.168.1.11 app2.internal
```

### Glob Patterns for `state: absent`

When `state: absent`, the basename of `dest` may contain shell glob characters
(`*`, `?`, `[...]`). The module expands the glob on the remote host and
removes all matching paths.

```yaml
- dest: /etc/myapp/conf.d/*.bak
  state: absent
- dest: /tmp/myapp-build-*
  state: absent
```

If the glob matches nothing, the item is reported as unchanged (not an error).

### Loop and Parameter Merging

The module supports a pattern where top-level task parameters serve as
defaults, and per-item loop values override them. **Per-item values always take
precedence over task-level values.** Task-level values serve as defaults for
any parameter not specified in the item.

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
item directly from `task_vars` -- no explicit `loop_item: "{{ item }}"` parameter
is needed. The plugin detects the loop variable name via
`self._task.loop_control` and only merges when `self._task.loop` is set,
preventing accidental merges from outer-scope variables.

The `_merge_loop_params()` function handles this. Precedence order (highest
first):

1. Per-item (loop) values -- always win when present
2. Explicitly-set task-level values
3. Parameter defaults (e.g. `state` defaults to `template`)

The action plugin also performs its own merge of loop parameters so that it can
determine `state`, `src`, `dest`, and `content` before the module runs.

### Parameter Interaction Rules

The following combinations are validated and will raise an error:

- `content` + `src` together on the same item: mutually exclusive, regardless
  of state.
- `state: lineinfile` without `line` (when `line_state` is `present`).
- `state: blockinfile` without `block` (when `block_state` is `present`).
- `insertafter` + `insertbefore` together: mutually exclusive.
- `validate` with states that don't produce a file (`directory`, `absent`,
  `link`, `hard`): ignored with a warning.

### Idempotency

All operations are idempotent:

- **template/copy**: Content is compared before writing. If the destination
  already has the correct content, no change is made.
- **directory**: `os.makedirs(exist_ok=True)` -- no error if it already exists.
- **exists**: Only creates the file if it doesn't already exist.
- **touch**: Always updates timestamps, so always reports changed (consistent
  with `ansible.builtin.file` behavior for `state: touch`).
- **absent**: Only acts if the path exists. Glob patterns that match nothing
  report unchanged.
- **link/hard**: Compares the existing link target. Only changes if the
  current target differs from `src` or if the path is not a link.
- **lineinfile/blockinfile**: Compares file content before and after the
  edit. Only reports changed if the file was actually modified.

File attribute changes (owner, group, mode) are handled by Ansible's built-in
`set_fs_attributes_if_different()`, which is also idempotent.

### Atomic Writes

Template and copy-with-content operations write to a temporary file in the
same directory as the destination, then atomically move it into place using
`shutil.move()`. This prevents partial writes from leaving a corrupted file.

When `validate` is specified, the validation command runs against the
temporary file **before** the atomic move. If validation fails, the temporary
file is removed and the destination is left untouched.

### When Conditions

Per-item `when` conditions are evaluated using Jinja2 with available system
facts. This allows conditional processing of individual items within a single
loop, without needing separate tasks.

The `creates` and `removes` conditionals provide a simpler alternative for
path-existence checks without Jinja2 expressions:

```yaml
- dest: /etc/myapp/config.ini
  creates: /etc/myapp/.initialized   # skip if this path exists
- dest: /tmp/myapp-build
  state: absent
  removes: /tmp/myapp-build           # skip if this path does NOT exist
```

### Diff Support

When Ansible is run with `--diff`, fsbuilder produces before/after diffs for
file content changes (`template`, `copy`, `lineinfile`, `blockinfile`). For
new files, the "before" is shown as empty. For `state: absent`, the "before"
shows the file content (or directory listing) being removed and the "after" is
empty.

Diff output is suppressed for binary files. The `no_log` parameter on the
task or item also suppresses diff output (for files containing secrets).

### Check Mode

The module supports Ansible's `--check` (dry run) mode. All state handlers
check `self.module.check_mode` and return early with the expected change
status without modifying the filesystem. Combined with `--diff`, this provides
a full preview of what would change.

### Return Data

The module returns structured data describing all operations performed:

```json
{
  "changed": true,
  "items": [
    {
      "dest": "/etc/myapp",
      "state": "directory",
      "changed": false,
      "msg": "directory already exists"
    },
    {
      "dest": "/etc/myapp/config.ini",
      "state": "template",
      "changed": true,
      "diff": {"before": "...", "after": "..."},
      "backup_file": null,
      "msg": "content updated"
    },
    {
      "dest": "/etc/myapp/old.conf",
      "state": "absent",
      "changed": true,
      "msg": "path removed"
    },
    {
      "dest": "/etc/myapp/debug.ini",
      "state": "template",
      "skipped": true,
      "skip_reason": "when condition evaluated to false"
    }
  ],
  "changed_count": 2,
  "ok_count": 1,
  "skipped_count": 1,
  "failed_count": 0
}
```

When `on_error: continue` is used, failed items include an `error` field with
the failure message, and the task-level result is marked `failed: true` if any
item failed.

## Comprehensive Example

```yaml
- name: Deploy myapp
  fsbuilder:
    owner: root
    group: myapp
    mode: "0644"
    on_error: continue
  loop:
    # Create directories (makedirs handles parents automatically)
    - dest: /etc/myapp/conf.d
      state: directory
      mode: "0755"

    # Render a template from a .j2 file
    - dest: /etc/myapp/config.ini
      # state: template is the default; renders config.ini.j2
      validate: "myapp --check-config %s"
      backup: true

    # Render an inline template (no .j2 file needed)
    - dest: /etc/myapp/version.txt
      state: template
      content: "version={{ app_version }}\nbuilt={{ ansible_date_time.iso8601 }}\n"

    # Copy a static file from the controller
    - dest: /etc/myapp/static.dat
      state: copy

    # Copy a file already on the remote host
    - dest: /etc/myapp/config.ini.dist
      src: /etc/myapp/config.ini
      state: copy
      remote_src: true
      creates: /etc/myapp/config.ini.dist  # only if it doesn't exist yet

    # Write literal content (not treated as a template)
    - dest: /etc/myapp/motd.txt
      state: copy
      content: "Welcome to {{ inventory_hostname }}"  # literal, not rendered

    # Create a symlink
    - dest: /etc/myapp/current
      state: link
      src: /opt/myapp/releases/v2.1

    # Ensure a line is present
    - dest: /etc/ssh/sshd_config
      state: lineinfile
      regexp: "^PermitRootLogin"
      line: "PermitRootLogin no"
      validate: "sshd -t -f %s"

    # Ensure a block is present
    - dest: /etc/hosts
      state: blockinfile
      marker: "# {mark} ANSIBLE MANAGED - myapp"
      block: |
        192.168.1.10 app1.internal
        192.168.1.11 app2.internal

    # Touch a file (always update timestamp)
    - dest: /etc/myapp/.last-deploy
      state: touch

    # Conditional item
    - dest: /etc/myapp/debug.conf
      when: '"dev" in group_names'

    # Clean up old files with a glob
    - dest: /etc/myapp/conf.d/*.rpmsave
      state: absent

    # Remove a path
    - dest: /etc/myapp/legacy.conf
      state: absent
```

## File Layout

```
action_plugins/
  fsbuilder.py        # Action plugin (runs on controller)
library/
  fsbuilder           # Module (runs on target host)
```
