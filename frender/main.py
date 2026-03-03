#!/usr/bin/env python3

"""
frender - Jinja2 template renderer

Renders Jinja2 templates with variables from .env, TOML, YAML, JSON, or INI files.
Supports globally registered macros and filters, multi-file rendering, and a persistent
~/.frender/config.yaml for project defaults.

Entry point: main()

Variable priority (lowest to highest): --env-file < --file-var < --var
"""

import argparse
import fnmatch
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import jinja2
from dotenv import dotenv_values

logger = logging.getLogger("frender")


class RenderError(Exception):
    """Custom exception for template rendering errors."""
    pass


# ---------------------------
# Main CLI
# ---------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Render Jinja2 templates with variables from .env, TOML, YAML, JSON, or INI."
    )
    parser.add_argument("input_file", nargs="?", help="Single file to render")
    parser.add_argument("-l", "--list", help="Comma-separated list of files to render")
    parser.add_argument("-f", "--file-list", help="File containing list of templates to render (one per line)")
    parser.add_argument("-d", "--dir", help="Render all files in a directory")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories when using --dir")
    parser.add_argument("-x", "--exclude", help="Filename patterns to exclude when using --dir (e.g. '*.bak,*.tmp,temp_*')")
    parser.add_argument("-o", "--output", help="Output directory to write rendered files")
    parser.add_argument("-sd", "--single-dir", action="store_true", help="Don't preserve full paths when writing to output directory")
    parser.add_argument("-ow", "--overwrite", action="store_true", help="Overwrite files in place")
    parser.add_argument("--var", action="append", metavar="NAME=VALUE", help="Set a template variable. Supports spaces when quoted. Can be specified multiple times.")
    parser.add_argument("--env-file", action="append", help="Path to a variable file (.env, .toml, .yaml/.yml, .json, .ini). Can be specified multiple times.")
    parser.add_argument("--file-var", action="append", metavar="NAME=PATH", help="Inject file contents as a Jinja variable. Can be used multiple times.")
    parser.add_argument("--macros-dir", action="append", help="Directory containing Jinja macros to register globally. Can be specified multiple times.")
    parser.add_argument("--filters-dir", action="append", help="Directory containing Python files to register as Jinja filters/globals. Can be specified multiple times.")
    parser.add_argument("--init", action="store_true", help="Write a starter config to ~/.frender/config.yaml and exit.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug output.")
    parser.add_argument("-s", "--silent", action="store_true", help="Suppress all logging output. Mutually exclusive with --verbose.")

    args = parser.parse_args()

    if args.init:
        init_config()
        sys.exit(0)

    if args.silent and args.verbose:
        parser.error("--silent and --verbose are mutually exclusive")

    if args.silent:
        log_level = logging.CRITICAL
    elif args.verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    try:
        validate_input_sources(args, parser)

        config = load_frender_config()

        # Config provides the base layer; CLI args extend it (config first, CLI after)
        args.env_file    = config.get("env_files",    []) + (args.env_file    or [])
        args.macros_dir  = config.get("macros_dirs",  []) + (args.macros_dir  or [])
        args.filters_dir = config.get("filters_dirs", []) + (args.filters_dir or [])

        files = collect_files(args)

        if not args.output and not args.overwrite and len(files) > 1:
            parser.error("Rendering multiple files requires --overwrite or --output.")

        context = build_context(args.env_file, args.file_var, args.var)

        macro_dirs  = [Path(p) for p in (args.macros_dir  or [])]
        filter_dirs = [Path(p) for p in (args.filters_dir or [])]

        env = None
        for src in files:
            if env is None:
                env = setup_environment(src, macro_dirs=macro_dirs, filter_dirs=filter_dirs)
            else:
                # If the next file is in another folder, add it to the search path
                if isinstance(env.loader, jinja2.FileSystemLoader):
                    parent = str(src.parent)
                    if parent not in env.loader.searchpath:
                        env.loader.searchpath.append(parent)

            rendered = render_file(src.name, env, context)

            if args.overwrite:
                write_rendered(src, rendered, src)

            elif args.output:
                flatten = False
                if args.input_file or args.list:
                    flatten = True
                elif args.file_list or args.dir:
                    flatten = args.single_dir

                if flatten:
                    dest = Path(args.output) / src.name
                else:
                    rel_path = src if not args.dir else src.relative_to(Path(args.dir))
                    dest = Path(args.output) / rel_path

                write_rendered(src, rendered, dest)

            else:
                write_rendered(src, rendered, None)

    except RenderError as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        sys.exit(2)


