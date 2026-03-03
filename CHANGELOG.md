# Changelog

## [1.0.0] - 2026-03-03

### Added

- **`--var NAME=VALUE`** — Set template variables directly on the command line without a config
  file. Can be specified multiple times. Values may contain spaces when quoted. Takes final
  precedence over all other variable sources.
- **`--file-var NAME=PATH`** — Inject the raw UTF-8 contents of a file into the template context
  under a named variable. Can be specified multiple times.
- **`--init`** — Write a commented YAML config template to `~/.frender/config.yaml` and exit.
  Replaces the previous interactive `frender config` wizard.
- **`--macros-dir` now repeatable** — `--macros-dir` can now be specified multiple times to
  register macros from several directories in a single invocation.
- **`--filters-dir` now repeatable** — Same as above for filter directories.
- **Multi-directory macro registry** — Macros registered across multiple `--macros-dir`
  directories can call each other without explicit `{% import %}` statements, at any nesting
  depth, regardless of directory registration order. This uses a dbt-style call-time context
  injection pattern (`MacroCallable`) that reconstructs the full macro registry on every
  invocation.
- **Macro and filter override semantics** — When multiple directories export the same macro or
  filter name, the later directory takes precedence. Same-filename collisions are handled
  correctly via searchpath ordering and Jinja cache invalidation.
- **Variable collision warnings** — A `WARNING`-level log message is emitted whenever a key is
  silently overridden: when later `--env-file` values override earlier ones, when `--file-var`
  overrides an env file key, and when `--var` overrides any previously set key.
- **`--verbose` / `-v`** — Enable `DEBUG`-level logging, including macro discovery details,
  searchpath state, and filter registration.
- **`--silent` / `-s`** — Suppress all log output. Useful when capturing stdout in scripts.
  Mutually exclusive with `--verbose`.
- **`jinja2.ext.loopcontrols` and `jinja2.ext.do` extensions** — Enabled globally on all
  Jinja environments, making `{% break %}`, `{% continue %}`, and `{% do %}` available in
  all templates.
- **Jinja environment reuse across files** — When rendering multiple files, a single Jinja
  environment is now created and reused, with additional template directories appended to the
  searchpath as needed. Previously a new environment was created per file.

### Changed

- **Config format changed from dotenv to YAML** — `~/.frender/config` (dotenv-style, single
  values only) has been replaced by `~/.frender/config.yaml`. The new format supports list
  values, enabling multiple default `env_files`, `macros_dirs`, and `filters_dirs` to be
  declared. Existing `~/.frender/config` files are not read and must be migrated manually.
- **Config merge semantics changed** — Previously, CLI arguments replaced config values.
  Config values are now the base layer and CLI arguments extend them: paths from config and
  paths from the CLI are both active simultaneously.
- **Removed implicit `.env` fallback** — Previously, if no `--env-file` was specified, frender
  would silently load `.env` from the current directory. This behaviour has been removed. Env
  files must now be specified explicitly via `--env-file` or via `~/.frender/config.yaml`.
- **Missing env files are now skipped with a warning** — Previously, a missing env file caused
  `load_context` to return an empty dict immediately, silently discarding any files that had
  already been loaded. Missing files are now logged at `WARNING` level and skipped, allowing
  remaining files to load normally.
- **All output now goes through `logging`** — Progress messages and errors previously written
  via `print()` are now routed through the `frender` logger at appropriate levels (`INFO` for
  render confirmations, `WARNING` for collisions and skipped files, `ERROR` for fatal errors).
  This means output respects `--silent` and `--verbose`, and integrates cleanly with logging
  pipelines.

### Fixed

- **Macro cross-directory calls** — Macros in one `--macros-dir` could not call macros from
  another directory. The new `MacroCallable` registry injects the full macro context at call
  time, resolving this at any depth.
- **Same-filename macro override** — When two macro directories contained files with identical
  names, Jinja's `FileSystemLoader` would always resolve to the first directory regardless of
  registration order. This is now fixed by prepending later directories to the searchpath and
  clearing Jinja's parse and template caches after each modification.
- **`load_context` early return on missing file** — A missing file caused the function to
  return `{}` immediately rather than continuing to load subsequent files in the list.

### Removed

- **Interactive config wizard (`frender config` / `run_config_setup`)** — Replaced by
  `frender --init`, which writes a commented YAML template that users edit directly.