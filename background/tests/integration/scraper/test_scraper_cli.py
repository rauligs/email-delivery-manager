from background.cli import main


def test_scraper_cli_prints_result(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["background-worker", "scraper"])

    assert main() == 0

    captured = capsys.readouterr()
    assert '"name":"scraper"' in captured.out
    assert '"status":"ok"' in captured.out
