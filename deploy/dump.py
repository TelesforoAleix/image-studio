"""Atomic daily custom-format Postgres dump; retain the seven newest dates."""

import datetime
import fcntl
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    directory = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "/srv/homelab/image-studio-data/originals/db"
    )
    # The destination must already exist on the mounted data volume (or in CI).
    os.umask(0o027)
    with (directory / ".dump.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=directory, prefix=".studio-", suffix=".tmp", delete=False
            ) as output:
                temporary = Path(output.name)
                subprocess.run(
                    [
                        "docker",
                        "compose",
                        "exec",
                        "-T",
                        "postgres",
                        "pg_dump",
                        "-U",
                        "studio",
                        "-d",
                        "studio",
                        "--format=custom",
                    ],
                    stdout=output,
                    check=True,
                )
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), 0o640)
            destination = directory / f"studio-{datetime.date.today().isoformat()}.dump"
            os.replace(temporary, destination)
            temporary = None
            dumps = sorted(
                p
                for p in directory.iterdir()
                if re.fullmatch(r"studio-\d{4}-\d{2}-\d{2}\.dump", p.name)
                and p.is_file()
                and not p.is_symlink()
            )
            for old in dumps[:-7]:
                old.unlink()
            print(f"Dump complete: {destination.name}; retained {min(len(dumps), 7)}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
