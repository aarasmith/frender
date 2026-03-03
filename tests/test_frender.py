"""
Unit tests for frender's core functions.

These tests exercise individual functions in isolation. They are fast, have no
CLI invocation overhead, and should be the first place to look when a function
behaves unexpectedly.

Coverage areas:
  - Context loaders (env, json, yaml, toml, ini)
  - Context merging and variable priority
  - File collection and input validation
  - Template rendering and output writing
  - Macro and filter registration
  - Config loading and initialisation
"""
import pytest
import json
import os
from pathlib import Path
import jinja2
from frender.main import (
    load_env_file, load_json_file, load_yaml_file, load_toml_file, load_ini_file,
    load_context, load_vars, load_file_vars, context_merger,
    render_file, write_rendered, collect_files, env_var,
    setup_environment, validate_input_sources, RenderError,
    register_filters, init_config, load_frender_config,
)


# ---------------------------
# Context Loaders
# ---------------------------

def test_load_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("FOO=bar\nBAR=baz")
    ctx = load_env_file(f)
    assert ctx["FOO"] == "bar"
    assert ctx["BAR"] == "baz"

def test_load_json_file(tmp_path):
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"key": "val"}))
    assert load_json_file(f) == {"key": "val"}

def test_load_yaml_file(tmp_path):
    f = tmp_path / "data.yaml"
    f.write_text("foo: bar")
    assert load_yaml_file(f) == {"foo": "bar"}

def test_load_toml_file(tmp_path):
    f = tmp_path / "data.toml"
    f.write_text("[section]\nkey = 'value'")
    assert load_toml_file(f) == {"section": {"key": "value"}}

def test_load_ini_file(tmp_path):
    f = tmp_path / "data.ini"
    f.write_text("[section]\nkey=value")
    assert load_ini_file(f) == {"section": {"key": "value"}}

def test_load_context_dispatch(tmp_path):
    """load_context must dispatch to the correct loader for every supported extension."""
    files = {
        ".env":  "FOO=bar",
        ".json": json.dumps({"key": "val"}),
        ".yaml": "foo: bar",
        ".toml": "[section]\nkey='value'",
        ".ini":  "[section]\nkey=value",
    }
    for ext, content in files.items():
        f = tmp_path / f"file{ext}"
        f.write_text(content)
        assert load_context([f]), f"Context for {ext} should not be empty"

def test_load_context_skips_missing_file(tmp_path):
    """
    A missing env file must be skipped rather than aborting the whole load.
    This is critical for config+CLI merging: the config layer may reference paths
    that don't exist yet, and the CLI layer should still load correctly.
    """
    missing = tmp_path / "nonexistent.yaml"
    present = tmp_path / "present.yaml"
    present.write_text("key: value")
    assert load_context([missing, present]) == [{"key": "value"}]

def test_load_context_empty_list():
    assert load_context([]) == []


# ---------------------------
# Context Merging
# ---------------------------

def test_context_merger_later_wins():
    """Later dicts must override earlier ones — this is the defined key priority order."""
    assert context_merger([{"a": 1, "b": 2}, {"b": 99, "c": 3}]) == {"a": 1, "b": 99, "c": 3}

def test_context_merger_empty():
    assert context_merger([]) == {}

def test_context_merger_warns_on_key_collision(caplog):
    """Key collisions across env files must emit a warning so users aren't silently surprised."""
    import logging
    with caplog.at_level(logging.WARNING, logger="frender"):
        context_merger([{"shared": "first", "a": 1}, {"shared": "second"}])
    assert any("shared" in msg for msg in caplog.messages)

def test_build_context_priority_order(tmp_path):
    """
    build_context must apply sources in order: env file < --file-var < --var.
    A key present in all three sources must resolve to the --var value.
    """
    from frender.main import build_context

    env_file = tmp_path / "env.yaml"
    env_file.write_text("key: from_env\nenv_only: present\n")

    file_var_file = tmp_path / "raw.txt"
    file_var_file.write_text("from_file_var")

    result = build_context(
        env_files=[str(env_file)],
        file_var_args=[f"key={file_var_file}"],
        var_args=["key=from_var"],
    )

    assert result["key"] == "from_var"       # --var wins
    assert result["env_only"] == "present"   # env-only key survives


