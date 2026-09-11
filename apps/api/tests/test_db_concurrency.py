from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import text

from booker_api.db import make_engine


def test_file_database_allows_parallel_authenticated_request_phases(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'parallel.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE probe (value INTEGER)"))
        connection.execute(text("INSERT INTO probe VALUES (1)"))
    barrier = Barrier(24)

    def request_phase(_):
        with engine.connect() as connection:
            value = connection.execute(text("SELECT value FROM probe")).scalar_one()
            barrier.wait(timeout=5)
            return value

    try:
        with ThreadPoolExecutor(max_workers=24) as workers:
            assert list(workers.map(request_phase, range(24))) == [1] * 24
    finally:
        engine.dispose()


def test_memory_database_survives_connection_reuse():
    engine = make_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE probe (value INTEGER)"))
            connection.execute(text("INSERT INTO probe VALUES (7)"))
        with engine.connect() as connection:
            assert connection.execute(text("SELECT value FROM probe")).scalar_one() == 7
    finally:
        engine.dispose()
