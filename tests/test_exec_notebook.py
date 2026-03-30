"""Tests for notebook execution via _exec_notebook."""

from pathlib import Path
from unittest.mock import patch

import nbformat
import pytest
from click.testing import CliRunner
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from nbexec import protocol as proto
from nbexec.cli.exec_cmd import exec_code


def _make_notebook(cells, path):
    """Create a .ipynb file with the given cells at path."""
    nb = new_notebook()
    nb.cells = cells
    with open(path, "w") as f:
        nbformat.write(nb, f)


def _make_daemon_response(text="", status="ok", execution_count=1, outputs=None):
    """Create a fake daemon response dict."""
    if outputs is None:
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


def _read_output_notebook(path):
    """Read and return a notebook from path."""
    with open(path) as f:
        return nbformat.read(f, as_version=4)


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
        assert "cell1" in result.output
        assert "cell2" in result.output

    def test_notebook_skips_markdown_and_empty_cells(self, tmp_path):
        """Only non-empty code cells are executed."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_markdown_cell(source="# Title"),
                new_code_cell(source=""),
                new_code_cell(source="   "),
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
        assert call_count == 1

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
        assert call_count == 2

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


class TestOutputNotebook:
    """Test the --output flag for writing executed notebooks."""

    def test_full_run_explicit_output(self, tmp_path):
        """Full run with --output writes executed notebook to that path."""
        nb_path = tmp_path / "input.ipynb"
        out_path = tmp_path / "output.ipynb"
        _make_notebook(
            [
                new_code_cell(source="print('hello')"),
                new_code_cell(source="1 + 1"),
            ],
            nb_path,
        )

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_daemon_response(
                    text="hello\n", execution_count=1,
                    outputs=[{"output_type": "stream", "name": "stdout", "text": "hello\n"}],
                )
            return _make_daemon_response(
                text="2", execution_count=2,
                outputs=[{"output_type": "execute_result", "data": {"text/plain": "2"}, "metadata": {}}],
            )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--output", str(out_path)],
            )

        assert result.exit_code == 0
        assert out_path.exists()
        out_nb = _read_output_notebook(out_path)
        # Both cells should have outputs
        code_cells = [c for c in out_nb.cells if c.cell_type == "code"]
        assert len(code_cells) == 2
        assert len(code_cells[0].outputs) == 1
        assert code_cells[0].outputs[0].output_type == "stream"
        assert code_cells[0].outputs[0].text == "hello\n"
        assert code_cells[1].outputs[0].output_type == "execute_result"
        assert code_cells[1].execution_count == 2
        # stderr reports the output path
        assert "Output notebook:" in result.output

    def test_full_run_auto_output(self, tmp_path):
        """Full run without --output auto-generates <input>_out.ipynb."""
        nb_path = tmp_path / "analysis.ipynb"
        _make_notebook([new_code_cell(source="x = 1")], nb_path)

        def fake_send(method, params, timeout=None):
            return _make_daemon_response(text="", execution_count=1)

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 0
        auto_path = tmp_path / "analysis_out.ipynb"
        assert auto_path.exists()
        assert str(auto_path) in result.output

    def test_partial_run_no_output_flag(self, tmp_path):
        """Partial run without --output does NOT write an output notebook."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [new_code_cell(source="a = 1"), new_code_cell(source="b = 2")],
            nb_path,
        )

        def fake_send(method, params, timeout=None):
            return _make_daemon_response(text="ok\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--from-cell", "1", "--to-cell", "1"],
            )

        assert result.exit_code == 0
        # No output notebook created
        assert not (tmp_path / "test_out.ipynb").exists()
        assert "Output notebook:" not in result.output

    def test_partial_run_with_output(self, tmp_path):
        """Partial run with --output writes only the executed cells' outputs."""
        nb_path = tmp_path / "test.ipynb"
        out_path = tmp_path / "out.ipynb"
        _make_notebook(
            [
                new_code_cell(source="a = 1"),
                new_code_cell(source="b = 2"),
                new_code_cell(source="c = 3"),
            ],
            nb_path,
        )

        def fake_send(method, params, timeout=None):
            return _make_daemon_response(
                text="done\n", execution_count=1,
                outputs=[{"output_type": "stream", "name": "stdout", "text": "done\n"}],
            )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                [
                    "--session", "s", "--file", str(nb_path),
                    "--from-cell", "2", "--to-cell", "2",
                    "--output", str(out_path),
                ],
            )

        assert result.exit_code == 0
        out_nb = _read_output_notebook(out_path)
        code_cells = [c for c in out_nb.cells if c.cell_type == "code"]
        # Cell 2 (index 1) has outputs, cells 1 and 3 do not
        assert len(code_cells[0].outputs) == 0
        assert len(code_cells[1].outputs) == 1
        assert code_cells[1].outputs[0].text == "done\n"
        assert len(code_cells[2].outputs) == 0

    def test_partial_run_incremental_output(self, tmp_path):
        """Two partial runs into the same output file accumulate outputs."""
        nb_path = tmp_path / "test.ipynb"
        out_path = tmp_path / "out.ipynb"
        _make_notebook(
            [
                new_code_cell(source="a = 1"),
                new_code_cell(source="b = 2"),
            ],
            nb_path,
        )

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            return _make_daemon_response(
                text=f"r{call_count}\n", execution_count=call_count,
                outputs=[{"output_type": "stream", "name": "stdout", "text": f"r{call_count}\n"}],
            )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            # First partial run: cell 1
            runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path),
                 "--from-cell", "1", "--to-cell", "1",
                 "--output", str(out_path)],
            )
            # Second partial run: cell 2
            runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path),
                 "--from-cell", "2", "--to-cell", "2",
                 "--output", str(out_path)],
            )

        out_nb = _read_output_notebook(out_path)
        code_cells = [c for c in out_nb.cells if c.cell_type == "code"]
        # Both cells should have outputs from their respective runs
        assert len(code_cells[0].outputs) == 1
        assert code_cells[0].outputs[0].text == "r1\n"
        assert len(code_cells[1].outputs) == 1
        assert code_cells[1].outputs[0].text == "r2\n"

    def test_output_preserves_markdown_cells(self, tmp_path):
        """Output notebook preserves markdown cells from the input."""
        nb_path = tmp_path / "test.ipynb"
        out_path = tmp_path / "out.ipynb"
        _make_notebook(
            [
                new_markdown_cell(source="# Header"),
                new_code_cell(source="x = 42"),
                new_markdown_cell(source="## Section 2"),
            ],
            nb_path,
        )

        def fake_send(method, params, timeout=None):
            return _make_daemon_response(text="", execution_count=1)

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--output", str(out_path)],
            )

        assert result.exit_code == 0
        out_nb = _read_output_notebook(out_path)
        assert len(out_nb.cells) == 3
        assert out_nb.cells[0].cell_type == "markdown"
        assert out_nb.cells[0].source == "# Header"
        assert out_nb.cells[1].cell_type == "code"
        assert out_nb.cells[2].cell_type == "markdown"
        assert out_nb.cells[2].source == "## Section 2"

    def test_output_written_on_error(self, tmp_path):
        """Output notebook is still written when a cell fails."""
        nb_path = tmp_path / "test.ipynb"
        out_path = tmp_path / "out.ipynb"
        _make_notebook(
            [
                new_code_cell(source="ok()"),
                new_code_cell(source="fail()"),
            ],
            nb_path,
        )

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return _make_daemon_response(
                    text="NameError", status="error", execution_count=2,
                    outputs=[{"output_type": "error", "ename": "NameError",
                              "evalue": "name 'fail' is not defined",
                              "traceback": ["NameError: name 'fail' is not defined"]}],
                )
            return _make_daemon_response(
                text="ok\n", execution_count=1,
                outputs=[{"output_type": "stream", "name": "stdout", "text": "ok\n"}],
            )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--output", str(out_path)],
            )

        assert result.exit_code == 1
        # Output notebook is still written with partial results
        assert out_path.exists()
        out_nb = _read_output_notebook(out_path)
        code_cells = [c for c in out_nb.cells if c.cell_type == "code"]
        assert len(code_cells[0].outputs) == 1  # first cell succeeded
        assert code_cells[1].outputs[0].output_type == "error"

    def test_output_written_incrementally(self, tmp_path):
        """Output notebook is flushed to disk after each cell, not just at the end."""
        nb_path = tmp_path / "test.ipynb"
        out_path = tmp_path / "out.ipynb"
        _make_notebook(
            [
                new_code_cell(source="a = 1"),
                new_code_cell(source="b = 2"),
                new_code_cell(source="c = 3"),
            ],
            nb_path,
        )

        snapshots = []  # snapshot output notebook state after each cell

        call_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal call_count
            call_count += 1
            # After the first cell, the output file should already exist on disk.
            if call_count > 1 and out_path.exists():
                snapshots.append(_read_output_notebook(out_path))
            return _make_daemon_response(
                text=f"r{call_count}\n", execution_count=call_count,
                outputs=[{"output_type": "stream", "name": "stdout", "text": f"r{call_count}\n"}],
            )

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--output", str(out_path)],
            )

        assert result.exit_code == 0
        # We should have captured 2 snapshots (before cell 2 and before cell 3)
        assert len(snapshots) == 2
        # After cell 1 completed, snapshot should have cell 1 output
        code_cells_snap1 = [c for c in snapshots[0].cells if c.cell_type == "code"]
        assert len(code_cells_snap1[0].outputs) == 1
        assert code_cells_snap1[0].outputs[0].text == "r1\n"
        # Cell 2 hasn't been recorded yet in this snapshot
        assert len(code_cells_snap1[1].outputs) == 0

    def test_output_rejected_for_non_notebook(self, tmp_path):
        """--output only allowed with .ipynb files."""
        py_path = tmp_path / "script.py"
        py_path.write_text("x = 1\n")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon"):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(py_path), "--output", "out.ipynb"],
            )

        assert result.exit_code == 1
        assert "--output" in result.output

    def test_output_same_as_input_rejected(self, tmp_path):
        """--output pointing to the same file as --file is rejected."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook([new_code_cell(source="x = 1")], nb_path)

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon"):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--output", str(nb_path)],
            )

        assert result.exit_code == 1
        assert "same file" in result.output


class TestCtrlCInterrupt:
    """Test that Ctrl+C during execution sends interrupt to the daemon."""

    def test_single_cell_ctrl_c_sends_interrupt(self):
        """Ctrl+C during single-cell exec interrupts the kernel and exits 130."""
        calls = []

        def fake_send(method, params, timeout=None):
            calls.append(method)
            if method == proto.EXEC:
                raise KeyboardInterrupt
            return {"interrupted": params["session_id"]}

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(exec_code, ["--session", "s", "--code", "x = 1"])

        assert result.exit_code == 130
        assert "Interrupted" in result.output
        assert calls == [proto.EXEC, proto.INTERRUPT]

    def test_notebook_ctrl_c_sends_interrupt(self, tmp_path):
        """Ctrl+C mid-notebook interrupts and exits 130."""
        nb_path = tmp_path / "test.ipynb"
        _make_notebook(
            [
                new_code_cell(source="a = 1"),
                new_code_cell(source="time.sleep(100)"),
                new_code_cell(source="c = 3"),
            ],
            nb_path,
        )

        exec_count = 0
        calls = []

        def fake_send(method, params, timeout=None):
            nonlocal exec_count
            calls.append(method)
            if method == proto.EXEC:
                exec_count += 1
                if exec_count == 2:
                    raise KeyboardInterrupt
                return _make_daemon_response(text="ok\n")
            return {"interrupted": params["session_id"]}

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path)],
            )

        assert result.exit_code == 130
        assert "Interrupted" in result.output
        # Cell 1 exec, cell 2 exec (interrupted), then interrupt sent
        assert calls == [proto.EXEC, proto.EXEC, proto.INTERRUPT]

    def test_notebook_ctrl_c_writes_partial_output(self, tmp_path):
        """Interrupted notebook still writes completed cells to output."""
        nb_path = tmp_path / "test.ipynb"
        out_path = tmp_path / "out.ipynb"
        _make_notebook(
            [
                new_code_cell(source="a = 1"),
                new_code_cell(source="b = 2"),
                new_code_cell(source="c = 3"),
            ],
            nb_path,
        )

        exec_count = 0

        def fake_send(method, params, timeout=None):
            nonlocal exec_count
            if method == proto.EXEC:
                exec_count += 1
                if exec_count == 2:
                    raise KeyboardInterrupt
                return _make_daemon_response(
                    text="ok\n", execution_count=1,
                    outputs=[{"output_type": "stream", "name": "stdout", "text": "ok\n"}],
                )
            return {"interrupted": params["session_id"]}

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(
                exec_code,
                ["--session", "s", "--file", str(nb_path), "--output", str(out_path)],
            )

        assert result.exit_code == 130
        assert out_path.exists()
        out_nb = _read_output_notebook(out_path)
        code_cells = [c for c in out_nb.cells if c.cell_type == "code"]
        # Only cell 1 completed; cells 2 and 3 have no outputs
        assert len(code_cells[0].outputs) == 1
        assert len(code_cells[1].outputs) == 0
        assert len(code_cells[2].outputs) == 0

    def test_interrupt_send_failure_still_exits(self):
        """If sending interrupt to daemon fails, CLI still exits 130."""
        def fake_send(method, params, timeout=None):
            if method == proto.EXEC:
                raise KeyboardInterrupt
            raise ConnectionError("daemon gone")

        runner = CliRunner()
        with patch("nbexec.cli.exec_cmd.send_to_daemon", side_effect=fake_send):
            result = runner.invoke(exec_code, ["--session", "s", "--code", "x = 1"])

        assert result.exit_code == 130
        assert "Interrupted" in result.output
