# Jinja2 Environment Renderer CLI

A command-line tool to render Jinja2 templated files with context variables.

![Tests Status](https://gitea.example.com/myuser/myrepo/actions/workflows/test.yml/badge.svg)

## Arguments
| Argument   | Type     | Description                                                                 |
| ---------- | -------- | --------------------------------------------------------------------------- |
| input_file | Optional | Single template file to render (positional argument).                       |

## Options
| Flag               | Type        | Default  | Description                                                             |
| ------------------ | ----------- | -------- | ----------------------------------------------------------------------- |
| `-l, --list`       | `str`       | `None`   | Comma-separated list of template files to render (e.g. `file1,file2`).  |
| `-f, --file-list`  | `str`       | `None`   | Path to a file containing a list of templates to render (one per line). |
| `-d, --dir`        | `str`       | `None`   | Render all files in a directory.                                        |
| `-r, --recursive`  | `bool`      | `False`  | Recurse into subdirectories when using `--dir`.                         |
| `-o, --output`     | `str`       | `stdout` | Directory to write rendered files. Omit to print to stdout.             |
| `-ow, --overwrite` | `bool`      | `False`  | Overwrite original files instead of writing to `--output`.              |
| `--env-file`       | `str`       | `.env`   | Path to a config file (`.toml`, `.json`, `.yaml/.yml`, or `.env`).      |
| `--templates-dir`  | `list[str]` | `None`   | Optional directory or directories with shared templates/partials.       |


## Examples

Render a single template to stdout:
```
python render.py templates/example.j2
```

Render multiple templates to an output directory:
```
python render.py -l templates/a.j2 templates/b.j2 -o output/
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