# ---------------------------
# Input Validation
# ---------------------------

def validate_input_sources(args, parser) -> None:
    """Ensure exactly one input source is provided."""
    sources = [bool(args.input_file), bool(args.list), bool(args.file_list), bool(args.dir)]
    if sum(sources) > 1:
        parser.error(
            "You can only provide one of input_file, -l/--list, -f/--file-list, or -d/--dir"
        )
    elif sum(sources) == 0:
        parser.error(
            "You must provide at least one input source: input_file, -l/--list, -f/--file-list, or -d/--dir"
        )


# ---------------------------
# File Collection
# ---------------------------

def collect_files(args) -> list[Path]:
    """Collect files based on CLI args."""
    files = []

    if args.input_file:
        f = Path(args.input_file)
        if not f.is_file():
            raise RenderError(f"Input file not found: {f}")
        files.append(f)

    if args.list:
        for f in [Path(x.strip()) for x in args.list.split(",") if x.strip()]:
            if not f.is_file():
                raise RenderError(f"File in list not found: {f}")
            files.append(f)

    if args.file_list:
        flist = Path(args.file_list)
        if not flist.is_file():
            raise RenderError(f"File list not found: {flist}")
        with open(flist, "r") as f:
            for line in f:
                path = line.strip()
                if path:
                    p = Path(path)
                    if not p.is_file():
                        raise RenderError(f"File listed not found: {p}")
                    files.append(p)

    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            raise RenderError(f"Directory not found: {dir_path}")
        exclude_patterns = get_exclude_patterns(args)
        if args.recursive:
            files.extend(
                p for p in dir_path.rglob("*")
                if p.is_file() and not is_excluded(p, exclude_patterns)
            )
        else:
            files.extend(
                p for p in dir_path.glob("*")
                if p.is_file() and not is_excluded(p, exclude_patterns)
            )

    if not files:
        raise RenderError("No input files collected. Use -l, -f, -d, or input_file.")

    return files


def get_exclude_patterns(args) -> list[Path]:
    if args.exclude:
        return [Path(x.strip()) for x in args.exclude.split(",") if x.strip()]
    return []


def is_excluded(path: Path, exclude_patterns: list[Path]) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in exclude_patterns)


# ---------------------------
# Context Loaders
# ---------------------------

def build_context(env_files: list, file_var_args: list, var_args: list) -> dict:
    """
    Assemble the final render context from all variable sources in priority order:
    env files < --file-var < --var. Warns on any key collision across sources.
    """
    context = context_merger(load_context([Path(f) for f in env_files]))

    file_vars = load_file_vars(file_var_args)
    for key in file_vars:
        if key in context:
            logger.warning("[context] --file-var '%s' overrides key from env file", key)
    context.update(file_vars)

    cli_vars = load_vars(var_args)
    for key in cli_vars:
        if key in context:
            logger.warning("[context] --var '%s' overrides previously set key", key)
    context.update(cli_vars)

    return context


def context_merger(context: list[dict]) -> dict:
    """Merge a list of dicts in order; warn on key collisions."""
    merged_context = {}
    for d in context:
        for key in d:
            if key in merged_context:
                logger.warning(
                    "[context] Key '%s' from later env file overrides earlier value", key
                )
        merged_context |= d
    return merged_context


