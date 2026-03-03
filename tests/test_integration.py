"""
Integration tests for frender's CLI.

These tests invoke frender.main() end-to-end via run_cli() and assert on rendered
output files or stdout. They cover behaviour that only emerges from the full pipeline:
CLI argument parsing, config loading, context merging, macro/filter registration,
and template rendering working together.

Test organisation:
  - Basic CLI modes         — input/output flags, stdout, overwrite
  - Context & variables     — env files, --var, --file-var, merge priority
  - Config integration      — ~/.frender/config.yaml loading and merging with CLI
  - Filters                 — registration, override precedence
  - Macros                  — registration, cross-directory calls, override precedence

The macro registry tests at the bottom are the most critical in this file.
MacroCallable's call-time context injection is subtle and must remain order-independent.
"""
import sys
import textwrap
import os
import logging
from pathlib import Path
import pytest
import frender


# ---------------------------
# Helpers & Fixtures
# ---------------------------

def make_env_files(base: Path):
    (base / "env.yaml").write_text(textwrap.dedent("""\
        key1: foo
        key2: bar
        key3:
          test: baz
    """))
    (base / "env.json").write_text('{"key1": "foo", "key2": "bar", "key3": {"test": "baz"}}')
    (base / "env.toml").write_text(textwrap.dedent("""\
        key1 = "foo"
        key2 = "bar"

        [key3]
        test = "baz"
    """))
    (base / ".env").write_text("key1=foo\nkey2=bar\n")


def make_sources(base: Path):
    src1 = base / "source1"
    src1.mkdir()
    (src1 / "test.yml").write_text("{{ key1 }}\n{{ key2 }}\n")
    (src1 / "test2.yaml").write_text("{{ key1 }}\n{{ key2 }}\n")

    src2 = base / "source2"
    src2.mkdir()
    (src2 / "env.yaml").write_text("{{ key1 }}\n{{ key2 }}\n{{ key3.test }}\n")
    (src2 / "macro.yaml").write_text("{{ test_macro('foo') }}\n")
    (src2 / "filter.yaml").write_text("{{ ref('foo') }}\n")


def make_macros_and_filters(base: Path):
    macros = base / "macros"; macros.mkdir()
    (macros / "test_macro.j2").write_text(
        "{% macro test_macro(x) %}I am a macro {{ x }}{% endmacro %}"
    )
    filters = base / "filters"; filters.mkdir()
    (filters / "ref.py").write_text(textwrap.dedent("""\
        from markupsafe import Markup
        def ref(value):
            return Markup(f"{{{{ ref({value}) }}}}")
    """))
    return macros, filters


def make_config(base_path: Path, env_files=None, macros_dirs=None, filters_dirs=None) -> Path:
    """Write a .frender/config.yaml inside base_path (used as the mock home dir in tests)."""
    import yaml
    config_dir = base_path / ".frender"; config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.yaml"
    config = {}
    if env_files:    config["env_files"]    = [str(p) for p in env_files]
    if macros_dirs:  config["macros_dirs"]  = [str(p) for p in macros_dirs]
    if filters_dirs: config["filters_dirs"] = [str(p) for p in filters_dirs]
    config_file.write_text(yaml.dump(config) if config else "")
    return config_file


def run_cli(monkeypatch, argv, capsys, home=None):
    monkeypatch.setattr(sys, "argv", ["frender.py", *argv])
    if home:
        monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    try:
        frender.main()
    except SystemExit:
        pass
    return capsys.readouterr()


@pytest.fixture
def setup_project(tmp_path, monkeypatch):
    """
    Standard project layout used by most integration tests:
      - env files: .env, env.yaml, env.json, env.toml
      - templates: source1/{test.yml,test2.yaml}, source2/{env.yaml,macro.yaml,filter.yaml}
      - macros:    macros/test_macro.j2
      - filters:   filters/ref.py
    Home is monkeypatched to tmp_path so no real ~/.frender/config.yaml is ever read.
    """
    make_env_files(tmp_path)
    make_sources(tmp_path)
    macros, filters = make_macros_and_filters(tmp_path)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path, macros, filters
    os.chdir(cwd)


# ---------------------------
# Basic CLI Modes
# ---------------------------

