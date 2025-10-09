#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
import jinja2
from dotenv import dotenv_values
import importlib.util
import fnmatch

class RenderError(Exception):
    """Custom exception for template rendering errors."""
    pass

# ---------------------------
# Context Loaders
# ---------------------------

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

def load_context(env_file: Path) -> dict:
    """Dispatch to the appropriate loader based on file extension."""
    if not env_file.exists():
        return {}

    suffix = env_file.suffix.lower()
    try:
        if suffix in {".yaml", ".yml"}:
            return load_yaml_file(env_file)
        elif suffix == ".json":
            return load_json_file(env_file)
        elif suffix == ".toml":
            return load_toml_file(env_file)
        elif suffix == ".ini":
            return load_ini_file(env_file)
        else:
            return load_env_file(env_file)
    except Exception as e:
        raise RenderError(f"Failed to load context from {env_file}: {e}")

# ---------------------------
# Rendering Helpers
# ---------------------------

def env_var(ctx, default=""):
    """Return environment variable value, or default."""
    return os.environ.get(ctx, default)

def render_file(src_path: Path, env: jinja2.Environment, context: dict) -> str:
    """Render a Jinja2 template file with env loader and provided context."""
    try:
        template = env.get_template(str(src_path))
        return template.render(**context)
    except Exception as e:
        raise RenderError(f"Failed to render template {src_path}: {e}")

def write_rendered(src: Path, rendered: str, dest: Path | None):
    """Write rendered string to dest, or stdout if dest is None."""
    try:
        if dest is None:
            sys.stdout.write(rendered)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered)
            print(f"Rendered: {src} -> {dest}")
    except Exception as e:
        raise RenderError(f"Failed to write rendered output for {src} -> {dest}: {e}")

# ---------------------------
# File collection
# ---------------------------

def get_exclude_patterns(args) -> list[Path]:
    exclude_patterns = []
    if args.exclude:
        exclude_patterns = [Path(x.strip()) for x in args.exclude.split(",") if x.strip()]
    return exclude_patterns

def is_excluded(path: Path, exclude_patterns: list[Path]) -> bool:
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False

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
            files.extend(p for p in dir_path.rglob("*") if p.is_file() and not is_excluded(p, exclude_patterns))
        else:
            files.extend(p for p in dir_path.glob("*") if p.is_file() and not is_excluded(p, exclude_patterns))

    if not files:
        raise RenderError("No input files collected. Use -l, -f, -d, or input_file.")

    return files

# ---------------------------
# Environment Setup
# ---------------------------

def register_filters(env: jinja2.Environment, filters_root: Path):
    """Recursively load Python files from filters_root and register callables as Jinja filters."""
    import importlib.util

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


def register_macros(env: jinja2.Environment, macros_dir: Path):
    """
    Recursively load all .j2 files from macros_dir and register macros globally.
    The macros_dir is added temporarily to the loader search path to resolve templates.
    """
    if not macros_dir or not macros_dir.exists():
        return

    # Add macros_dir to loader search paths temporarily
    if isinstance(env.loader, jinja2.FileSystemLoader):
        paths = list(env.loader.searchpath)
        env.loader.searchpath.append(str(macros_dir))
    else:
        paths = []

    try:
        for f in macros_dir.rglob("*.j2"):
            try:
                rel_path = f.relative_to(macros_dir)
                template = env.get_template(str(rel_path))
                for name, func in template.module.__dict__.items():
                    if callable(func) and not name.startswith("_"):
                        env.globals[name] = func
            except Exception as e:
                raise RenderError(f"Failed to load macros from {f}: {e}")
    finally:
        # Restore original search paths
        if paths:
            env.loader.searchpath = paths