def load_context(env_files: list[Path]) -> list[dict]:
    """Dispatch to the appropriate loader based on file extension."""
    loaded_files = []
    for env_file in env_files:
        if not env_file.exists():
            logger.warning("[context] Env file not found, skipping: %s", env_file)
            continue
        suffix = env_file.suffix.lower()
        try:
            if suffix in {".yaml", ".yml"}:
                loaded_files.append(load_yaml_file(env_file))
            elif suffix == ".json":
                loaded_files.append(load_json_file(env_file))
            elif suffix == ".toml":
                loaded_files.append(load_toml_file(env_file))
            elif suffix == ".ini":
                loaded_files.append(load_ini_file(env_file))
            else:
                loaded_files.append(load_env_file(env_file))
        except Exception as e:
            raise RenderError(f"Failed to load context from {env_file}: {e}")
    return loaded_files


def load_vars(var_args: list[str]) -> dict[str, str]:
    """Parse --var NAME=VALUE items into a dict. Value is treated as raw text (UTF-8 str)."""
    vars_dict: dict[str, str] = {}
    for item in var_args or []:
        if "=" not in item:
            raise RenderError(f"--var must be in NAME=VALUE format (got '{item}')")
        name, value = item.split("=", 1)
        if not name.isidentifier():
            raise RenderError(f"Invalid variable name for --var: '{name}'")
        # VALUE is used as-is; quoting is handled by the shell before it reaches us.
        vars_dict[name] = value
    return vars_dict


def load_file_vars(file_var_args) -> dict:
    """Parse --file-var NAME=PATH items, reading each file's contents as a string."""
    file_vars = {}
    for item in file_var_args or []:
        if "=" not in item:
            raise RenderError(f"--file-var must be in NAME=PATH format (got '{item}')")
        name, path = item.split("=", 1)
        if not name.isidentifier():
            raise RenderError(f"Invalid jinja variable name for --file-var: '{name}'")
        file_path = Path(path)
        if not file_path.exists():
            raise RenderError(f"--file-var file does not exist: {file_path}")
        if not file_path.is_file():
            raise RenderError(f"--file-var path is not a file: {file_path}")
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise RenderError(f"File '{file_path}' is not valid UTF-8 text") from e
        file_vars[name] = content
    return file_vars


def load_env_file(env_file: Path) -> dict:
    """Load dotenv-style file (key=value)."""
    return dotenv_values(env_file)


def load_json_file(env_file: Path) -> dict:
    """Load JSON config."""
    import json
    with open(env_file, "r") as f:
        return json.load(f) or {}


def load_yaml_file(env_file: Path) -> dict:
    """Load YAML config."""
    import yaml
    with open(env_file, "r") as f:
        return yaml.safe_load(f) or {}


