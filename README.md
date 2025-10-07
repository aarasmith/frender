# Jinja2 Environment Renderer CLI

![Tests Status](https://git.arasmith.org/admin/frender/actions/workflows/test.yaml/badge.svg)

A command-line tool to render Jinja2 templated files with context variables.

## Arguments
| Argument   | Type     | Description                                                                                    |
| ---------- | -------- | ---------------------------------------------------------------------------------------------- |
| input_file | Optional | Single template file to render (positional argument). Use `config` to run configuration setup. |


## Options
| Flag                | Type   | Default  | Description                                                                                         |
| ------------------- | ------ | -------- | --------------------------------------------------------------------------------------------------- |
| `-l, --list`        | `str`  | `None`   | List of template files to render (comma-separated, e.g. `file1,file2`).                             |
| `-f, --file-list`   | `str`  | `None`   | Path to a file containing a list of templates to render (one per line).                             |
| `-d, --dir`         | `str`  | `None`   | Render all files in a directory.                                                                    |
| `-r, --recursive`   | `bool` | `False`  | Recurse into subdirectories when using `--dir`.                                                     |
| `-x, --exclude`     | `str`  | `None`   | Patterns to exclude when using `--dir` (supports glob/wildcards, e.g. `*.bak,*.tmp,temp_*`).        |
| `-o, --output`      | `str`  | `stdout` | Directory to write rendered files. Omit to print to stdout.                                         |
| `-sd, --single-dir` | `bool` | `False`  | Don’t preserve subdirectory structure when writing to `--output`; all files go into one directory.  |
| `-ow, --overwrite`  | `bool` | `False`  | Overwrite original files instead of writing to `--output`.                                          |
| `--env-file`        | `str`  | `.env`   | Path to a config file (`.toml`, `.json`, `.yaml/.yml`, or `.env`).                                  |
| `--macros-dir`      | `str`  | `None`   | Directory containing Jinja macros to register globally for all templates.                           |
| `--filters-dir`     | `str`  | `None`   | Directory containing Python files with functions to register as Jinja filters and globals.          |


## Examples

Render a single template to stdout:
```
frender templates/example.j2
```

Render multiple templates to an output directory:
```
frender -l templates/a.j2 templates/b.j2 -o output/
```

Render templates from a file list:
```
python render.py -f filelist.txt -o output/
```

Render all files in a directory recursively and overwrite originals:
```
python render.py -d templates/ -r -ow
```

Use a custom config file (TOML, YAML, JSON, or .env) and template directory:
```
python render.py templates/config.j2 --env-file config.toml --templates-dir templates/partials
```