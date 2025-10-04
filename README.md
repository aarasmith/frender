# Jinja2 Environment Renderer CLI

A command-line tool to render Jinja2 templates with environment variables.

## Usage
```
python render.py [options] [output_dir]
```

## Arguments
| Argument   | Type     | Description                                                 |
| ---------- | -------- | ----------------------------------------------------------- |
| output_dir | Optional | Directory to write rendered files. Omit to print to stdout. |


## Options
| Flag               | Type        | Default  | Description                                                           |
| ------------------ | ----------- | -------- | --------------------------------------------------------------------- |
| `-f, --file`       | `str`       | `None`   | Render a single template file.                                        |
| `-F, --files`      | `list[str]` | `None`   | Render multiple template files.                                       |
| `-l, --file-list`  | `str`       | `None`   | Path to a file containing list of templates to render (one per line). |
| `-d, --dir`        | `str`       | `None`   | Render all files in a directory.                                      |
| `-r, --recursive`  | `bool`      | `False`  | Recurse into subdirectories when using `--dir`.                       |
| `output_dir`       | `str`       | `stdout` | Directory to write rendered files. Omit to print to stdout.           |
| `-ow, --overwrite` | `bool`      | `False`  | Overwrite original files instead of writing to `output_dir`.          |
| `--env-file`       | `str`       | `.env`   | Path to `.env` file to load environment variables from.               |
| `--templates-dir`  | `list[str]` | `None`   | Optional directory or directories with shared templates/partials.     |

## Examples

Render a single template to stdout:
```
python render.py -f templates/example.j2
```

Render multiple templates to an output directory:
```
python render.py -F templates/a.j2 templates/b.j2 output/
```

Render all files in a directory recursively and overwrite originals:
```
python render.py -d templates/ -r -ow
```

Use a custom .env file and template directory:
```
python render.py -f templates/config.j2 --env-file .env.production --templates-dir templates/partials
```