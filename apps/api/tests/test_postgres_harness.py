import pytest

from tests.postgres_harness import validate_test_postgres_dsn


@pytest.mark.parametrize(
    "dsn",
    [
        "",
        "sqlite:///booker_test.db",
        "postgresql+psycopg://u:p@db.example/booker_test",
        "postgresql+psycopg://u:p@localhost/booker",
        "postgresql+psycopg://u:p@localhost/booker_test?host=prod.example",
        "postgresql+psycopg://u:p@localhost/booker_test?options=-csearch_path%3Dpublic",
    ],
)
def test_postgres_harness_rejects_unsafe_dsn_before_connection(dsn):
    with pytest.raises(ValueError):
        validate_test_postgres_dsn(dsn)


def test_postgres_harness_accepts_only_explicit_local_test_database():
    url = validate_test_postgres_dsn(
        "postgresql+psycopg://booker:example@127.0.0.1:5432/booker_test"
    )
    assert url.database == "booker_test"
