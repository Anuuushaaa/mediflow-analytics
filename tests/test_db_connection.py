from unittest.mock import patch

from sqlalchemy.engine import URL

from etl.load import get_engine


def test_get_engine_handles_special_characters(tmp_path, monkeypatch):
    """Database passwords with URL-special characters remain intact."""

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "database:\n"
        "  host: localhost\n"
        "  port: 5432\n"
        "  name: mediflow_analytics\n"
    )

    test_password = "test@pass:/#word"

    monkeypatch.setenv("DB_USER", "test_user")
    monkeypatch.setenv("DB_PASSWORD", test_password)

    with patch("etl.load.create_engine") as mock_create_engine:
        get_engine(str(config_file))

    mock_create_engine.assert_called_once()

    connection_url = mock_create_engine.call_args.args[0]

    assert isinstance(connection_url, URL)
    assert connection_url.username == "test_user"
    assert connection_url.password == test_password
    assert connection_url.host == "localhost"
    assert connection_url.port == 5432
    assert connection_url.database == "mediflow_analytics"