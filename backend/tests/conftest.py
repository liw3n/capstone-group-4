import pytest

from campaign_fixtures import fixture_repository


@pytest.fixture
def campaign_rows():
    """Unit tests inject synthetic rows; runtime always reads PostgreSQL."""
    with fixture_repository():
        yield
