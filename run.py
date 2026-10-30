#!/usr/bin/env python3
"""Точка входа: python run.py [--port 8000] [--open] [--reset]."""

import sys

from server.app import main

if __name__ == "__main__":
    sys.exit(main())
