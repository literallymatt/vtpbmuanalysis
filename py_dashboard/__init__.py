"""Python-only Dash dashboard for GB VTP Settlement Forensics."""

from __future__ import annotations

__all__ = ["create_app"]


def create_app():
    """Lazily import and construct the Dash application."""
    from .app import create_app as _create_app

    return _create_app()