def test_build_context_collision_warnings(tmp_path, caplog):
    """
    build_context must warn at each override boundary:
    once when --file-var shadows an env key, once when --var shadows a key.
    """
    import logging
    from frender.main import build_context

    env_file = tmp_path / "env.yaml"
    env_file.write_text("key: from_env\n")

    file_var_file = tmp_path / "raw.txt"
    file_var_file.write_text("from_file_var")

    with caplog.at_level(logging.WARNING, logger="frender"):
        build_context(
            env_files=[str(env_file)],
            file_var_args=[f"key={file_var_file}"],
            var_args=["key=from_var"],
        )

    warning_messages = [m for m in caplog.messages if "key" in m]
    assert len(warning_messages) == 2

# ---------------------------
# Variable Loaders
# ---------------------------

def test_load_vars_parses_correctly():
    assert load_vars(["title=Hello", "greeting=Hello world"]) == {
        "title": "Hello",
        "greeting": "Hello world",
    }

def test_load_vars_invalid_format():
    with pytest.raises(RenderError):
        load_vars(["badformat"])

def test_load_vars_invalid_identifier():
    with pytest.raises(RenderError):
        load_vars(["123bad=value"])

def test_load_file_vars_reads_utf8_text(tmp_path):
    f = tmp_path / "example.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    assert load_file_vars([f"content={f}"]) == {"content": "hello\nworld\n"}

def test_load_file_vars_missing_file(tmp_path):
    with pytest.raises(RenderError, match="does not exist"):
        load_file_vars([f"content={tmp_path / 'ghost.txt'}"])


# ---------------------------
# Rendering & Output
# ---------------------------

def test_env_var(monkeypatch):
    monkeypatch.setenv("TESTVAR", "123")
    assert env_var("TESTVAR") == "123"
    assert env_var("NOPE", "default") == "default"

def test_render_file(tmp_path):
    tpl = tmp_path / "tpl.j2"
    tpl.write_text("Hello {{ name }}!")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(tmp_path)]))
    assert render_file(tpl.name, env, {"name": "World"}) == "Hello World!"

def test_write_and_render(tmp_path):
    tpl = tmp_path / "tpl.j2"
    tpl.write_text("Name: {{ name }}")
    output = tmp_path / "out.txt"
    env = setup_environment(tpl)
    write_rendered(tpl, render_file(tpl.name, env, {"name": "Bob"}), output)
    assert output.read_text() == "Name: Bob"


# ---------------------------
# File Collection
# ---------------------------

def test_collect_files_list(tmp_path):
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("y")
    class Args:
        list = f"{f1},{f2}"; file_list = None; dir = None
        recursive = False; input_file = None; exclude = None
    assert set(collect_files(Args)) == {f1, f2}

def test_collect_files_dir_recursive(tmp_path):
    sub = tmp_path / "sub"; sub.mkdir()
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = sub / "b.txt"; f2.write_text("y")
    class Args:
        list = None; file_list = None; dir = str(tmp_path)
        recursive = True; input_file = None; exclude = None
    files = collect_files(Args)
    assert f1 in files and f2 in files

def test_collect_files_raises_with_no_source():
    class Args:
        list = None; file_list = None; dir = None
        recursive = False; input_file = None; exclude = None
    with pytest.raises(RenderError):
        collect_files(Args)


# ---------------------------
# Input Validation
# ---------------------------

def test_validate_input_sources_multiple_raises():
    """Providing more than one input mode (e.g. both a file and --list) must error."""
    class Args:
        input_file = "foo.j2"; list = "bar.j2"; file_list = None; dir = None
    class FakeParser:
        def error(self, msg): raise SystemExit(msg)
    with pytest.raises(SystemExit):
        validate_input_sources(Args, FakeParser())

def test_validate_input_sources_none_raises():
    class Args:
        input_file = None; list = None; file_list = None; dir = None
    class FakeParser:
        def error(self, msg): raise SystemExit(msg)
    with pytest.raises(SystemExit):
        validate_input_sources(Args, FakeParser())


# ---------------------------
# Config
# ---------------------------

