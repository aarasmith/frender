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

class RenderError(Exception):
    """Custom exception for template rendering errors."""
    pass


def denv(ctx, default=""):
    """Return environment variable value, or default."""
    return os.environ.get(ctx, default)


def load_context(env_file: Path) -> dict:
    """Load context variables from env_file (.env, .toml, .yaml/.yml, .json)."""
    if not env_file.exists():
        return {}

    suffix = env_file.suffix.lower()
    try:
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
            return dotenv_values(env_file)
    except Exception as e:
        raise RenderError(f"Failed to load context from {env_file}: {e}")


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


def main():
    parser = argparse.ArgumentParser(
        description="Render Jinja2 templates with variables from .env, TOML, YAML, or JSON."
    )
    parser.add_argument("input_file", nargs="?", help="Single file to render")
    parser.add_argument("-l", "--list", help="Comma-separated list of files to render (e.g. file1,file2,file3)")
    parser.add_argument("-f", "--file-list", help="File containing list of templates to render (one per line)")
    parser.add_argument("-d", "--dir", help="Render all files in a directory")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories when using --dir")
    parser.add_argument("-o", "--output", help="Output directory to write rendered files. Omit to print to stdout.")
    parser.add_argument("-ow", "--overwrite", action="store_true",
                        help="Overwrite files in place instead of writing to --output")
    parser.add_argument("--env-file", default=".env",
                        help="Path to config file (.env, .toml, .yaml/.yml, or .json). Default: .env")
    parser.add_argument("--templates-dir", nargs="+",
                        help="Optional directory (or directories) with shared templates/partials"
                        )

    args = parser.parse_args()

    try:
        files = collect_files(args)

        if not args.output and not args.overwrite and len(files) > 1:
            parser.error("Rendering multiple files requires --overwrite or --output.")

        context = load_context(Path(args.env_file))

        # Build Jinja environment
        search_paths = []
        if args.templates_dir:
            search_paths.extend(args.templates_dir)
        search_paths.extend([str(f.parent) for f in files])
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(search_paths))
        env.filters["denv"] = denv

        for src in files:
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
