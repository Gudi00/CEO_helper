"""Engine (full_auto) and session state machine. See ADRs 0004, 0006, 0007.

This module's runtime deps (selenium, undetected-chromedriver, beautifulsoup4)
live in the `engine` extras of pyproject.toml — install with
`pip install -e .[engine]`.
"""