def test_init_config_creates_template(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    init_config()
    content = (tmp_path / ".frender" / "config.yaml").read_text()
    assert "env_files" in content and "macros_dirs" in content

def test_init_config_does_not_overwrite(tmp_path, monkeypatch):
    """--init must never silently destroy an existing config."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    config_path = tmp_path / ".frender" / "config.yaml"
    config_path.parent.mkdir()
    config_path.write_text("existing: content")
    init_config()
    assert config_path.read_text() == "existing: content"

def test_load_frender_config_expands_paths(tmp_path, monkeypatch):
    """Paths in config.yaml must be expanded and resolved to absolute strings."""
    import yaml
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    config_dir = tmp_path / ".frender"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(yaml.dump({
        "env_files":   [str(tmp_path / "defaults.env")],
        "macros_dirs": [str(tmp_path / "macros")],
        "filters_dirs": [],
    }))
    result = load_frender_config()
    assert result["env_files"]   == [str(tmp_path / "defaults.env")]
    assert result["macros_dirs"] == [str(tmp_path / "macros")]
    assert result["filters_dirs"] == []

def test_load_frender_config_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert load_frender_config() == {}


# ---------------------------
# Macros & Filters
# ---------------------------

def test_setup_environment_macros(tmp_path):
    macros_dir = tmp_path / "macros"; macros_dir.mkdir()
    (macros_dir / "macro.j2").write_text(
        "{% macro greet(name) %}Hello {{ name }}{% endmacro %}"
    )
    env = setup_environment(tmp_path / "dummy.j2", macro_dirs=[macros_dir])
    assert "greet" in env.globals
    assert env.globals["greet"]("World") == "Hello World"

def test_setup_environment_macros_recursive(tmp_path):
    """Macros in subdirectories must also be discovered and registered."""
    subdir = tmp_path / "macros" / "sub"; subdir.mkdir(parents=True)
    (subdir / "submacro.j2").write_text(
        "{% macro bye(name) %}Bye {{ name }}{% endmacro %}"
    )
    env = setup_environment(tmp_path / "dummy.j2", macro_dirs=[tmp_path / "macros"])
    assert env.globals["bye"]("Alice") == "Bye Alice"

def test_setup_environment_filters(tmp_path):
    filters_dir = tmp_path / "filters"; filters_dir.mkdir()
    (filters_dir / "custom_filter.py").write_text(
        "def shout(text):\n    return text.upper()\n"
    )
    tpl = tmp_path / "template.j2"
    tpl.write_text("{{ 'hello' | shout }}")
    assert setup_environment(tpl, filter_dirs=[filters_dir]).get_template("template.j2").render() == "HELLO"

def test_setup_environment_filters_recursive(tmp_path):
    """Filters in subdirectories must also be discovered and registered."""
    subdir = tmp_path / "filters" / "sub"; subdir.mkdir(parents=True)
    (subdir / "excite.py").write_text(
        "def excite(text):\n    return text + '!!!'\n"
    )
    tpl = tmp_path / "template.j2"
    tpl.write_text("{{ 'wow' | excite }}")
    assert setup_environment(tpl, filter_dirs=[tmp_path / "filters"]).get_template("template.j2").render() == "wow!!!"

def test_register_filters_later_dir_wins(tmp_path):
    """A filter in a later --filters-dir must replace one with the same name from an earlier dir."""
    f1 = tmp_path / "f1"; f1.mkdir()
    (f1 / "myfilter.py").write_text("def shout(text): return 'FIRST'")
    f2 = tmp_path / "f2"; f2.mkdir()
    (f2 / "myfilter.py").write_text("def shout(text): return 'SECOND'")
    tpl = tmp_path / "tpl.j2"
    tpl.write_text("{{ 'x' | shout }}")
    assert setup_environment(tpl, filter_dirs=[f1, f2]).get_template("tpl.j2").render() == "SECOND"

def test_macro_name_collision_later_wins(tmp_path):
    """When two macro dirs export the same name, the later dir's definition must win."""
    m1 = tmp_path / "m1"; m1.mkdir()
    (m1 / "a.j2").write_text("{% macro hello(x) %}FIRST {{ x }}{% endmacro %}")
    m2 = tmp_path / "m2"; m2.mkdir()
    (m2 / "b.j2").write_text("{% macro hello(x) %}SECOND {{ x }}{% endmacro %}")
    env = setup_environment(tmp_path / "dummy.j2", macro_dirs=[m1, m2])
    assert env.globals["hello"]("x") == "SECOND x"