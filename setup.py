"""Minimal setup.py for editable installs (pip install -e .).

All metadata is in pyproject.toml. This file exists only because
older pip versions require setuptools-based builds for editable mode.

`egg_info.egg_base` redirects the generated *.egg-info directory into
tmp/ (project convention: build artifacts never live in the source tree).
"""

from setuptools import setup

setup(egg_info={"egg_base": "tmp"})
