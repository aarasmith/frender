import sys
import textwrap
import os
from pathlib import Path
import pytest
import frender  # your script should be importable as a module


# ---------------------------
# Helpers for test setup
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
    macros = base / "macros"
    macros.mkdir()
    (macros / "test_macro.j2").write_text(
        "{% macro test_macro(x) %}I am a macro {{ x }}{% endmacro %}"
    )

    filters = base / "filters"
    filters.mkdir()
    (filters / "ref.py").write_text(textwrap.dedent("""\
        from markupsafe import Markup
        def ref(value):
            return Markup(f"{{{{ ref({value}) }}}}")
    """))
    return macros, filters

def make_config(base_path: Path, env_file=None, macros_dir=None, filters_dir=None) -> Path:
    """Write a .frender/config file inside base_path."""
    config_dir = base_path / ".frender"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config"
    lines = [
        f"ENV_FILE={env_file or ''}",
        f"MACROS_DIR={macros_dir or ''}",
        f"FILTERS_DIR={filters_dir or ''}"
    ]
    config_file.write_text("\n".join(lines))
    return config_file

def run_cli(monkeypatch, argv, capsys):
    monkeypatch.setattr(sys, "argv", ["frender.py", *argv])
    try:
        frender.main()
    except SystemExit as e:
        # Let pytest continue; we can inspect exit code if needed
        pass
    return capsys.readouterr()


# ---------------------------
# Fixtures
# ---------------------------

@pytest.fixture
def setup_project(tmp_path):
    make_env_files(tmp_path)
    make_sources(tmp_path)
    macros, filters = make_macros_and_filters(tmp_path)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path, macros, filters
    os.chdir(cwd)


# ---------------------------
# Individual tests
# ---------------------------

