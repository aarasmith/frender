#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
import jinja2
from dotenv import dotenv_values

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
        if args.recursive:
            files.extend(p for p in dir_path.rglob("*") if p.is_file())
        else:
            files.extend(p for p in dir_path.glob("*") if p.is_file())

    if not files:
        raise RenderError("No input files collected. Use -l, -f, -d, or input_file.")

    return files

# ---------------------------
# Environment Setup
# ---------------------------

def register_macros(env: jinja2.Environment, macros_dir: Path):
    """
    Recursively load all .j2 files from macros_dir and register macros globally.
    """
    if not macros_dir or not macros_dir.exists():
        return
    for f in macros_dir.rglob("*.j2"):
        try:
            rel_path = f.relative_to(macros_dir)
            template = env.get_template(str(rel_path))
            for name, func in template.module.__dict__.items():
                if callable(func) and not name.startswith("_"):
                    env.globals[name] = func
        except Exception as e:
            raise RenderError(f"Failed to load macros from {f}: {e}")

def setup_environment(template_file: Path, macros_dir: Path | None = None) -> jinja2.Environment:
    """
    Create a Jinja2 Environment for a given template.
    Automatically adds parent directory of template to search path.
    Optionally registers macros from macros_dir if provided.
    """
    search_paths = [str(template_file.parent)]
    if macros_dir:
        search_paths.append(str(macros_dir))

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(search_paths))
    env.filters["env_var"] = env_var
    env.globals["env_var"] = env_var

    if macros_dir:
        register_macros(env, macros_dir)

    return env

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
    parser.add_argument("-o", "--output", help="Output directory to write rendered files")
    parser.add_argument("-ow", "--overwrite", action="store_true", help="Overwrite files in place")
    parser.add_argument("--env-file", default=".env", help="Path to config file (.env, .toml, .yaml/.yml, .json, .ini)")
    parser.add_argument("--macros-dir", help="Directory containing Jinja macros to register globally")

    args = parser.parse_args()

    try:
        files = collect_files(args)

        if not args.output and not args.overwrite and len(files) > 1:
            parser.error("Rendering multiple files requires --overwrite or --output.")

        context = load_context(Path(args.env_file))
        macros_dir = Path(args.macros_dir) if args.macros_dir else None

        for src in files:
            env = setup_environment(src, macros_dir=macros_dir)
            rendered = render_file(src.name, env, context)

            if args.overwrite:
                write_rendered(src, rendered, src)
            elif args.output:
                rel_path = src if not args.dir else src.relative_to(Path(args.dir))
                dest = Path(args.output) / rel_path
                write_rendered(src, rendered, dest)
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
