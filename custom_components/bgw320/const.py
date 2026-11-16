"""Constants for the AT&T BGW320 integration."""

from __future__ import annotations

import logging
from datetime import timedelta

DOMAIN = "bgw320"
LOGGER = logging.getLogger(__package__)

DEFAULT_URL = "https://192.168.1.254"
DEFAULT_VERIFY_SSL = False
DEFAULT_TIMEOUT = 8.0
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)

# Ignore small clock/polling drift when computing boot timestamp from uptime_seconds
BOOT_TIME_DRIFT_TOLERANCE = timedelta(seconds=120)
