"""Minimal .env file loader — no dependencies beyond the stdlib.

Reads KEY=VALUE pairs from a file and sets them into os.environ using
setdefault semantics (real shell env always wins).

Rules:
- Blank lines and lines starting with '#' are skipped.
- Splits on the FIRST '=' only, so values may contain '='.
- Strips trailing whitespace/CRLF from values.
- Strips surrounding single or double quotes from values.
- Sets via os.environ.setdefault so existing env vars are never overridden.
- Missing file is silently ignored.
"""
import os


def load_dotenv(path: str = ".env") -> None:
    """Load environment variables from *path* into os.environ.

    Silently returns if the file does not exist.
    Does NOT override variables already present in the environment.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return

    for raw in lines:
        line = raw.rstrip("\r\n").strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes (single or double)
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if not key:
            continue
        os.environ.setdefault(key, value)
