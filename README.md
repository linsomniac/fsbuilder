# linsomniac.fsbuilder.fsbuilder

Ansible module that consolidates multiple filesystem operations into a single
task. Instead of writing separate `ansible.builtin.template`, `copy`, `file`,
`lineinfile`, and `blockinfile` tasks, define one `fsbuilder` task with a loop.


## Key Features

FSBuilder is a single module that provides many filesystem operations under a
single module, so that an ansible loop can be used to provide many similar
operations.

- **Loop parameter merging**: Per-item values override task-level defaults
- **Per-item `when`**: Conditional execution within loop items
- **Per-item `notify`**: Handler notifications per item
- **Template rendering**: File-based `.j2` templates and inline content
- **Validation**: Run a command to validate files before placement
- **Backup**: Timestamped backups before overwriting
- **Check mode**: Full `--check` support across all states
- **Diff mode**: `--diff` shows before/after for content changes
- **Idempotent**: All states follow the Ansible idempotency contract
- **Glob support**: `state: absent` supports glob patterns
- **Rich set of operations**: Template, copy, directory, ensure file exists,
  absent, symbolic+hard links, lineinfile, blockinfile.

## Teaser Example

```yaml
- name: Deploy application configs
  linsomniac.fsbuilder.fsbuilder:
    owner: root
    group: myapp
    mode: "a=rX,u+w"
  loop:
    - dest: /etc/myapp/conf.d
      state: directory
    - dest: /etc/myapp/config.ini
      #  src defaults to "config.ini.j2"
      #  "type: template" is the default, so no type here
      validate: "myapp --check-config %s"
      backup: true
      notify: "Restart myapp"
```

## Requirements

- ansible-core >= 2.15
- Python >= 3.9 on controller
- Python >= 3.6 on remote hosts

## Installation

### As a Collection

```bash
# From Galaxy
ansible-galaxy collection install linsomniac.fsbuilder

# From source
ansible-galaxy collection build
ansible-galaxy collection install linsomniac-fsbuilder-VERSION.tar.gz
```

### As a Role (for role-level plugin discovery)

Clone the repository and symlink the embedded role into your roles path:

```bash
# Clone the repo (e.g. next to your playbook project)
git clone https://github.com/linsomniac/fsbuilder .fsbuilder

# Symlink the role into your roles directory
ln -s ../.fsbuilder/roles/fsbuilder roles/fsbuilder
```

The symlink preserves the relative paths inside the role so that its
`action_plugins/` and `library/` symlinks correctly resolve back to the
collection plugins.

## Quick Start

When installed as a collection use `linsomniac.fsbuilder.fsbuilder`.
When installed as a role use just `fsbuilder` and include the role first:

```yaml
- hosts: all
  roles:
    - fsbuilder          # activates role-level plugin discovery
  tasks:
    - name: Deploy app config
      fsbuilder:
        ...
```

### Collection example

```yaml
- name: Deploy application config
  linsomniac.fsbuilder.fsbuilder:
    owner: root
    group: myapp
    mode: "0644"
  loop:
    # Create a directory
    - dest: /etc/myapp/conf.d
      state: directory
      mode: "0755"

    # Render a Jinja2 template (default state)
    - dest: /etc/myapp/config.ini
      validate: "myapp --check-config %s"
      backup: true
      notify: "Restart myapp"

    # Write literal content
    - dest: /etc/myapp/version.txt
      state: copy
      content: "v1.0.0"

    # Ensure a line in sshd_config
    - dest: /etc/ssh/sshd_config
      state: lineinfile
      regexp: "^PermitRootLogin"
      line: "PermitRootLogin no"

    # Clean up old files
    - dest: /etc/myapp/conf.d/*.rpmsave
      state: absent
```

## Parameters

See the full parameter reference in the module's `DOCUMENTATION` string:

```bash
ansible-doc linsomniac.fsbuilder.fsbuilder
```

## Development

```bash
# Install dev dependencies
uv sync

# Run linting
uv run ruff check
uv run ruff format --check
uv run mypy plugins/

# Run unit tests
uv run pytest tests/unit/ -v

# Run with coverage
uv run pytest tests/unit/ --cov=plugins --cov-report=html
```

## Architecture

The module is composed of two cooperating components:

- **Action Plugin** (`plugins/action/fsbuilder.py`) -- runs on the Ansible
  controller. Handles template rendering, file transfer, loop parameter
  merging, per-item `when` evaluation, and handler notification.
- **Module** (`plugins/modules/fsbuilder.py`) -- runs on the remote target
  host. Performs all filesystem operations.

## License

CC0
