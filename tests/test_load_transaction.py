
"""
Tests for transaction-safe PostgreSQL loading.

Uses mocks instead of a real PostgreSQL connection.
No production database tables are modified.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from etl.load import LOAD_ORDER, TABLE_COLUMNS, LoadError, load_all


@pytest.fixture
def mock_clean_data():
    """Create one synthetic row for each database table."""
    return {
        table: pd.DataFrame(
            [{column: None for column in TABLE_COLUMNS[table]}]
        )
        for table in LOAD_ORDER
    }


@pytest.fixture
def mock_database():
    """Mock SQLAlchemy's engine and transaction context."""
    engine = MagicMock()
    connection = MagicMock()

    engine.begin.return_value.__enter__.return_value = connection

    with patch("etl.load.get_engine", return_value=engine):
        with patch.object(pd.DataFrame, "to_sql") as mock_to_sql:
            yield engine, connection, mock_to_sql


def test_successful_load_verifies_before_commit(
    mock_clean_data,
    mock_database,
):
    """A successful load verifies all tables within the transaction."""
    engine, connection, mock_to_sql = mock_database

    connection.execute.return_value.scalar_one.return_value = 1

    load_all(mock_clean_data)

    assert mock_to_sql.call_count == len(LOAD_ORDER)
    assert connection.execute.call_count == 2 * len(LOAD_ORDER)

    # Transaction exits normally, allowing SQLAlchemy to commit.
    engine.begin.return_value.__exit__.assert_called_once_with(
        None, None, None
    )
    engine.dispose.assert_called_once()


def test_row_count_mismatch_rolls_back(
    mock_clean_data,
    mock_database,
):
    """A verification mismatch exits the transaction with an error."""
    engine, connection, mock_to_sql = mock_database

    # Every SELECT COUNT(*) returns zero instead of the expected one.
    connection.execute.return_value.scalar_one.return_value = 0

    with pytest.raises(LoadError, match="Row count mismatch"):
        load_all(mock_clean_data)

    # A non-None exception reaches the transaction context manager.
    exit_args = engine.begin.return_value.__exit__.call_args.args

    assert exit_args[0] is LoadError
    assert isinstance(exit_args[1], LoadError)

    engine.dispose.assert_called_once()