def load_toml_file(env_file: Path) -> dict:
    """Load TOML config."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    with open(env_file, "rb") as f:
        return tomllib.load(f) or {}


def load_ini_file(env_file: Path) -> dict:
    """Load INI config (sections -> dicts)."""
    import configparser
    parser = configparser.ConfigParser()
    parser.read(env_file)
    return {section: dict(parser.items(section)) for section in parser.sections()}


# ---------------------------
# Rendering Helpers
# ---------------------------

def render_file(src_path: Path, env: jinja2.Environment, context: dict) -> str:
    """Render a Jinja2 template file with env loader and provided context."""
    try:
        template = env.get_template(str(src_path))
        return template.render(**context)
    except Exception as e:
        raise RenderError(f"Failed to render template {src_path}: {e}")


def write_rendered(src: Path, rendered: str, dest: Path | None) -> None:
    """Write rendered string to dest, or stdout if dest is None."""
    try:
        if dest is None:
            sys.stdout.write(rendered)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered)
            logger.info("Rendered: %s -> %s", src, dest)
    except Exception as e:
        raise RenderError(f"Failed to write rendered output for {src} -> {dest}: {e}")


# ---------------------------
# Environment Setup
# ---------------------------

def setup_environment(
    template_file: Path,
    macro_dirs: Optional[List[Path]] = None,
    filter_dirs: Optional[List[Path]] = None,
) -> jinja2.Environment:

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader([str(template_file.parent)]),
        extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"],
    )
    env.filters["env_var"] = env_var
    env.globals["env_var"] = env_var

    logger.debug("[setup] Template dir: %s", template_file.parent)
    logger.debug("[setup] Initial loader.searchpath: %s", env.loader.searchpath)

    if macro_dirs:
        logger.debug("[setup] Declared macro roots:")
        for d in macro_dirs:
            logger.debug("  DIR: %s  ABS: %s  EXISTS: %s", d, d.resolve(), d.exists())
        for mdir in macro_dirs:
            if not mdir or not mdir.exists():
                continue
            register_macros(env, mdir)

    if filter_dirs:
        logger.debug("[setup] Declared filter roots:")
        for d in filter_dirs:
            logger.debug("  DIR: %s  ABS: %s  EXISTS: %s", d, d.resolve(), d.exists())
            register_filters(env, d)

    return env


def env_var(ctx, default=""):
    """Return environment variable value, or default."""
    return os.environ.get(ctx, default)


def register_filters(env: jinja2.Environment, filters_root: Path) -> None:
    """Recursively load Python files from filters_root and register callables as Jinja filters."""
    if not filters_root.exists():
        return
    for f in filters_root.rglob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name in dir(module):
                func = getattr(module, name)
                if callable(func) and not name.startswith("_"):
                    env.filters[name] = func
                    env.globals[name] = func
        except Exception as e:
            raise RenderError(f"Failed to load filters from {f}: {e}")


class MacroCallable:
    """
    Wraps a macro so that calling it reconstructs a template module with a full
    context that includes all macro callables (registry) plus any other globals
    (e.g. env_var), so nested calls work at any depth.

    Similar in spirit to dbt's CallableMacroGenerator: re-get the template,
    make a module with vars=context, fetch the macro, and invoke it.
    """
    def __init__(
        self,
        env: jinja2.Environment,
        template_name: str,
        macro_name: str,
        registry_ref: Dict[str, Callable],
        extra_globals: Dict[str, Any],
    ) -> None:
        self.env = env
        self.template_name = template_name
        self.macro_name = macro_name
        self.registry_ref = registry_ref
        self.extra_globals = extra_globals

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # Build a call-time context containing ALL macro callables and extra globals.
        call_ctx: Dict[str, Any] = {}
        call_ctx.update(self.registry_ref)
        call_ctx.update(self.extra_globals)

        # Compile the template module with the call-time context so names used
        # inside this macro's body (and any nested calls) resolve correctly.
        tmpl = self.env.get_template(self.template_name)
        module = tmpl.make_module(vars=call_ctx)
        try:
            macro = getattr(module, self.macro_name)
        except AttributeError as e:
            raise RenderError(
                f"[macro] Missing macro '{self.macro_name}' in template '{self.template_name}'"
            ) from e
        return macro(*args, **kwargs)


def register_macros(env: jinja2.Environment, macros_dir: Path) -> None:
    """
    Build a dbt-style macro registry:

    1) Add macros_dir to loader.searchpath (inserted at front so later dirs take priority).
    2) Collect files deterministically; compile with vars={} to discover exported macro names.
    3) Warn on name collision; later directory wins.
    4) Create MacroCallable wrappers for each macro and publish to env.globals.

    The wrapper reconstructs the template module with a full context at call time,
    so nested macro calls (A->B->C...) resolve correctly regardless of registration order.
    """
    if not macros_dir or not macros_dir.exists():
        logger.warning("[macros] macros_dir missing/empty: %s", macros_dir)
        return

    if isinstance(env.loader, jinja2.FileSystemLoader):
        if str(macros_dir) not in env.loader.searchpath:
            env.loader.searchpath.insert(0, str(macros_dir))
            if hasattr(env, '_parse_cache'):
                env._parse_cache.clear()
            if hasattr(env, 'cache') and hasattr(env.cache, 'clear'):
                env.cache.clear()
    else:
        logger.warning("[macros] non-FileSystemLoader; searchpath tweaks skipped")

    try:
        files: List[Path] = sorted(
            [f for f in macros_dir.rglob("*") if f.is_file()]
        )

        logger.debug("[macros] Scanning dir: %s (%d files)", macros_dir, len(files))
        for f in files:
            logger.debug("  - %s", f)

        discovered: Dict[str, str] = {}
        name_to_file: Dict[str, Path] = {}

        for f in files:
            rel = f.relative_to(macros_dir)
            logger.debug("[macros][DISCOVER] %s as %s", f, rel)
            try:
                tmpl = env.get_template(str(rel))
                mod = tmpl.make_module(vars={})
                exports = []
                for name in dir(mod):
                    obj = getattr(mod, name, None)
                    if callable(obj) and not name.startswith("_"):
                        exports.append(name)
                        if name in discovered:
                            logger.warning(
                                "[macros] Macro '%s' from %s overrides previous definition from %s",
                                name, rel, name_to_file[name]
                            )
                        discovered[name] = str(rel)
                        name_to_file[name] = rel
                logger.debug("[macros][DISCOVER] %s exports: %s", rel, exports)
            except Exception as e:
                raise RenderError(f"Failed to discover macros from {f}: {e}")

        logger.debug(
            "[macros] Registered %d macros: %s", len(discovered), sorted(discovered.keys())
        )

        registry: Dict[str, Callable] = {}

        extra_globals: Dict[str, Any] = {}
        for k, v in env.globals.items():
            if k not in discovered:
                extra_globals[k] = v
        for k, v in env.filters.items():
            if k not in discovered and k not in extra_globals:
                extra_globals[k] = v

        for macro_name, template_name in discovered.items():
            registry[macro_name] = MacroCallable(
                env=env,
                template_name=template_name,
                macro_name=macro_name,
                registry_ref=registry,
                extra_globals=extra_globals,
            )

        env.globals.update(registry)

    except RenderError:
        raise
    except Exception as e:
        raise RenderError(f"Failed to register macros from {macros_dir}: {e}") from e


# ---------------------------
# Config
# ---------------------------

CONFIG_TEMPLATE = """\
# frender configuration file
# All paths support ~ expansion and can be relative or absolute.