def test_stdout_render(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    out = run_cli(monkeypatch, ["source1/test.yml"], capsys)
    assert out.out.strip() == "foo\nbar"


def test_overwrite_in_place(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["source1/test.yml", "-ow"], capsys)
    assert Path("source1/test.yml").read_text().strip() == "foo\nbar"


def test_list_mode_flatten(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["-l", "source1/test.yml,source1/test2.yaml", "-o", "target"], capsys)
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


def test_custom_env_file_json(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project
    run_cli(monkeypatch, ["source2/env.yaml", "-o", "target5", "--env-file", "env.json"], capsys)
    rendered = Path("target5/env.yaml").read_text().strip()
    assert rendered == "foo\nbar\nbaz"


def test_macros_dir(setup_project, monkeypatch, capsys):
    tmp_path, macros, _ = setup_project
    run_cli(monkeypatch, ["source2/macro.yaml", "-o", "target6", "--macros-dir", str(macros)], capsys)
    rendered = Path("target6/macro.yaml").read_text().strip()
    assert rendered == "I am a macro foo"


def test_filters_dir(setup_project, monkeypatch, capsys):
    tmp_path, _, filters = setup_project
    run_cli(monkeypatch, ["source2/filter.yaml", "-o", "target7", "--filters-dir", str(filters)], capsys)
    rendered = Path("target7/filter.yaml").read_text().strip()
    assert rendered == "{{ ref(foo) }}"

# def test_cli_with_config(setup_project, monkeypatch, capsys):
#     tmp_path, macros, filters = setup_project

#     # write config using standalone helper
#     make_config(tmp_path, env_file=tmp_path / "env.yaml", macros_dir=macros, filters_dir=filters)

#     monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

#     run_cli(monkeypatch, ["source2/env.yaml", "-o", "target_config"], capsys)
#     run_cli(monkeypatch, ["source2/macro.yaml", "-o", "target_config"], capsys)
#     run_cli(monkeypatch, ["source2/filter.yaml", "-o", "target_config"], capsys)

#     assert (tmp_path / "target_config" / "env.yaml").read_text().strip() == "foo\nbar\nbaz"
#     assert (tmp_path / "target_config" / "macro.yaml").read_text().strip() == "I am a macro foo"
#     assert (tmp_path / "target_config" / "filter.yaml").read_text().strip() == "{{ ref(foo) }}"

def test_cli_overrides_config(setup_project, monkeypatch, capsys):
    """
    Verify that --env-file, --macros-dir, and --filters-dir CLI arguments
    override any values specified in the ~/.frender/config file.
    """
    tmp_path, macros, filters = setup_project

    # Write dummy config (values won't actually be used)
    make_config(tmp_path, env_file="dummy_env", macros_dir="dummy_macros", filters_dir="dummy_filters")

    # Monkeypatch Path.home() so frender will pick up the config file
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    # Run CLI on each source file with explicit CLI overrides
    for src in ["env.yaml", "macro.yaml", "filter.yaml"]:
        run_cli(
            monkeypatch,
            [
                f"source2/{src}",
                "-o",
                "target_override",
                "--env-file",
                "env.yaml",
                "--macros-dir",
                "macros",
                "--filters-dir",
                "filters",
            ],
            capsys,
        )

    # Verify all files rendered correctly using the CLI-specified paths
    assert (tmp_path / "target_override" / "env.yaml").read_text().strip() == "foo\nbar\nbaz"
    assert (tmp_path / "target_override" / "macro.yaml").read_text().strip() == "I am a macro foo"
    assert (tmp_path / "target_override" / "filter.yaml").read_text().strip() == "{{ ref(foo) }}"
def test_cli_overrides_config(setup_project, monkeypatch, capsys):
    """
    Verify that --env-file, --macros-dir, and --filters-dir CLI arguments
    override any values specified in the ~/.frender/config file.
    """
    tmp_path, macros, filters = setup_project

    # Write dummy config (values won't actually be used)
    make_config(tmp_path, env_file="dummy_env", macros_dir="dummy_macros", filters_dir="dummy_filters")

    # Monkeypatch Path.home() so frender will pick up the config file
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    # Run CLI on each source file with explicit CLI overrides
    for src in ["env.yaml", "macro.yaml", "filter.yaml"]:
        run_cli(
            monkeypatch,
            [
                f"source2/{src}",
                "-o",
                "target_override",
                "--env-file",
                "env.yaml",
                "--macros-dir",
                "macros",
                "--filters-dir",
                "filters",
            ],
            capsys,
        )

    # Verify all files rendered correctly using the CLI-specified paths
    assert (tmp_path / "target_override" / "env.yaml").read_text().strip() == "foo\nbar\nbaz"
    assert (tmp_path / "target_override" / "macro.yaml").read_text().strip() == "I am a macro foo"
    assert (tmp_path / "target_override" / "filter.yaml").read_text().strip() == "{{ ref(foo) }}"

def test_multiple_env_files(setup_project, monkeypatch, capsys):
    """
    Verify that multiple --env-file arguments are merged correctly.
    Later files should override keys from earlier ones.
    """
    tmp_path, _, _ = setup_project

    # Create two environment files with overlapping keys
    (tmp_path / "env1.yaml").write_text(
        "key1: foo\nkey2: bar\nunique1: only_in_env1\n"
    )
    (tmp_path / "env2.yaml").write_text(
        "key2: baz\nkey3: qux\nunique2: only_in_env2\n"
    )

    # Template references keys from both files
    (tmp_path / "source_merge.yaml").write_text(
        "{{ key1 }}\n{{ key2 }}\n{{ key3 }}\n{{ unique1 }}\n{{ unique2 }}\n"
    )

    # Run CLI with both env files (order matters!)
    run_cli(
        monkeypatch,
        [
            "source_merge.yaml",
            "-o",
            "target_multi",
            "--env-file",
            "env1.yaml",
            "--env-file",
            "env2.yaml",
        ],
        capsys,
    )

    rendered = (tmp_path / "target_multi" / "source_merge.yaml").read_text().strip()

    # Expected behavior:
    # - key1 from env1
    # - key2 overridden by env2
    # - key3 from env2
    # - unique1 from env1
    # - unique2 from env2
    assert rendered == "foo\nbaz\nqux\nonly_in_env1\nonly_in_env2"


def test_cli_file_var_injected_into_context(setup_project, monkeypatch, capsys):
    tmp_path, _, _ = setup_project

    #File whose raw contents will be injected
    raw_file = tmp_path / "raw.txt"
    raw_file.write_text("hello from file-var")

    # Template that uses both env vars and the file var
    template = tmp_path / "source_file_var.yaml"
    template.write_text(
        "{{ key1 }}\n{{ file_contents }}\n"
    )

    run_cli(
        monkeypatch,
        [
            "source_file_var.yaml",
            "-o",
            "target_file_var",
            "--env-file",
            "env.yaml",
            "--file-var",
            f"file_contents={raw_file}",
        ],
        capsys,
    )

    rendered = (tmp_path / "target_file_var" / "source_file_var.yaml").read_text().strip()

    assert rendered == "foo\nhello from file-var"

def test_filter_override_later_dir_wins(tmp_path, monkeypatch, capsys):
    """
    Verify that a filter defined in a later --filters-dir supersedes one with the same
    name from an earlier directory, mirroring the override semantics of --macros-dir.
    """
    filters1 = tmp_path / "filters1"
    filters1.mkdir()
    (filters1 / "ref.py").write_text(
        "from markupsafe import Markup\n"
        "def ref(value):\n"
        "    return Markup(f'FIRST({value})')\n"
    )

    filters2 = tmp_path / "filters2"
    filters2.mkdir()
    (filters2 / "ref.py").write_text(
        "from markupsafe import Markup\n"
        "def ref(value):\n"
        "    return Markup(f'SECOND({value})')\n"
    )

    tpl = tmp_path / "tpl.j2"
    tpl.write_text("{{ 'bar' | ref }}")

    out_dir = tmp_path / "out"

    run_cli(
        monkeypatch,
        [
            str(tpl),
            "-o", str(out_dir),
            "--filters-dir", str(filters1),
            "--filters-dir", str(filters2),
        ],
        capsys,
    )

    rendered = (out_dir / tpl.name).read_text().strip()
    assert rendered == "SECOND(bar)"

def test_deeply_nested_macros_across_directories_order_independent(setup_project, monkeypatch, capsys):
    """
    Verify that macros can call other macros at multiple nesting levels across different --macros-dir
    folders without explicit Jinja imports, and that the result is independent of directory order.

    Scenario:
      - macro_a defines: inner(x)   -> "INNER {{ x }}"
      - macro_b defines: mid(x)     -> uses inner(x) within a {% set %} (nested call)
      - macro_c defines: outer(x)   -> calls mid(x) and inner(x) again
      - template uses: outer('foo')
    
    We render twice with opposite macro-dir orders (outer-first vs. inner-first).
    Expected output is the same both times "OUTER -> MID [INNER foo] & INNER foo"
    """
    tmp_path, _, _ = setup_project

    # Create three macro roots with multi-level nesting
    macros_a = tmp_path / "macros_a"
    macros_a.mkdir()
    (macros_a / "inner.j2").write_text(
        "{% macro inner(x) %}INNER {{ x }}{% endmacro %}"
    )

    macros_b = tmp_path / "macros_b"
    macros_b.mkdir()
    (macros_b / "mid.sql").write_text(
        "{% macro mid(x) %}{% set v = inner(x) %}MID [{{ v }}]{% endmacro %}"
    )

    macros_c = tmp_path / "macros_c"
    macros_c.mkdir()
    (macros_c / "outer.sql").write_text(
        "{% macro outer(x) %}OUTER -> {{ mid(x) }} & {{ inner(x) }}{% endmacro %}"
    )

    # Template that triggers the deepest chain
    tpl = tmp_path / "source_nesting.yaml"
    tpl.write_text("{{ outer('foo') }}\n")

    # --- Order 1: "worst-case" (outer-first) ---
    run_cli(
        monkeypatch,
        [
            "source_nesting.yaml",
            "-o", "target_nesting_o1",
            "--macros-dir", str(macros_c),
            "--macros-dir", str(macros_b),
            "--macros-dir", str(macros_a),
            "--env-file", "env.yaml",
        ],
        capsys,
    )

    out1 = (tmp_path / "target_nesting_o1" / "source_nesting.yaml").read_text().strip()
    assert out1 == "OUTER -> MID [INNER foo] & INNER foo"

    # --- Order 2: reverse (inner-first) ---
    run_cli(
        monkeypatch,
        [
            "source_nesting.yaml",
            "-o", "target_nesting_o2",
            "--macros-dir", str(macros_a),
            "--macros-dir", str(macros_b),
            "--macros-dir", str(macros_c),
            "--env-file", "env.yaml",
        ],
        capsys,
    )

    out2 = (tmp_path / "target_nesting_o2" / "source_nesting.yaml").read_text().strip()
    assert out2 == "OUTER -> MID [INNER foo] & INNER foo"

def test_macro_diamond_dependency_across_directories(setup_project, monkeypatch, capsys):
    """
    Verify correct resolution when multiple macros share a common dependency (diamond pattern),
    all living in separate --macros-dir directories.

    Call graph:
                     outer(x)
                    /         \\
              mid_a(x)       mid_b(x)
                    \\         /
                     inner(x)

    'inner' must be resolved correctly when called from both mid_a AND mid_b, even though
    none of these macros share a file or use explicit {% import %} statements.
    This is the strongest stress-test for the registry's call-time context injection —
    a naive implementation that injects context shallowly would fail here.

    Expected: "DIAMOND: [A: INNER foo] + [B: INNER foo]"
    """
    tmp_path, _, _ = setup_project

    macros_inner = tmp_path / "macros_inner"
    macros_inner.mkdir()
    (macros_inner / "inner.j2").write_text(
        "{% macro inner(x) %}INNER {{ x }}{% endmacro %}"
    )

    macros_mid_a = tmp_path / "macros_mid_a"
    macros_mid_a.mkdir()
    (macros_mid_a / "mid_a.j2").write_text(
        "{% macro mid_a(x) %}A: {{ inner(x) }}{% endmacro %}"
    )

    macros_mid_b = tmp_path / "macros_mid_b"
    macros_mid_b.mkdir()
    (macros_mid_b / "mid_b.j2").write_text(
        "{% macro mid_b(x) %}B: {{ inner(x) }}{% endmacro %}"
    )

    macros_outer = tmp_path / "macros_outer"
    macros_outer.mkdir()
    (macros_outer / "outer.j2").write_text(
        "{% macro outer(x) %}DIAMOND: [{{ mid_a(x) }}] + [{{ mid_b(x) }}]{% endmacro %}"
    )

    tpl = tmp_path / "source_diamond.yaml"
    tpl.write_text("{{ outer('foo') }}\n")

    # Order 1: outer registered first (worst case — dependencies not yet known)
    run_cli(
        monkeypatch,
        [
            "source_diamond.yaml",
            "-o", "target_diamond_o1",
            "--macros-dir", str(macros_outer),
            "--macros-dir", str(macros_mid_a),
            "--macros-dir", str(macros_mid_b),
            "--macros-dir", str(macros_inner),
            "--env-file", "env.yaml",
        ],
        capsys,
    )
    out1 = (tmp_path / "target_diamond_o1" / "source_diamond.yaml").read_text().strip()
    assert out1 == "DIAMOND: [A: INNER foo] + [B: INNER foo]"

    # Order 2: inner registered first
    run_cli(
        monkeypatch,
        [
            "source_diamond.yaml",
            "-o", "target_diamond_o2",
            "--macros-dir", str(macros_inner),
            "--macros-dir", str(macros_mid_a),
            "--macros-dir", str(macros_mid_b),
            "--macros-dir", str(macros_outer),
            "--env-file", "env.yaml",
        ],
        capsys,
    )
    out2 = (tmp_path / "target_diamond_o2" / "source_diamond.yaml").read_text().strip()
    assert out2 == "DIAMOND: [A: INNER foo] + [B: INNER foo]"

def test_macro_override_later_dir_wins(tmp_path, monkeypatch, capsys):
    macros1 = tmp_path / "macros1"
    macros1.mkdir()
    (macros1 / "base.j2").write_text(
        "{% macro test_macro(x) %}BASE {{ x }}{% endmacro %}"
    )

    macros2 = tmp_path / "macros2"
    macros2.mkdir()
    (macros2 / "override.j2").write_text(
        "{% macro test_macro(x) %}OVERRIDE {{ x }}{% endmacro %}"
    )

    tpl = tmp_path / "tpl.j2"
    tpl.write_text("{{ test_macro('foo') }}")

    # Output directory
    out_dir = tmp_path / "out"

    run_cli(
        monkeypatch,
        [
            str(tpl),
            "-o", str(out_dir),
            "--macros-dir", str(macros1),
            "--macros-dir", str(macros2),
        ],
        capsys,
    )

    # Let the CLI decide the output filename; mirror source
    output_file = out_dir / tpl.name
    assert output_file.exists(), f"Expected rendered file: {output_file}"
    rendered = output_file.read_text().strip()
    assert rendered == "OVERRIDE foo"


def test_macro_override_same_filename(tmp_path, monkeypatch, capsys):
    macros1 = tmp_path / "macros1"
    macros1.mkdir()
    (macros1 / "test.j2").write_text(
        "{% macro test_macro(x) %}FIRST {{ x }}{% endmacro %}"
    )

    macros2 = tmp_path / "macros2"
    macros2.mkdir()
    (macros2 / "test.j2").write_text(
        "{% macro test_macro(x) %}SECOND {{ x }}{% endmacro %}"
    )

    tpl = tmp_path / "tpl.j2"
    tpl.write_text("{{ test_macro('foo') }}")

    out_dir = tmp_path / "out"

    run_cli(
        monkeypatch,
        [
            str(tpl),
            "-o", str(out_dir),
            "--macros-dir", str(macros1),
            "--macros-dir", str(macros2),
        ],
        capsys,
    )

    output_file = out_dir / tpl.name
    assert output_file.exists(), f"Expected rendered file: {output_file}"
    rendered = output_file.read_text().strip()
    assert rendered == "SECOND foo"
