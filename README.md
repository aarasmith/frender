# Jinja2 Environment Renderer CLI

![Tests Status](https://git.arasmith.org/admin/frender/actions/workflows/test.yaml/badge.svg)

A command-line tool to render Jinja2 templated files with context variables, custom macros, and custom filters.

## Arguments
| Argument   | Type     | Description                                                                                    |
| ---------- | -------- | ---------------------------------------------------------------------------------------------- |
| input_file | Optional | Single template file to render (positional argument). Use `config` to run configuration setup. |


## Options
| Flag                | Type   | Default  | Description                                                                                         |
| ------------------- | ------ | -------- | --------------------------------------------------------------------------------------------------- |
| `-l, --list`        | `str`  | `None`   | List of template files to render (comma-separated, e.g. `file1,file2`).                            |
| `-f, --file-list`   | `str`  | `None`   | Path to a file containing a list of templates to render (one per line).                            |
| `-d, --dir`         | `str`  | `None`   | Render all files in a directory.                                                                   |
| `-r, --recursive`   | `bool` | `False`  | Recurse into subdirectories when using `--dir`.                                                    |
| `-x, --exclude`     | `str`  | `None`   | Patterns to exclude when using `--dir` (supports glob/wildcards, e.g. `*.bak,*.tmp,temp_*`).       |
| `-o, --output`      | `str`  | `None`   | Directory to write rendered files. Omit to print to stdout.                                        |
| `-sd, --single-dir` | `bool` | `False`  | Don't preserve subdirectory structure when writing to `--output`; all files go into one directory. |
| `-ow, --overwrite`  | `bool` | `False`  | Overwrite original files instead of writing to `--output`.                                         |
| `--env-file`        | `str`  | `None`   | Path to a variable file (`.env`, `.toml`, `.yaml/.yml`, `.json`, `.ini`). Can be used multiple times. |
| `--var`             | `str`  | `None`   | Set a template variable. Supports spaces when quoted. Can be used multiple times. `NAME=VALUE`.    |
| `--file-var`        | `str`  | `None`   | Inject file contents as a Jinja variable. Can be used multiple times. `NAME=PATH`.                 |
| `--macros-dir`      | `str`  | `None`   | Directory containing Jinja macros to register globally. Can be used multiple times.                |
| `--filters-dir`     | `str`  | `None`   | Directory containing Python files with functions to register as Jinja filters and globals. Can be used multiple times. |
| `--init`            | `bool` | `False`  | Write a starter config to `~/.frender/config.yaml` and exit.                                       |
| `-v, --verbose`     | `bool` | `False`  | Enable verbose debug output.                                                                        |
| `-s, --silent`      | `bool` | `False`  | Suppress all logging output. Useful when redirecting stdout. Mutually exclusive with `--verbose`.   |

## Examples

### Render a single template to stdout
```
frender templates/example.j2
```
Renders `example.j2` to stdout. Multiple files require either `--output` or `--overwrite`.

### Render a single template in place
```
frender templates/example.j2 -ow
```
Overwrites the input file with the rendered result.

### Render multiple templates to an output directory
```
frender -l templates/a.j2,templates/b.j2 -o output/
```
Output files are written directly into the target directory, without preserving subdirectory structure (`templates/subdir/a.j2` becomes `output/a.j2`).

### Render templates listed in a file
```
frender -f filelist.txt -o output/
```
Each line of `filelist.txt` should contain a path to a template. Directory structure is preserved by default (`templates/subdir/template.yml` becomes `output/subdir/template.yml`). Use `--single-dir` to flatten output into a single directory.

### Render all files in a directory
```
frender -d templates/ -o output/
```
Recursively, overwriting in place:
```
frender -d templates/ -r -ow
```

### Exclude files when rendering a directory
```
frender -d templates/ -o output/ -x "*.bak,*.tmp,temp_*"
```

### Load variables from a config file
```
frender templates/config.j2 --env-file config.toml
frender templates/config.j2 --env-file config.yaml
frender templates/config.j2 --env-file config.json
frender templates/config.j2 --env-file .env
```
Multiple files can be specified and are merged in order — later files take precedence on key collision:
```
frender templates/config.j2 --env-file base.yaml --env-file overrides.env
```

### Set variables directly on the command line
```
frender templates/example.j2 --var env=prod --var title="Hello World"
```
`--var` takes final precedence over all other variable sources. Values may include spaces when quoted.

### Inject a file's contents as a template variable
```
frender templates/example.j2 --file-var body=content/body.txt
```
Reads the entire contents of a UTF-8 text file and injects it into the template context under the given variable name.

### Register macros and filters
```
frender templates/example.j2 -o output/ --macros-dir macros/ --filters-dir filters/
```
Multiple directories can be specified for each. Later directories take precedence on name collision.

### Set up a config file
```
frender --init
```
Creates a commented template at `~/.frender/config.yaml`. Set default `env_files`, `macros_dirs`, and `filters_dirs` there to avoid repeating them on every invocation. CLI arguments extend config values rather than replacing them — both sources are active at once.