def setup_environment(template_file: Path, macros_dir: Path | None = None, filters_dir: Path | None = None) -> jinja2.Environment:
    """
    Create a Jinja2 Environment with:
    - template_file.parent as loader path
    - optional macros registered from macros_dir
    - optional filters registered from filters_dir
    """
    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(template_file.parent)]))
    env.filters["env_var"] = env_var
    env.globals["env_var"] = env_var

    if macros_dir:
        register_macros(env, macros_dir)
    if filters_dir:
        register_filters(env, filters_dir)

    return env

# ---------------------------
# Config setup
# ---------------------------

def run_config_setup():
    config_dir = Path.home() / ".frender"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config"

    print("frender configuration setup")
    env_file = input("Path to your default env file (or leave blank): ").strip()
    macros_dir = input("Path to your macros directory (or leave blank): ").strip()
    filters_dir = input("Path to your filters directory (or leave blank): ").strip()

    # Expand '~', convert relative to absolute paths
    def expand(path):
        if not path:
            return ""
        return str((Path(path).expanduser().resolve()))

    lines = [
        f"ENV_FILE={expand(env_file)}",
        f"MACROS_DIR={expand(macros_dir)}",
        f"FILTERS_DIR={expand(filters_dir)}"
    ]

    config_path.write_text("\n".join(lines))
    print(f"Configuration saved to {config_path}")

def load_frender_config() -> dict:
    """Load the ~/.frender/config file if it exists."""
    config_path = Path.home() / ".frender" / "config"
    if not config_path.exists():
        return {}
    print(f"Using configuration at: {config_path}")
    return dotenv_values(config_path)

# ---------------------------
# Input validation
# ---------------------------

def validate_input_sources(args, parser):
    """Ensure only one input source is provided."""
    sources = [
        bool(args.input_file),
        bool(args.list),
        bool(args.file_list),
        bool(args.dir),
    ]
    if sum(sources) > 1:
        parser.error(
            "You can only provide one of input_file, -l/--list, -f/--file-list, or -d/--dir"
        )
    elif sum(sources) == 0:
        parser.error(
            "You must provide at least one input source: input_file, -l/--list, -f/--file-list, or -d/--dir"
        )

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
    parser.add_argument("-x", "--exclude", help="list of filename patterns to exclude when using --dir (supports wildcards, e.g. '*.bak,*.tmp,temp_*')")
    parser.add_argument("-o", "--output", help="Output directory to write rendered files")
    parser.add_argument("-sd", "--single-dir", action="store_true", help="Don't preserve full paths when writing to output directory")
    parser.add_argument("-ow", "--overwrite", action="store_true", help="Overwrite files in place")
    parser.add_argument("--env-file", help="Path to config file (.env, .toml, .yaml/.yml, .json, .ini)")
    parser.add_argument("--macros-dir", help="Directory containing Jinja macros to register globally")
    parser.add_argument("--filters-dir", help="Directory containing Python files to register as Jinja filters/globals")

    args = parser.parse_args()

    validate_input_sources(args, parser)

    config = load_frender_config()
    
    if not args.env_file:
        args.env_file = config.get("ENV_FILE") or ".env" # .env is default if none supplied
    args.macros_dir = args.macros_dir or config.get("MACROS_DIR")
    args.filters_dir = args.filters_dir or config.get("FILTERS_DIR")

    try:
        files = collect_files(args)

        if not args.output and not args.overwrite and len(files) > 1:
            parser.error("Rendering multiple files requires --overwrite or --output.")

        context = load_context(Path(args.env_file))
        macros_dir = Path(args.macros_dir) if args.macros_dir else None
        filters_dir = Path(args.filters_dir) if args.filters_dir else None

        for src in files:
            env = setup_environment(src, macros_dir=macros_dir, filters_dir=filters_dir)
            rendered = render_file(src.name, env, context)

            #in place
            if args.overwrite:
                write_rendered(src, rendered, src)
            
            #target directory
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
            
            # stdout
            else:
                write_rendered(src, rendered, None)

    except RenderError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[UNEXPECTED ERROR] {e}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
