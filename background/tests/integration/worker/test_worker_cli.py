from background.cli import main


def test_worker_cli_prints_result(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["background-worker", "worker"])

    assert main() == 0

    captured = capsys.readouterr()
    assert '"name":"worker"' in captured.out
    assert '"status":"ok"' in captured.out