# Default environment/variable files (loaded in order, later files override earlier ones)
# env_files:
#   - ~/.frender/defaults.env
#   - ~/projects/common.yaml

# Macro directories (loaded in order, later directories override earlier ones)
# macros_dirs:
#   - ~/frender/macros

# Filter directories
# filters_dirs:
#   - ~/frender/filters
"""


def init_config() -> None:
    """Write a commented config template to ~/.frender/config.yaml if it doesn't exist."""
    config_dir = Path.home() / ".frender"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.yaml"

    if config_path.exists():
        print(f"Config already exists at {config_path}")
        return

    config_path.write_text(CONFIG_TEMPLATE)
    print(f"Config template written to {config_path}")
    print("Edit it to set your defaults, then run frender as normal.")


def load_frender_config() -> dict:
    """Load ~/.frender/config.yaml if it exists. Returns a dict with list values."""
    config_path = Path.home() / ".frender" / "config.yaml"
    if not config_path.exists():
        return {}
    logger.debug("Using configuration at: %s", config_path)
    try:
        raw = load_yaml_file(config_path) or {}
    except Exception as e:
        raise RenderError(f"Failed to load frender config: {e}")

    # Normalise all path lists: expand ~ and resolve relative paths
    def expand_paths(key):
        return [str(Path(p).expanduser().resolve()) for p in raw.get(key) or []]

    return {
        "env_files":    expand_paths("env_files"),
        "macros_dirs":  expand_paths("macros_dirs"),
        "filters_dirs": expand_paths("filters_dirs"),
    }


if __name__ == "__main__":
    main()