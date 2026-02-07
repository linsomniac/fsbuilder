# Changelog

## 0.1.0 (Unreleased)

### Added
- Initial release of `aix.fsbuilder` collection
- Module (`plugins/modules/fsbuilder.py`) with 10 state handlers:
  `template`, `copy`, `directory`, `exists`, `touch`, `absent`, `link`,
  `hard`, `lineinfile`, `blockinfile`
- Action plugin (`plugins/action/fsbuilder.py`) with:
  - Template rendering (file-based and inline content)
  - Controller-to-remote file transfer for `state: copy`
  - Loop parameter merging (per-item overrides)
  - Per-item `when` evaluation
  - Per-item `notify` handler notification
- Full check mode (`--check`) support for all states
- Diff mode (`--diff`) for content-changing operations
- Idempotent behavior for all state handlers
- `validate` parameter for file content validation before placement
- `backup` parameter for timestamped backups
- `makedirs` parameter for automatic parent directory creation
- `force` and `force_backup` for handling conflicting paths
- `creates`/`removes` conditional execution
- Glob pattern support for `state: absent`
- Role-level plugin discovery via symlinks
- Comprehensive unit test suite (115 tests)
