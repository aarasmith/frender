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

### Render a single template to stdout
This renders `example.j2` using variables in `.env` (if exists) by default:
```
frender templates/example.j2
```
Any other options require either a specified ouput or the --overwrite (-ow) flag

### Render a single template in place:
This overwrites the input file with the rendered result:
```
frender templates/example.j2 -ow
```

### Render multiple templates from a list (flattened) to an output directory
Use `-l` / `--list` to specify multiple templates. Output files are written directly to the target directory (e.g. `templates/subdir/a.j2` -> `output/a.j2`):
```
frender -l templates/a.j2,templates/b.j2 -o output
```

### Render templates listed in a file
Each line of `filelist.txt` should contain a path to a template. File paths/hierarchy will be respected (e.g. `templates/subdir/template.yml` -> `output/subdir/template.yml`):
```
frender -f filelist.txt -o output
```

### Flattening output when using -f or -d
When rendering multiple files from a file list (-f) or directory (-d), you can control whether subdirectories are preserved:
```
frender -f filelist.txt -o output/ --single-dir
```

### Render all files in a directory
Render templates in a directory:
```
frender -d templates/ -o output/
```
Recursively render templates in a directory and all subdirectories in place using the --recursive (-r) flag:
```
frender -d templates/ -r -ow
```

### Exclude specific files when rendering a directory
Use wildcards to exclude files from rendering:
```
frender -d templates/ -o output/ -x "*.bak,*.tmp,temp_*"
```

### Use a custom environment/config file
Load variables from JSON, TOML, YAML, or dotenv-style files:
```
frender templates/config.j2 --env-file config.toml
frender templates/config.j2 --env-file config.yaml (or .yml)
frender templates/config.j2 --env-file .env
frender templates/config.j2 --env-file config.json
frender templates/config.j2 --env-file config.json --env-file .env --env-file config.toml
```

### Use macros or custom Jinja filters
Macros and filters can be registered globally from directories:
```
# Use macros
frender templates/macro_example.j2 -o output/ --macros-dir macros/

# Use custom filters
frender templates/filter_example.j2 -o output/ --filters-dir filters/
```

### Configure default env-file, macros-dir, and filters-dir
You can configure default settings by running:
```
frender config
```
This will create `~/.frender/config` and be used for subsequent runs

### Combine overrides with a config file
CLI arguments always take precedence over the configuration file:
```
frender templates/example.j2 -o output/ --env-file custom.env
```