"""The console log handler must not break requests when stderr is unwritable.

A daemonised deploy (systemd, ``nohup``, supervisor) can hand the process a
stderr whose pipe is closed. A plain ``StreamHandler`` then raises ``OSError``
on every ``emit``; the base ``handleError`` reports that back to stderr, which
fails again, so the log fills with ``--- Logging error ---`` noise and the
rotating file handler's output is buried.
"""

import logging

import app as app_module


class _BrokenStream:
    """Stands in for a closed/broken stderr pipe."""

    def write(self, data):
        raise OSError(5, 'I/O error')

    def flush(self):
        raise OSError(5, 'I/O error')


def _record():
    return logging.LogRecord(
        'test', logging.INFO, __file__, 1, 'رسالة', None, None,
    )


def test_safe_stream_handler_swallows_write_oserror(capsys):
    handler = app_module._SafeStreamHandler(_BrokenStream())
    handler.setLevel(logging.INFO)

    # emit() must return normally rather than propagating or reporting.
    assert handler.emit(_record()) is None
    assert 'Logging error' not in capsys.readouterr().err


def test_plain_stream_handler_would_have_reported_it(capsys):
    """Guards the premise: the unpatched handler does emit the noise."""
    handler = logging.StreamHandler(_BrokenStream())
    handler.setLevel(logging.INFO)

    handler.emit(_record())
    assert 'Logging error' in capsys.readouterr().err


def test_setup_logging_installs_the_safe_handler():
    app_module._setup_logging(None)
    assert any(
        isinstance(h, app_module._SafeStreamHandler)
        for h in logging.getLogger().handlers
    )


def test_setup_logging_is_idempotent():
    app_module._setup_logging(None)
    before = len(logging.getLogger().handlers)
    app_module._setup_logging(None)
    assert len(logging.getLogger().handlers) == before
