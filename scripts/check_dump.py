"""Restore proof for the disposable CI stack; never run against owner data."""

import datetime
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

COMPOSE = ["docker", "compose", "exec", "-T", "postgres"]


def sql(database, query):
    return subprocess.check_output(
        COMPOSE
        + [
            "psql",
            "-U",
            "studio",
            "-d",
            database,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            query,
        ],
        text=True,
    ).strip()


def counts(database):
    tables = sql(
        database,
        "SELECT tablename FROM pg_tables "
        "WHERE schemaname = 'public' ORDER BY tablename",
    ).splitlines()
    assert tables, "No restored tables"
    result = {}
    for table in tables:
        identifier = '"' + table.replace('"', '""') + '"'
        result[table] = int(sql(database, f"SELECT count(*) FROM public.{identifier}"))
    return result


def main():
    scratch = "restore_check_" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run([sys.executable, "deploy/dump.py", directory], check=True)
        dump = Path(directory) / f"studio-{datetime.date.today().isoformat()}.dump"
        assert dump.stat().st_mode & 0o777 == 0o640
        source = counts("studio")
        subprocess.run(COMPOSE + ["createdb", "-U", "studio", scratch], check=True)
        try:
            with dump.open("rb") as data:
                subprocess.run(
                    COMPOSE
                    + ["pg_restore", "-U", "studio", "-d", scratch, "--exit-on-error"],
                    stdin=data,
                    check=True,
                )
            restored = counts(scratch)
            assert restored == source, (source, restored)
            print("PROOF dump restored with matching tables and row counts:", restored)
        finally:
            subprocess.run(COMPOSE + ["dropdb", "-U", "studio", scratch], check=True)


if __name__ == "__main__":
    main()
