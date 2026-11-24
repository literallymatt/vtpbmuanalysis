#!/usr/bin/env python3
"""Launch the Python-only GB VTP Settlement Forensics Dash dashboard.

Usage:
    python run_dashboard.py [--host 127.0.0.1] [--port 8050] [--debug]
"""

from __future__ import annotations

from py_dashboard.__main__ import main

if __name__ == "__main__":
    main()
