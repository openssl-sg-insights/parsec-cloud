# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPL-3.0 2016-present Scille SAS
from __future__ import annotations

import sys
import trio
import click
import datetime
import traceback
from typing import Any, Optional, Dict
from functools import partial, wraps
from contextlib import contextmanager, asynccontextmanager

from parsec._parsec import DateTime
from parsec.logging import configure_logging, configure_sentry_logging


# Scheme stolen from py-spinners
# MIT License Copyright (c) 2017 Manraj Singh
# (https://github.com/manrajgrover/py-spinners)
SCHEMES = {"dots": {"interval": 80, "frames": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]}}

ok = click.style("✔", fg="green")
ko = click.style("✘", fg="red")


@contextmanager
def operation(txt):

    click.echo(txt, nl=False)
    try:

        yield

    except Exception:
        click.echo(f"\r\033[K{txt} {ko}")
        raise

    else:
        click.echo(f"\r\033[K{txt} {ok}")


@asynccontextmanager
async def spinner(txt, sep=" ", scheme="dots", color="magenta"):
    interval = SCHEMES[scheme]["interval"]
    frames = SCHEMES[scheme]["frames"]
    result = None

    def _render_line(frame):
        # Clear line then re-print it
        click.echo(f"\r\033[K{txt}{sep}{frame}", nl=False)

    async def _update_spinner():
        try:
            i = 1
            while True:
                await trio.sleep(interval / 1000)
                _render_line(click.style(frames[i], fg=color))
                i = (i + 1) % len(frames)
        finally:
            # Last render for result
            _render_line(result)
            click.echo()

    async with trio.open_service_nursery() as nursery:
        _render_line(frames[0])
        nursery.start_soon(_update_spinner)

        try:
            yield

        except Exception:
            result = ko
            raise

        else:
            result = ok

        finally:
            nursery.cancel_scope.cancel()


@contextmanager
def cli_exception_handler(debug):
    try:
        yield debug

    except KeyboardInterrupt:
        click.echo("bye ;-)")
        raise SystemExit(0)

    except Exception as exc:
        exc_msg = str(exc)
        if not exc_msg.strip():
            exc_msg = repr(exc)
        click.echo(click.style("Error: ", fg="red") + exc_msg)
        if debug:
            raise
        else:
            raise SystemExit(1)


def generate_not_available_cmd(exc, hint=None):
    error_msg = "".join(
        [
            click.style("Not available: ", fg="red"),
            "Importing this module has failed with error:\n\n",
            *traceback.format_exception(exc, exc, exc.__traceback__),
            f"\n\n{hint}\n" if hint else "",
        ]
    )

    @click.command(
        context_settings=dict(ignore_unknown_options=True),
        help=f"Not available{' (' + hint + ')' if hint else ''}",
    )
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def bad_cmd(args):
        raise SystemExit(error_msg)

    return bad_cmd


async def aconfirm(*args, **kwargs):
    return await trio.to_thread.run_sync(partial(click.confirm, *args, **kwargs))


async def aprompt(*args: Any, **kwargs: Any) -> Any:
    return await trio.to_thread.run_sync(partial(click.prompt, *args, **kwargs))


def logging_config_options(default_log_level: str):
    LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    assert default_log_level in LOG_LEVELS

    def _logging_config_options(fn):
        @click.option(
            "--log-level",
            "-l",
            type=click.Choice(LOG_LEVELS, case_sensitive=False),
            default=default_log_level,
            show_default=True,
            envvar="PARSEC_LOG_LEVEL",
        )
        @click.option(
            "--log-format",
            "-f",
            type=click.Choice(("CONSOLE", "JSON"), case_sensitive=False),
            default="CONSOLE",
            show_default=True,
            envvar="PARSEC_LOG_FORMAT",
        )
        @click.option(
            "--log-file", "-o", default=None, envvar="PARSEC_LOG_FILE", help="[default: stderr]"
        )
        @wraps(fn)
        def wrapper(**kwargs):
            # `click.open_file` considers "-" to be stdout
            if kwargs["log_file"] in (None, "-"):

                @contextmanager
                def open_log_file():
                    yield sys.stderr

            else:
                open_log_file = partial(click.open_file, kwargs["log_file"], "w")

            with open_log_file() as fd:

                configure_logging(
                    log_level=kwargs["log_level"], log_format=kwargs["log_format"], log_stream=fd
                )

                return fn(**kwargs)

        return wrapper

    return _logging_config_options


