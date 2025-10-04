import pytest
from pathlib import Path
import json
import yaml
import jinja2
from frender import (
    load_env_file, load_json_file, load_yaml_file, load_toml_file, load_ini_file,
    load_context, render_file, write_rendered, collect_files, env_var, setup_environment, RenderError
)

# ---------------------------
# Loader Unit Tests
# ---------------------------

def test_load_env_file(tmp_path):
    """Test dotenv-style key=value parsing."""
    f = tmp_path / ".env"
    f.write_text("FOO=bar\nBAR=baz")
    ctx = load_env_file(f)
    assert ctx["FOO"] == "bar"
    assert ctx["BAR"] == "baz"

def test_load_json_file(tmp_path):
    """Test JSON file parsing."""
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"key": "val"}))
    ctx = load_json_file(f)
    assert ctx["key"] == "val"

def test_load_yaml_file(tmp_path):
    """Test YAML file parsing."""
    f = tmp_path / "data.yaml"
    f.write_text("foo: bar")
    ctx = load_yaml_file(f)
    assert ctx["foo"] == "bar"

def test_load_toml_file(tmp_path):
    """Test TOML file parsing."""
    f = tmp_path / "data.toml"
    f.write_text("[section]\nkey = 'value'")
    ctx = load_toml_file(f)
    assert ctx["section"]["key"] == "value"

def test_load_ini_file(tmp_path):
    """Test INI file parsing."""
    f = tmp_path / "data.ini"
    f.write_text("[section]\nkey=value")
    ctx = load_ini_file(f)
    assert ctx["section"]["key"] == "value"

def test_load_context_dispatch(tmp_path):
    """Ensure load_context dispatches correctly based on file extension."""
    files = {
        ".env": "FOO=bar",
        ".json": json.dumps({"key": "val"}),
        ".yaml": "foo: bar",
        ".toml": "[section]\nkey='value'",
        ".ini": "[section]\nkey=value"
    }
    for ext, content in files.items():
        f = tmp_path / f"file{ext}"
        f.write_text(content)
        ctx = load_context(f)
        assert ctx, f"Context for {ext} should not be empty"

# ---------------------------
# Rendering & Write Tests
# ---------------------------

def test_env_var(monkeypatch):
    """Test env_var filter returns system env values or default."""
    monkeypatch.setenv("TESTVAR", "123")
    assert env_var("TESTVAR") == "123"
    assert env_var("NOPE", "default") == "default"

def test_render_file(tmp_path):
    """Ensure Jinja template renders correctly."""
    tpl = tmp_path / "tpl.j2"
    tpl.write_text("Hello {{ name }}!")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(tmp_path)]))
    out = render_file(tpl.name, env, {"name": "World"})
    assert out == "Hello World!"

def test_write_rendered(tmp_path):
    """Ensure rendered content is written to file."""
    dest = tmp_path / "out.txt"
    write_rendered(dest, "test content", dest)
    assert dest.read_text() == "test content"

# ---------------------------
# File Collection Tests
# ---------------------------

def test_collect_files_list(tmp_path):
    """Verify files collected from a comma-separated list."""
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("y")
    class Args:
        list=f"{f1},{f2}"
        file_list=None
        dir=None
        recursive=False
        input_file=None
    files = collect_files(Args)
    assert set(files) == {f1, f2}

def test_collect_files_dir_recursive(tmp_path):
    """Verify files collected recursively from a directory."""
    sub = tmp_path / "sub"; sub.mkdir()
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = sub / "b.txt"; f2.write_text("y")
    class Args:
        list=None
        file_list=None
        dir=str(tmp_path)
        recursive=True
        input_file=None
    files = collect_files(Args)
    assert f1 in files and f2 in files

# ---------------------------
# Macros & Environment Tests
# ---------------------------

