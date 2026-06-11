"""Tests for sentinel.dotenv.load_dotenv — no network, no file system side effects."""
import os

import pytest

from sentinel.dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_env(path, content: str):
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_load_dotenv_sets_simple_key(tmp_path, monkeypatch):
    """A plain KEY=VALUE line is loaded into os.environ."""
    monkeypatch.delenv("MY_TEST_KEY", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, "MY_TEST_KEY=hello\n")
    load_dotenv(str(env_file))
    assert os.environ["MY_TEST_KEY"] == "hello"


def test_load_dotenv_strips_double_quotes(tmp_path, monkeypatch):
    """Double-quoted values are unquoted."""
    monkeypatch.delenv("QUOTED_KEY", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, 'QUOTED_KEY="my value"\n')
    load_dotenv(str(env_file))
    assert os.environ["QUOTED_KEY"] == "my value"


def test_load_dotenv_strips_single_quotes(tmp_path, monkeypatch):
    """Single-quoted values are unquoted."""
    monkeypatch.delenv("SINGLE_KEY", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, "SINGLE_KEY='my value'\n")
    load_dotenv(str(env_file))
    assert os.environ["SINGLE_KEY"] == "my value"


def test_load_dotenv_value_with_spaces_not_quoted(tmp_path, monkeypatch):
    """Values with spaces but no quotes are loaded as-is (stripped of trailing whitespace)."""
    monkeypatch.delenv("SCOPE_KEY", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, "SCOPE_KEY=OR.Jobs OR.Execution\n")
    load_dotenv(str(env_file))
    assert os.environ["SCOPE_KEY"] == "OR.Jobs OR.Execution"


def test_load_dotenv_crlf_line_endings(tmp_path, monkeypatch):
    """CRLF line endings in values are stripped."""
    monkeypatch.delenv("CRLF_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"CRLF_KEY=value\r\n")
    load_dotenv(str(env_file))
    assert os.environ["CRLF_KEY"] == "value"


def test_load_dotenv_skips_blank_lines(tmp_path, monkeypatch):
    """Blank lines are silently skipped."""
    monkeypatch.delenv("AFTER_BLANK", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, "\n\nAFTER_BLANK=yes\n")
    load_dotenv(str(env_file))
    assert os.environ["AFTER_BLANK"] == "yes"


def test_load_dotenv_skips_comments(tmp_path, monkeypatch):
    """Lines starting with # are skipped."""
    monkeypatch.delenv("NOT_A_COMMENT", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, "# this is a comment\nNOT_A_COMMENT=ok\n")
    load_dotenv(str(env_file))
    assert os.environ.get("NOT_A_COMMENT") == "ok"
    # The comment itself must not be a key
    assert os.environ.get("# this is a comment") is None


def test_load_dotenv_value_with_equals_sign(tmp_path, monkeypatch):
    """Splits only on the FIRST = so values can contain = signs."""
    monkeypatch.delenv("URL_KEY", raising=False)
    env_file = tmp_path / ".env"
    _write_env(env_file, "URL_KEY=https://example.com?a=1&b=2\n")
    load_dotenv(str(env_file))
    assert os.environ["URL_KEY"] == "https://example.com?a=1&b=2"


# ---------------------------------------------------------------------------
# No override of existing env
# ---------------------------------------------------------------------------

def test_load_dotenv_does_not_override_existing_env(tmp_path, monkeypatch):
    """Pre-existing env vars are NOT overridden (setdefault semantics)."""
    monkeypatch.setenv("EXISTING_KEY", "original")
    env_file = tmp_path / ".env"
    _write_env(env_file, "EXISTING_KEY=overridden\n")
    load_dotenv(str(env_file))
    assert os.environ["EXISTING_KEY"] == "original"


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------

def test_load_dotenv_missing_file_is_noop(tmp_path):
    """Calling load_dotenv with a non-existent path is a no-op (no exception)."""
    # Should not raise
    load_dotenv(str(tmp_path / "nonexistent.env"))
