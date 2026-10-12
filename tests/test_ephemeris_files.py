import pytest

from astrofacts import ephemeris


def test_missing_files_give_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv(ephemeris.EPHE_ENV, str(tmp_path))
    with pytest.raises(ephemeris.EphemerisError, match="fetch_ephemeris"):
        ephemeris.check_files()


def test_damaged_file_is_rejected(tmp_path, monkeypatch):
    for name in ephemeris.REQUIRED_FILES:
        (tmp_path / name).write_bytes(b"not an ephemeris")
    monkeypatch.setenv(ephemeris.EPHE_ENV, str(tmp_path))
    with pytest.raises(ephemeris.EphemerisError, match="контрольная сумма"):
        ephemeris.check_files()


def test_every_thread_reads_the_files():
    """Регрессия: путь к файлам у библиотеки свой в каждом потоке."""
    import threading

    from astrofacts.types import Body

    expected = ephemeris.state(Body.MOON, 2461325.5)
    results = []

    def work():
        try:
            results.append(ephemeris.state(Body.MOON, 2461325.5))
        except Exception as e:  # noqa: BLE001
            results.append(e)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [expected] * 4
