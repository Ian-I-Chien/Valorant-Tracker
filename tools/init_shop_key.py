"""Generate a private Fernet key file, refusing to overwrite an existing key."""

import argparse
import os
from pathlib import Path

from cryptography.fernet import Fernet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(Fernet.generate_key() + b"\n")
    print(
        "Private shop key created. Keep it outside the repository and database backups."
    )


if __name__ == "__main__":
    main()
