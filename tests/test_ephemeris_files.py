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