def test_stdout_render(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    out = run_cli(monkeypatch, ["source1/test.yml", "--env-file", ".env"], capsys)
    assert out.out.strip() == "foo\nbar"

def test_overwrite_in_place(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["source1/test.yml", "-ow", "--env-file", ".env"], capsys)
    assert Path("source1/test.yml").read_text().strip() == "foo\nbar"

def test_list_mode_flatten(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["-l", "source1/test.yml,source1/test2.yaml", "-o", "target", "--env-file", ".env"], capsys)
    assert Path("target/test.yml").read_text().strip() == "foo\nbar"
    assert Path("target/test2.yaml").read_text().strip() == "foo\nbar"

def test_file_list_single_dir(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    Path("file_list.txt").write_text("source1/test.yml\nsource1/test2.yaml\n")
    run_cli(monkeypatch, ["-f", "file_list.txt", "-o", "target2", "--single-dir"], capsys)
    assert Path("target2/test.yml").exists()
    assert Path("target2/test2.yaml").exists()

def test_dir_mode_recursive_off(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["-d", "source1", "-o", "target3"], capsys)
    assert Path("target3/test.yml").exists()
    assert Path("target3/test2.yaml").exists()

def test_dir_mode_with_exclude(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["-d", "source1", "-o", "target4", "-x", "*.yml"], capsys)
    assert not Path("target4/test.yml").exists()
    assert Path("target4/test2.yaml").exists()


# ---------------------------
# Context & Variables
# ---------------------------

def test_custom_env_file_json(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["source2/env.yaml", "-o", "target5", "--env-file", "env.json"], capsys)
    assert Path("target5/env.yaml").read_text().strip() == "foo\nbar\nbaz"

def test_multiple_env_files_merged(setup_project, monkeypatch, capsys):
    """
    Multiple --env-file args must be merged in order: later files override earlier ones.
    Keys unique to each file must both be present in the final context.
    """
    tmp_path, _, _ = setup_project
    (tmp_path / "env1.yaml").write_text("key1: foo\nkey2: bar\nunique1: only_in_env1\n")
    (tmp_path / "env2.yaml").write_text("key2: baz\nkey3: qux\nunique2: only_in_env2\n")
    (tmp_path / "source_merge.yaml").write_text(
        "{{ key1 }}\n{{ key2 }}\n{{ key3 }}\n{{ unique1 }}\n{{ unique2 }}\n"
    )
    run_cli(monkeypatch, [
        "source_merge.yaml", "-o", "target_multi",
        "--env-file", "env1.yaml", "--env-file", "env2.yaml",
    ], capsys)
    assert (tmp_path / "target_multi" / "source_merge.yaml").read_text().strip() == \
        "foo\nbaz\nqux\nonly_in_env1\nonly_in_env2"

def test_var_overrides_env_file(setup_project, monkeypatch, capsys):
    """--var must take final precedence over the same key from --env-file."""
    tmp_path, _, _ = setup_project
    (tmp_path / "source_var.yaml").write_text("{{ key1 }}\n")
    run_cli(monkeypatch, [
        "source_var.yaml", "-o", "target_var",
        "--env-file", "env.yaml", "--var", "key1=OVERRIDDEN",
    ], capsys)
    assert (tmp_path / "target_var" / "source_var.yaml").read_text().strip() == "OVERRIDDEN"

def test_var_override_warns(setup_project, monkeypatch, caplog, capsys):
    """--var overriding a key already set by --env-file must emit a warning."""
    tmp_path, _, _ = setup_project
    (tmp_path / "source_var.yaml").write_text("{{ key1 }}\n")
    with caplog.at_level(logging.WARNING, logger="frender"):
        run_cli(monkeypatch, [
            "source_var.yaml", "-o", "target_warn",
            "--env-file", "env.yaml", "--var", "key1=OVERRIDDEN",
        ], capsys)
    assert any("key1" in msg for msg in caplog.messages)

def test_env_file_key_collision_warns(setup_project, monkeypatch, caplog, capsys):
    """Overlapping keys across multiple --env-files must emit a warning."""
    tmp_path, _, _ = setup_project
    (tmp_path / "env2.yaml").write_text("key1: override\n")
    (tmp_path / "source_var.yaml").write_text("{{ key1 }}\n")
    with caplog.at_level(logging.WARNING, logger="frender"):
        run_cli(monkeypatch, [
            "source_var.yaml", "-o", "target_warn2",
            "--env-file", "env.yaml", "--env-file", "env2.yaml",
        ], capsys)
    assert any("key1" in msg for msg in caplog.messages)

def test_file_var_injected_into_context(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    raw_file = tmp_path / "raw.txt"
    raw_file.write_text("hello from file-var")
    (tmp_path / "source_file_var.yaml").write_text("{{ key1 }}\n{{ file_contents }}\n")
    run_cli(monkeypatch, [
        "source_file_var.yaml", "-o", "target_file_var",
        "--env-file", "env.yaml", "--file-var", f"file_contents={raw_file}",
    ], capsys)
    assert (tmp_path / "target_file_var" / "source_file_var.yaml").read_text().strip() == \
        "foo\nhello from file-var"


# ---------------------------
# Config Integration
# ---------------------------

def test_config_paths_contribute_to_rendering(setup_project, monkeypatch, capsys):
    """
    Macros and filters in config.yaml must be active without any CLI flags.
    This confirms the config is actually loaded and applied, not just parsed.
    """
    tmp_path, macros, filters = setup_project
    make_config(tmp_path, macros_dirs=[macros], filters_dirs=[filters])
    run_cli(monkeypatch, ["source2/macro.yaml", "-o", "target_cfg", "--env-file", str(tmp_path / "env.yaml")], capsys, home=tmp_path)
    run_cli(monkeypatch, ["source2/filter.yaml", "-o", "target_cfg", "--env-file", str(tmp_path / "env.yaml")], capsys, home=tmp_path)
    assert (tmp_path / "target_cfg" / "macro.yaml").read_text().strip() == "I am a macro foo"
    assert (tmp_path / "target_cfg" / "filter.yaml").read_text().strip() == "{{ ref(foo) }}"

def test_config_and_cli_macro_dirs_both_active(setup_project, monkeypatch, capsys):
    """
    Macro dirs from config and CLI must both be active — config is the base layer,
    CLI extends it. A template requiring macros from both sources must render correctly.
    If either layer were dropped, rendering would fail with an undefined macro error.
    """
    tmp_path, _, _ = setup_project
    macros_inner = tmp_path / "macros_inner"; macros_inner.mkdir()
    (macros_inner / "inner.j2").write_text(
        "{% macro inner(x) %}INNER {{ x }}{% endmacro %}"
    )
    macros_outer = tmp_path / "macros_outer"; macros_outer.mkdir()
    (macros_outer / "outer.j2").write_text(
        "{% macro outer(x) %}OUTER + {{ inner(x) }}{% endmacro %}"
    )
    (tmp_path / "source_combined.yaml").write_text("{{ outer('foo') }}\n")
    make_config(tmp_path, macros_dirs=[macros_inner])
    run_cli(monkeypatch, [
        "source_combined.yaml", "-o", "target_combined",
        "--macros-dir", str(macros_outer), "--env-file", "env.yaml",
    ], capsys, home=tmp_path)
    assert (tmp_path / "target_combined" / "source_combined.yaml").read_text().strip() == \
        "OUTER + INNER foo"


# ---------------------------
# Filters
# ---------------------------

def test_filters_dir(setup_project, monkeypatch, capsys):
    tmp_path, _, filters = setup_project
    run_cli(monkeypatch, ["source2/filter.yaml", "-o", "target7", "--filters-dir", str(filters)], capsys)
    assert Path("target7/filter.yaml").read_text().strip() == "{{ ref(foo) }}"

def test_filter_override_later_dir_wins(tmp_path, monkeypatch, capsys):
    """A filter in a later --filters-dir must supersede one with the same name from an earlier dir."""
    f1 = tmp_path / "filters1"; f1.mkdir()
    (f1 / "ref.py").write_text(
        "from markupsafe import Markup\n"
        "def ref(value): return Markup(f'FIRST({value})')\n"
    )
    f2 = tmp_path / "filters2"; f2.mkdir()
    (f2 / "ref.py").write_text(
        "from markupsafe import Markup\n"
        "def ref(value): return Markup(f'SECOND({value})')\n"
    )
    tpl = tmp_path / "tpl.j2"; tpl.write_text("{{ 'bar' | ref }}")
    run_cli(monkeypatch, [str(tpl), "-o", str(tmp_path / "out"),
                          "--filters-dir", str(f1), "--filters-dir", str(f2)], capsys)
    assert (tmp_path / "out" / tpl.name).read_text().strip() == "SECOND(bar)"


# ---------------------------
# Macros
# ---------------------------

def test_macros_dir(setup_project, monkeypatch, capsys):
    tmp_path, macros, _ = setup_project
    run_cli(monkeypatch, ["source2/macro.yaml", "-o", "target6", "--macros-dir", str(macros)], capsys)
    assert Path("target6/macro.yaml").read_text().strip() == "I am a macro foo"

def test_macro_override_later_dir_wins(tmp_path, monkeypatch, capsys):
    """A macro in a later --macros-dir must supersede one with the same name from an earlier dir."""
    m1 = tmp_path / "macros1"; m1.mkdir()
    (m1 / "base.j2").write_text("{% macro test_macro(x) %}BASE {{ x }}{% endmacro %}")
    m2 = tmp_path / "macros2"; m2.mkdir()
    (m2 / "override.j2").write_text("{% macro test_macro(x) %}OVERRIDE {{ x }}{% endmacro %}")
    tpl = tmp_path / "tpl.j2"; tpl.write_text("{{ test_macro('foo') }}")
    out_dir = tmp_path / "out"
    run_cli(monkeypatch, [str(tpl), "-o", str(out_dir),
                          "--macros-dir", str(m1), "--macros-dir", str(m2)], capsys)
    assert (out_dir / tpl.name).read_text().strip() == "OVERRIDE foo"

def test_macro_override_same_filename(tmp_path, monkeypatch, capsys):
    """
    When two macro dirs contain files with identical filenames, the later dir must win.
    This is the harder case: Jinja's FileSystemLoader resolves by filename, so searchpath
    ordering and cache-busting must be handled correctly to avoid the first file winning.
    """
    m1 = tmp_path / "macros1"; m1.mkdir()
    (m1 / "test.j2").write_text("{% macro test_macro(x) %}FIRST {{ x }}{% endmacro %}")
    m2 = tmp_path / "macros2"; m2.mkdir()
    (m2 / "test.j2").write_text("{% macro test_macro(x) %}SECOND {{ x }}{% endmacro %}")
    tpl = tmp_path / "tpl.j2"; tpl.write_text("{{ test_macro('foo') }}")
    out_dir = tmp_path / "out"
    run_cli(monkeypatch, [str(tpl), "-o", str(out_dir),
                          "--macros-dir", str(m1), "--macros-dir", str(m2)], capsys)
    assert (out_dir / tpl.name).read_text().strip() == "SECOND foo"

def test_deeply_nested_macros_across_directories_order_independent(setup_project, monkeypatch, capsys):
    """
    Macros must be able to call other macros at any nesting depth across different
    --macros-dir folders, without explicit {% import %} statements, and the result
    must be identical regardless of directory registration order.

    This guards the core MacroCallable guarantee: call-time context injection must
    supply the full registry to every macro body at every depth, not just the top level.

    Call graph:
        outer(x)  -->  mid(x)  -->  inner(x)
                  -->  inner(x)

    Expected: "OUTER -> MID [INNER foo] & INNER foo"
    """
    tmp_path, _, _ = setup_project

    macros_a = tmp_path / "macros_a"; macros_a.mkdir()
    (macros_a / "inner.j2").write_text("{% macro inner(x) %}INNER {{ x }}{% endmacro %}")

    macros_b = tmp_path / "macros_b"; macros_b.mkdir()
    (macros_b / "mid.sql").write_text(
        "{% macro mid(x) %}{% set v = inner(x) %}MID [{{ v }}]{% endmacro %}"
    )

    macros_c = tmp_path / "macros_c"; macros_c.mkdir()
    (macros_c / "outer.sql").write_text(
        "{% macro outer(x) %}OUTER -> {{ mid(x) }} & {{ inner(x) }}{% endmacro %}"
    )

    (tmp_path / "source_nesting.yaml").write_text("{{ outer('foo') }}\n")

    # Order 1: worst-case (outer registered before its dependencies)
    run_cli(monkeypatch, [
        "source_nesting.yaml", "-o", "target_nesting_o1",
        "--macros-dir", str(macros_c),
        "--macros-dir", str(macros_b),
        "--macros-dir", str(macros_a),
        "--env-file", "env.yaml",
    ], capsys)
    assert (tmp_path / "target_nesting_o1" / "source_nesting.yaml").read_text().strip() == \
        "OUTER -> MID [INNER foo] & INNER foo"

    # Order 2: reverse (inner registered first)
    run_cli(monkeypatch, [
        "source_nesting.yaml", "-o", "target_nesting_o2",
        "--macros-dir", str(macros_a),
        "--macros-dir", str(macros_b),
        "--macros-dir", str(macros_c),
        "--env-file", "env.yaml",
    ], capsys)
    assert (tmp_path / "target_nesting_o2" / "source_nesting.yaml").read_text().strip() == \
        "OUTER -> MID [INNER foo] & INNER foo"

def test_macro_diamond_dependency_across_directories(setup_project, monkeypatch, capsys):
    """
    Macros with a shared transitive dependency (diamond pattern) must resolve correctly
    when all four macros live in separate --macros-dir directories.

    This is the strongest stress-test for MacroCallable's registry injection. A shallow
    implementation would fail because mid_a and mid_b each need 'inner' independently —
    it must be present in the call-time context of both, not just the outermost macro.

    Call graph:
             outer(x)
            /         \\
      mid_a(x)       mid_b(x)
            \\         /
             inner(x)

    Expected: "DIAMOND: [A: INNER foo] + [B: INNER foo]"
    """
    tmp_path, _, _ = setup_project

    macros_inner = tmp_path / "macros_inner"; macros_inner.mkdir()
    (macros_inner / "inner.j2").write_text("{% macro inner(x) %}INNER {{ x }}{% endmacro %}")

    macros_mid_a = tmp_path / "macros_mid_a"; macros_mid_a.mkdir()
    (macros_mid_a / "mid_a.j2").write_text("{% macro mid_a(x) %}A: {{ inner(x) }}{% endmacro %}")

    macros_mid_b = tmp_path / "macros_mid_b"; macros_mid_b.mkdir()
    (macros_mid_b / "mid_b.j2").write_text("{% macro mid_b(x) %}B: {{ inner(x) }}{% endmacro %}")

    macros_outer = tmp_path / "macros_outer"; macros_outer.mkdir()
    (macros_outer / "outer.j2").write_text(
        "{% macro outer(x) %}DIAMOND: [{{ mid_a(x) }}] + [{{ mid_b(x) }}]{% endmacro %}"
    )

    (tmp_path / "source_diamond.yaml").write_text("{{ outer('foo') }}\n")

    # Order 1: outer registered first (worst case)
    run_cli(monkeypatch, [
        "source_diamond.yaml", "-o", "target_diamond_o1",
        "--macros-dir", str(macros_outer),
        "--macros-dir", str(macros_mid_a),
        "--macros-dir", str(macros_mid_b),
        "--macros-dir", str(macros_inner),
        "--env-file", "env.yaml",
    ], capsys)
    assert (tmp_path / "target_diamond_o1" / "source_diamond.yaml").read_text().strip() == \
        "DIAMOND: [A: INNER foo] + [B: INNER foo]"

    # Order 2: inner registered first
    run_cli(monkeypatch, [
        "source_diamond.yaml", "-o", "target_diamond_o2",
        "--macros-dir", str(macros_inner),
        "--macros-dir", str(macros_mid_a),
        "--macros-dir", str(macros_mid_b),
        "--macros-dir", str(macros_outer),
        "--env-file", "env.yaml",
    ], capsys)
    assert (tmp_path / "target_diamond_o2" / "source_diamond.yaml").read_text().strip() == \
        "DIAMOND: [A: INNER foo] + [B: INNER foo]"