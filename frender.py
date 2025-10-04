#!/usr/bin/env python3
import argparse
import os
import sys
import json
from pathlib import Path
import tomllib
import jinja2
import yaml
from dotenv import dotenv_values


def denv(ctx, default=""):
    """Return environment variable value, or default."""
    return os.environ.get(ctx, default)


def load_context(env_file: Path) -> dict:
    """Load context variables from env_file (.env, .toml, .yaml/.yml, .json)."""
    if not env_file.exists():
        return {}

    suffix = env_file.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        with open(env_file, "r") as f:
            return yaml.safe_load(f) or {}
    elif suffix == ".json":
        with open(env_file, "r") as f:
            return json.load(f) or {}
    elif suffix == ".toml":
        with open(env_file, "rb") as f:
            return tomllib.load(f) or {}
    else:
        # Default: .env style (key=value)
        return dotenv_values(env_file)


def render_file(src_path: Path, env: jinja2.Environment, context: dict) -> str:
    """Render a Jinja2 template file with env loader and provided context."""
    template = env.get_template(str(src_path))
    return template.render(**context)


def write_rendered(src: Path, rendered: str, dest: Path | None):
    """Write rendered string to dest, or stdout if dest is None."""
    if dest is None:
        sys.stdout.write(rendered)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered)
        print(f"Rendered: {src} -> {dest}")


def collect_files(args) -> list[Path]:
    """Collect files based on CLI args."""
    files = []
    if args.input_file:
        files.append(Path(args.input_file))
    if args.list:
        # split comma-separated list, remove whitespace
        files_from_list = [Path(f.strip()) for f in args.list.split(",") if f.strip()]
        files.extend(files_from_list)
    if args.file_list:
        with open(args.file_list, "r") as f:
            for line in f:
                path = line.strip()
                if path:
                    files.append(Path(path))
    if args.dir:
        dir_path = Path(args.dir)
        if args.recursive:
            files.extend(p for p in dir_path.rglob("*") if p.is_file())
        else:
            files.extend(p for p in dir_path.glob("*") if p.is_file())
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Render Jinja2 templates with variables from .env, YAML, or JSON."
    )
    parser.add_argument("input_file", nargs="?", help="Single file to render")
    parser.add_argument("-l", "--list", help="Comma-separated list of files to render (e.g. file1,file2,file3)")
    parser.add_argument("-f", "--file-list", help="File containing list of files to render (one per line)")
    parser.add_argument("-d", "--dir", help="Render all files in a directory")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories")
    parser.add_argument("-o", "--output", help="Output directory to write rendered files. Omit to print to stdout.")
    parser.add_argument("-ow", "--overwrite", action="store_true",
        help="Overwrite files in place instead of writing to output directory")
    parser.add_argument("--env-file", default=".env",
        help="Path to env file (supports .env, .yaml/.yml, .json). Default: .env")
    parser.add_argument("--templates-dir", nargs="+",
        help="Optional directory (or directories) with shared templates/partials"
    )

    args = parser.parse_args()

    files = collect_files(args)
    if not files:
        print("No files to render.")
        return

    if not args.output and not args.overwrite and len(files) > 1:
        parser.error("Rendering multiple files requires --overwrite or an output directory.")

    # Load context from env/yaml/json
    context = load_context(Path(args.env_file))

    # Build Jinja environment
    search_paths = []
    if args.templates_dir:
        search_paths.extend(args.templates_dir)
    search_paths.extend({str(f.parent) for f in files})
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(search_paths))
    env.filters["denv"] = denv

    for src in files:
        rendered = render_file(src.relative_to(src.parent), env, context)

        if args.overwrite:
            write_rendered(src, rendered, src)
        elif args.output:
            rel_path = src if not args.dir else src.relative_to(Path(args.dir))
            dest = Path(args.output) / rel_path
            write_rendered(src, rendered, dest)
        else:
            write_rendered(src, rendered, None)


if __name__ == "__main__":
    main()
