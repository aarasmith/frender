import pytest
from pathlib import Path
import json
import yaml
import jinja2
from frender import load_context, render_file, write_rendered, collect_files, denv

# ---------------------------
# Unit Tests
# ---------------------------

def test_load_context_env(tmp_path):
    """Ensure .env-style key=value pairs are correctly parsed into context."""
    f = tmp_path / ".env"
    f.write_text("FOO=bar\nBAR=baz")
    ctx = load_context(f)
    assert ctx["FOO"] == "bar"
    assert ctx["BAR"] == "baz"

def test_load_context_json(tmp_path):
    """Ensure JSON files are correctly parsed into context."""
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"key": "val"}))
    ctx = load_context(f)
    assert ctx["key"] == "val"

def test_load_context_yaml(tmp_path):
    """Ensure YAML files are correctly parsed into context."""
    f = tmp_path / "data.yaml"
    f.write_text("foo: bar")
    ctx = load_context(f)
    assert ctx["foo"] == "bar"

def test_load_context_toml(tmp_path):
    """Ensure TOML files are correctly parsed into context."""
    f = tmp_path / "data.toml"
    f.write_text("[section]\nkey = \"value\"")
    ctx = load_context(f)
    assert ctx["section"]["key"] == "value"

def test_denv(monkeypatch):
    """Test the denv filter returns environment variables or default values."""
    monkeypatch.setenv("TESTVAR", "123")
    assert denv("TESTVAR") == "123"
    assert denv("NOPE", "default") == "default"

def test_render_file(tmp_path):
    """Test that Jinja2 templates render correctly given a context."""
    tpl = tmp_path / "tpl.j2"
    tpl.write_text("Hello {{ name }}!")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(tmp_path)]))
    out = render_file(tpl.name, env, {"name": "World"})
    assert out == "Hello World!"

def test_write_rendered(tmp_path):
    """Ensure that rendered content is correctly written to a file."""
    dest = tmp_path / "out.txt"
    write_rendered(dest, "test content", dest)
    assert dest.read_text() == "test content"

# ---------------------------
# Integration Tests
# ---------------------------

def test_collect_files_list(tmp_path):
    """Verify that comma-separated file lists are collected correctly."""
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

def test_collect_files_file_list(tmp_path):
    """Verify that files listed in a text file are collected correctly."""
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = tmp_path / "b.txt"; f2.write_text("y")
    list_file = tmp_path / "files.txt"
    list_file.write_text(f"{f1}\n{f2}\n")
    class Args:
        list=None
        file_list=str(list_file)
        dir=None
        recursive=False
        input_file=None
    files = collect_files(Args)
    assert set(files) == {f1, f2}

def test_collect_files_dir_non_recursive(tmp_path):
    """Verify that files in a directory are collected (non-recursively)."""
    sub = tmp_path / "sub"; sub.mkdir()
    f1 = tmp_path / "a.txt"; f1.write_text("x")
    f2 = sub / "b.txt"; f2.write_text("y")
    class Args:
        list=None
        file_list=None
        dir=str(tmp_path)
        recursive=False
        input_file=None
    files = collect_files(Args)
    assert f1 in files
    assert f2 not in files

def test_collect_files_dir_recursive(tmp_path):
    """Verify that files in a directory and subdirectories are collected recursively."""
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
    assert f1 in files
    assert f2 in files

def test_render_integration(tmp_path):
    """Full integration test: render template files from a list using context."""
    # Setup template
    tpl1 = tmp_path / "tpl1.j2"; tpl1.write_text("Hello {{ foo }}!")
    tpl2 = tmp_path / "tpl2.j2"; tpl2.write_text("Value is {{ bar }}.")
    env_context = {"foo": "Alice", "bar": 42}

    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(tmp_path)]))
    out1 = render_file(tpl1.name, env, env_context)
    out2 = render_file(tpl2.name, env, env_context)
    assert out1 == "Hello Alice!"
    assert out2 == "Value is 42."

def test_write_and_render(tmp_path):
    """Integration test: write rendered template to output file and verify content."""
    tpl = tmp_path / "tpl.j2"; tpl.write_text("Name: {{ name }}")
    output = tmp_path / "out.txt"
    env_context = {"name": "Bob"}
    env = jinja2.Environment(loader=jinja2.FileSystemLoader([str(tmp_path)]))
    rendered = render_file(tpl.name, env, env_context)
    write_rendered(tpl, rendered, output)
    assert output.read_text() == "Name: Bob"