def test_setup_environment_macros(tmp_path):
    """Test that macros from a macros dir are loaded recursively into Jinja globals."""
    macros_dir = tmp_path / "macros"
    macros_dir.mkdir()
    
    # create a macro file
    macro_file = macros_dir / "macro.j2"
    macro_file.write_text("{% macro greet(name) %}Hello {{ name }}{% endmacro %}")
    
    # setup environment with macros explicitly passed
    env = setup_environment(template_file=tmp_path / "dummy.j2", macros_dir=macros_dir)
    
    # check macro is available in globals
    assert "greet" in env.globals
    assert env.globals["greet"]("World") == "Hello World"

def test_setup_environment_macros_recursive(tmp_path):
    """Test that macros in subdirectories are also loaded into globals."""
    macros_dir = tmp_path / "macros"
    subdir = macros_dir / "sub"
    subdir.mkdir(parents=True)
    
    macro_file = subdir / "submacro.j2"
    macro_file.write_text("{% macro bye(name) %}Bye {{ name }}{% endmacro %}")
    
    env = setup_environment(template_file=tmp_path / "dummy.j2", macros_dir=macros_dir)
    
    assert "bye" in env.globals
    assert env.globals["bye"]("Alice") == "Bye Alice"

def test_setup_environment_filters(tmp_path):
    """Test that Python filters in filters-dir are loaded into Jinja environment."""
    filters_dir = tmp_path / "filters"
    filters_dir.mkdir()

    # Create a Python filter
    filter_file = filters_dir / "custom_filter.py"
    filter_file.write_text(
        "def shout(text):\n"
        "    return text.upper()\n"
    )

    # Dummy template
    template_file = tmp_path / "template.j2"
    template_file.write_text("{{ 'hello' | shout }}")

    env = setup_environment(template_file, filters_dir=filters_dir)
    tpl = env.get_template("template.j2")
    rendered = tpl.render()
    assert rendered == "HELLO"
    assert "shout" in env.filters
    assert callable(env.filters["shout"])

def test_setup_environment_filters_recursive(tmp_path):
    """Test that Python filters in subdirectories of filters-dir are also loaded."""
    filters_dir = tmp_path / "filters"
    subdir = filters_dir / "sub"
    subdir.mkdir(parents=True)

    # Create a Python filter in subdir
    filter_file = subdir / "excite.py"
    filter_file.write_text(
        "def excite(text):\n"
        "    return text + '!!!'\n"
    )

    # Dummy template
    template_file = tmp_path / "template.j2"
    template_file.write_text("{{ 'wow' | excite }}")

    env = setup_environment(template_file, filters_dir=filters_dir)
    tpl = env.get_template("template.j2")
    rendered = tpl.render()
    assert rendered == "wow!!!"
    assert "excite" in env.filters
    assert callable(env.filters["excite"])


# ---------------------------
# Integration Rendering Tests
# ---------------------------

def test_render_integration(tmp_path):
    """Integration test: render multiple templates from a list using context."""
    tpl1 = tmp_path / "tpl1.j2"; tpl1.write_text("Hello {{ foo }}!")
    tpl2 = tmp_path / "tpl2.j2"; tpl2.write_text("Value is {{ bar }}.")
    context = {"foo": "Alice", "bar": 42}

    env1 = setup_environment(tpl1)
    env2 = setup_environment(tpl2)

    out1 = render_file(tpl1.name, env1, context)
    out2 = render_file(tpl2.name, env2, context)
    assert out1 == "Hello Alice!"
    assert out2 == "Value is 42."

def test_write_and_render(tmp_path):
    """Integration test: render template and write output to file."""
    tpl = tmp_path / "tpl.j2"; tpl.write_text("Name: {{ name }}")
    output = tmp_path / "out.txt"
    context = {"name": "Bob"}

    env = setup_environment(tpl)
    rendered = render_file(tpl.name, env, context)
    write_rendered(tpl, rendered, output)
    assert output.read_text() == "Name: Bob"
