"""Formatter registry — maps client source to the correct formatter."""

from src.formatters.api import APIFormatter
from src.formatters.base import ResponseFormatter
from src.formatters.cli import CLIFormatter
from src.formatters.neovim import NeovimFormatter
from src.formatters.slack import SlackFormatter

_FORMATTERS: dict[str, ResponseFormatter] = {
    "slack": SlackFormatter(),
    "cli": CLIFormatter(),
    "api": APIFormatter(),
    "neovim": NeovimFormatter(),
}


def get_formatter(source: str = "cli") -> ResponseFormatter:
    """Get the appropriate formatter for the given source."""
    return _FORMATTERS.get(source, _FORMATTERS["cli"])