def sentry_config_options(configure_sentry: bool):
    def _sentry_config_options(fn):
        # Sentry SKD uses 3 environ variables during it configuration phase:
        # - `SENTRY_DSN`
        # - `SENTRY_ENVIRONMENT`
        # - `SENTRY_RELEASE`
        # Those variable are only used if the corresponding parameter is not
        # explicitly provided while calling `sentry_init(**config)`.
        # Hence we make sure we provide the three parameters (note the release
        # is determined from Parsec's version) so those `PARSEC_*` env vars
        # are never read and don't clash with the `PARSEC_SENTRY_*` ones.
        @click.option(
            "--sentry-dsn",
            metavar="URL",
            envvar="PARSEC_SENTRY_DSN",
            help="Sentry DSN for telemetry report",
        )
        @click.option(
            "--sentry-environment",
            metavar="NAME",
            envvar="PARSEC_SENTRY_ENVIRONMENT",
            default="production",
            show_default=True,
            help="Sentry environment for telemetry report",
        )
        @wraps(fn)
        def wrapper(**kwargs):
            if configure_sentry and kwargs["sentry_dsn"]:
                configure_sentry_logging(
                    dsn=kwargs["sentry_dsn"], environment=kwargs["sentry_environment"]
                )

            return fn(**kwargs)

        return wrapper

    return _sentry_config_options


def debug_config_options(fn):
    decorator = click.option(
        "--debug",
        is_flag=True,
        # Don't prefix with `PARSEC_` given devs are lazy
        envvar="DEBUG",
    )
    return decorator(fn)


class ParsecDateTimeClickType(click.ParamType):
    """
    Add support for RFC3339 date time to `click.DateTime`.

    Funny enough, `click.DateTime` only support local time (e.g. 2000-01-01T00:00:00)
    while we precisely want the exact opposite: only support time in Zoulou
    format (e.g. 2000-01-01T00:00:00Z).

    The rational for this is using local time is very error prone:
    - Copy/pasting between computers `2000-01-01T00:00:00` may changes it meaning
    - The convenient date only format (e.g. `2000-01-01`) becomes ambiguous given
      we don't know if it should use local time or not (for instance with a CET
      timezone `2000-01-01` gets translated to `1999-12-31T23:00:00Z`, even if
      we are in summer and hence current local time is UTC+1 :/)

    So the simple fix is to only allow the Zoulou format (e.g. `2000-01-01T00:00:00Z`)
    and consider the date only format as shortcut for not typing the final `T00:00:00Z`.

    On top of that, we don't support the full range of timezone but only `Z` (so
    `2000-01-01T00:00:00+01:00` is not supported), this makes code much simpler
    and should be enough in most cases.
    """

    name = "datetime"

    def __repr__(self) -> str:
        return "ParsecDateTimeClickType"

    def to_info_dict(self) -> Dict[str, Any]:
        info_dict = super().to_info_dict()
        info_dict["formats"] = self.formats
        return info_dict

    def get_metavar(self, param: click.Parameter) -> str:
        return f"[2000-01-01|2000-01-01T00:00:00Z]"

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> DateTime:
        if isinstance(value, DateTime):
            return value

        assert isinstance(value, str)

        pydt: Optional[datetime.datetime] = None
        try:
            # Try short format
            pydt = datetime.datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            try:
                # Try long format
                pydt = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                try:
                    # Long format with subseconds ?
                    pydt = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
                except ValueError:
                    pass

        if not pydt:
            self.fail(
                f"`{value}` must be a RFC3339 date/datetime (e.g. `2000-01-01` or `2000-01-01T00:00:00Z`)",
                param,
                ctx,
            )

        # strptime consider the provided datetime to be in local time,
        # so we must correct it given we know it is in fact a UTC
        pydt = pydt.replace(tzinfo=datetime.timezone.utc)

        return DateTime.from_timestamp(pydt.timestamp())
