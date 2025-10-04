#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import jinja2
import sys
from dotenv import load_dotenv

def denv(ctx, default=""):
    """Return environment variable value, or default."""
    return os.environ.get(ctx, default)

def render_file(src_path: Path, env: jinja2.Environment) -> str:
    """Render a Jinja2 template file with env loader."""
    template = env.get_template(str(src_path))
    return template.render()

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

    if args.file:
        files.append(Path(args.file))

    if args.files:
        files.extend(Path(f) for f in args.files)

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
        description="Render Jinja2 templates with environment variables."
    )
    parser.add_argument("-f", "--file", help="Single file to render")
    parser.add_argument("-F", "--files", nargs="+", help="List of files to render")
    parser.add_argument("-l", "--file-list", help="File containing list of files to render (one per line)")
    parser.add_argument("-d", "--dir", help="Render all files in a directory")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recurse into directories")
    parser.add_argument("output_dir", nargs="?", help="Output directory (omit for stdout)")
    parser.add_argument("-ow", "--overwrite", action="store_true",
        help="Overwrite files in place instead of writing to output directory")
    parser.add_argument("--env-file", default=".env", help="Path to .env file (default: .env)")
    parser.add_argument("--templates-dir", nargs="+",
        help="Optional directory (or directories) with shared templates/partials"
    )

    args = parser.parse_args()

    # Load .env if present
    if args.env_file and Path(args.env_file).exists():
        load_dotenv(args.env_file)

    files = collect_files(args)
    if not files:
        print("No files to render.")
        return

    # Validate: stdout mode must be single file
    if not args.output_dir and not args.overwrite and len(files) > 1:
        parser.error("Rendering multiple files requires --overwrite or an output directory.")

    # Setup Jinja environment with file system loader
    search_paths = []
    if args.templates_dir:
        search_paths.extend(args.templates_dir)
    # Always include directories of individual source files
    search_paths.extend({str(f.parent) for f in files})
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(search_paths))
    env.filters["denv"] = denv

    for src in files:
        # Get relative path so includes work correctly
        rendered = render_file(src.relative_to(src.parent), env)

        if args.overwrite:
            write_rendered(src, rendered, src)
        elif args.output_dir:
            rel_path = src if not args.dir else src.relative_to(Path(args.dir))
            dest = Path(args.output_dir) / rel_path
            write_rendered(src, rendered, dest)
        else:
            write_rendered(src, rendered, None)

if __name__ == "__main__":
    main()
