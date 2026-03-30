"""Tests for notebook execution via _exec_notebook."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import nbformat
import pytest
from click.testing import CliRunner
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from nbexec.cli.exec_cmd import exec_code


def _make_notebook(cells, path):
    """Create a .ipynb file with the given cells at path."""
    nb = new_notebook()
    nb.cells = cells
    with open(path, "w") as f:
        nbformat.write(nb, f)


def _make_daemon_response(text="", status="ok", execution_count=1):
    """Create a fake daemon response dict."""
    outputs = []
    if text:
        outputs.append({"output_type": "stream", "name": "stdout", "text": text})
    return {
        "status": status,
        "execution_count": execution_count,
        "cell_index": 0,
        "outputs": outputs,
        "text": text,
    }


class TestExecNotebook:
    """Test executing .ipynb files through the CLI."""

    def test_basic_notebook_execution(self, tmp_path):
        """Execute a notebook with two code cells, both succeed."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_code_cell(source="print('hello')"),
                new_code_cell(source="print('world')"),
            ],
            nb_path,
        )

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            return _make_daemon_response(
                text=f"cell{call_count}\n", execution_count=call_count
            )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "test-session", "--file", str(nb_path)],
            )

        assert result.exit_code == 0
        assert call_count == 2
        # stdout contains the text output from both cells
        assert "cell1" in result.output
        assert "cell2" in result.output

    def test_notebook_skips_markdown_and_empty_cells(self, tmp_path):
        """Only non-empty code cells are executed."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_markdown_cell(source="# Title"),
                new_code_cell(source=""),  # empty, should be skipped
                new_code_cell(source="   "),  # whitespace-only, should be skipped
                new_code_cell(source="x = 1"),
            ],
            nb_path,
        )

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            return _make_daemon_response(text="ok\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 0
        assert call_count == 1  # only one real code cell

    def test_notebook_stops_on_error(self, tmp_path):
        """Execution stops at the first failing cell."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_code_cell(source="good()"),
                new_code_cell(source="bad()"),
                new_code_cell(source="never_reached()"),
            ],
            nb_path,
        )

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return _make_daemon_response(text="NameError", status="error")
            return _make_daemon_response(text="ok\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 1
        assert call_count == 2  # third cell never executed

    def test_notebook_progress_markers(self, tmp_path):
        """Progress markers like '--- cell 1/3 ---' are printed."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_code_cell(source="a = 1"),
                new_code_cell(source="b = 2"),
                new_code_cell(source="c = 3"),
            ],
            nb_path,
        )

        def fake_send(method, params, timeout=None):
            return _make_daemon_response(text="")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 0
        # Progress markers are emitted (via click.echo(err=True) in production,
        # but CliRunner captures everything together)
        assert "--- cell 1/3 ---" in result.output
        assert "--- cell 2/3 ---" in result.output
        assert "--- cell 3/3 ---" in result.output

    def test_notebook_from_cell_to_cell(self, tmp_path):
        """--from-cell and --to-cell select a range of code cells."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_code_cell(source="cell_1()"),
                new_code_cell(source="cell_2()"),
                new_code_cell(source="cell_3()"),
                new_code_cell(source="cell_4()"),
            ],
            nb_path,
        )

        executed_code = []

        def fake_send(method, params, timeout=None):
            executed_code.append(params["code"])
            return _make_daemon_response(text="ok\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                [
                    "--session", "s",
                    "--file", str(nb_path),
                    "--from-cell", "2",
                    "--to-cell", "3",
                ],
            )

        assert result.exit_code == 0
        assert executed_code == ["cell_2()", "cell_3()"]

    def test_notebook_no_code_cells(self, tmp_path):
        """Notebook with only markdown cells fails gracefully."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [new_markdown_cell(source="# Just a title")],
            nb_path,
        )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon"):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 1
        assert "No code cells" in result.output

    def test_cell_range_flags_rejected_for_non_notebook(self, tmp_path):
        """--from-cell / --to-cell only allowed with .ipynb files."""
        py_path = tmp_path / "script.py"
        py_path.write_text("x = 1\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon"):
            result = runner.invoke(
                exec_code,
                [
                    "--session", "s",
                    "--file", str(py_path),
                    "--from-cell", "1",
                ],
            )

        assert result.exit_code == 1
        assert "--from-cell" in result.output

    def test_notebook_captures_multiline_output(self, tmp_path):
        """Verify multi-line output from cells is captured correctly."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [new_code_cell(source="for i in range(3): print(i)")],
            nb_path,
        )

        def fake_send(method, params, timeout=None):
            return _make_daemon_response(text="0\n1\n2\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 0
        assert "0\n1\n2" in result.output
