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
    """Run frender.main() in-process with fake argv and capture stdout."""
    monkeypatch.setattr(sys, "argv", ["frender.py", *argv])
    frender.main()
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

def test_cli_with_config(setup_project, monkeypatch, capsys):
    tmp_path, macros, filters = setup_project

    # write config using standalone helper
    make_config(tmp_path, env_file=tmp_path / "env.yaml", macros_dir=macros, filters_dir=filters)

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    run_cli(monkeypatch, ["source2/env.yaml", "-o", "target_config"], capsys)
    run_cli(monkeypatch, ["source2/macro.yaml", "-o", "target_config"], capsys)
    run_cli(monkeypatch, ["source2/filter.yaml", "-o", "target_config"], capsys)

    assert (tmp_path / "target_config" / "env.yaml").read_text().strip() == "foo\nbar\nbaz"
    assert (tmp_path / "target_config" / "macro.yaml").read_text().strip() == "I am a macro foo"
    assert (tmp_path / "target_config" / "filter.yaml").read_text().strip() == "{{ ref(foo) }}"

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


