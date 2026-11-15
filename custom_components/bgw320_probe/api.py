"""Async client and HTML status-page parser for AT&T BGW gateways."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import aiohttp

PAGE_PATHS: dict[str, str] = {
    "system": "/cgi-bin/sysinfo.ha",
    "broadband": "/cgi-bin/broadbandstatistics.ha",
    "firewall": "/cgi-bin/firewall.ha",
}
REQUIRED_PAGES: frozenset[str] = frozenset({"system", "broadband"})

MAX_RESPONSE_BYTES = 1_000_000
USER_AGENT = "bgw320-probe/0.1"

_MAC_RE = re.compile(
    r"^(?:[0-9a-fA-F]{2}([-:]))(?:[0-9a-fA-F]{2}\1){4}[0-9a-fA-F]{2}$"
    r"|^[0-9a-fA-F]{12}$"
)
_INVALID_MACS: frozenset[str] = frozenset({"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"})


class BgwProbeError(Exception):
    """Base exception for BGW320 Probe errors."""


class BgwInvalidUrlError(BgwProbeError):
    """Raised when the configured gateway URL is invalid."""


class BgwConnectionError(BgwProbeError):
    """Raised when the gateway cannot be reached."""


class BgwParseError(BgwProbeError):
    """Raised when gateway HTML cannot be parsed into required fields."""


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    """Normalized gateway hardware and firmware metadata."""

    model: str
    manufacturer: str | None = None
    firmware: str | None = None
    uptime_seconds: int | None = None
    mac_address: str | None = None
    serial_number: str | None = None


@dataclass(frozen=True, slots=True)
class BroadbandInfo:
    """Normalized broadband link state and traffic counters."""

    connection: str
    network_type: str | None = None
    line_state: str | None = None
    speed_mbps: int | float | None = None
    duplex: str | None = None
    rx_packets: int | None = None
    tx_packets: int | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    rx_drops: int | None = None
    tx_drops: int | None = None
    rx_errors: int | None = None
    tx_errors: int | None = None
    collisions: int | None = None
    tx_discards: int | None = None


@dataclass(frozen=True, slots=True)
class FirewallInfo:
    """Normalized high-level firewall feature states."""

    packet_filter: str | None = None
    ip_passthrough: str | None = None
    nat_default_server: str | None = None
    advanced: str | None = None


@dataclass(frozen=True, slots=True)
class BgwSnapshot:
    """Point-in-time snapshot collected from the BGW gateway."""

    gateway: GatewayInfo
    broadband: BroadbandInfo
    firewall: FirewallInfo | None
    failed_pages: dict[str, str]


def normalize_gateway_url(raw_url: str) -> str:
    """Validate and normalize the gateway root URL."""
    candidate = raw_url.strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BgwInvalidUrlError("Gateway URL must use http:// or https:// with a host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise BgwInvalidUrlError("Gateway URL must be a root URL without path or query")
    return candidate


def _clean_cell_text(value: str) -> str:
    """Normalize HTML cell text."""
    return " ".join(unescape(value).replace("\xa0", " ").split())


class _TableRowParser(HTMLParser):
    """Extract two-column label/value rows from HTML tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(_clean_cell_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) >= 2:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def parse_label_value_rows(html: str) -> dict[str, str]:
    """Parse HTML table rows into a first-seen label -> value mapping."""
    parser = _TableRowParser()
    parser.feed(html)
    values: dict[str, str] = {}
    for row in parser.rows:
        label = row[0].strip().rstrip(":")
        value = row[1].strip()
        if label and label not in values:
            values[label] = value
    return values


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())[:128]
    return cleaned or None


def _status(value: str | None) -> str | None:
    cleaned = _text(value)
    return cleaned.lower() if cleaned else None


def _mac_address(value: str | None) -> str | None:
    """Validate and format a 6-octet MAC address, rejecting placeholders."""
    cleaned = _text(value)
    if not cleaned or not _MAC_RE.match(cleaned):
        return None
    hex_digits = cleaned.replace(":", "").replace("-", "").lower()
    formatted = ":".join(hex_digits[i : i + 2] for i in range(0, 12, 2))
    return None if formatted in _INVALID_MACS else formatted


def _first_numeric_token(value: str | None) -> str | None:
    if value is None:
        return None
    tokens = value.replace(",", "").strip().split()
    return tokens[0] if tokens else None


def _number(value: str | None) -> int | float | None:
    token = _first_numeric_token(value)
    if token is None:
        return None
    try:
        parsed = float(token)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _int_counter(value: str | None) -> int | None:
    """Parse non-negative integer counters directly without float precision loss."""
    token = _first_numeric_token(value)
    if token is None:
        return None
    try:
        parsed = int(token)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) not in {3, 4}:
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 3:
        days = 0
        hours, minutes, seconds = numbers
    else:
        days, hours, minutes, seconds = numbers
    if min(numbers) < 0 or minutes > 59 or seconds > 59:
        return None
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class _HttpStatusError(Exception):
    """Internal HTTP status failure wrapper."""

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


def _safe_error_code(exc: Exception) -> str:
    """Convert an exception into a non-sensitive error code."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, _HttpStatusError):
        return f"http_{exc.status}"
    if isinstance(exc, aiohttp.ClientError):
        return "network_error"
    if isinstance(exc, ValueError):
        return "parse_error"
    return "unexpected_error"


class BgwGatewayClient:
    """Async client for read-only AT&T BGW status pages."""

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession,
        timeout: float = 8.0,
    ) -> None:
        """Initialize the gateway client with an injected aiohttp session."""
        self._base_url = normalize_gateway_url(base_url)
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def base_url(self) -> str:
        """Return the normalized gateway base URL."""
        return self._base_url

    async def async_fetch_page(self, page: str) -> str:
        """Fetch a single gateway status page."""
        path = PAGE_PATHS[page]
        async with self._session.get(
            f"{self._base_url}{path}",
            headers={"User-Agent": USER_AGENT},
            timeout=self._timeout,
        ) as response:
            if response.status >= 400:
                raise _HttpStatusError(response.status)
            raw_bytes = await response.content.read(MAX_RESPONSE_BYTES)
            return raw_bytes.decode("utf-8", "replace")

    async def async_collect(self) -> BgwSnapshot:
        """Sequentially fetch and normalize gateway status pages, failing fast on core errors."""
        parsed: dict[str, dict[str, str]] = {}
        failures: dict[str, str] = {}

        for page in PAGE_PATHS:
            try:
                html = await self.async_fetch_page(page)
                rows = parse_label_value_rows(html)
                if not rows:
                    raise ValueError("no table rows")
                parsed[page] = rows
            except Exception as exc:  # noqa: BLE001
                code = _safe_error_code(exc)
                if page in REQUIRED_PAGES:
                    if code == "parse_error":
                        raise BgwParseError(
                            f"Unable to parse {page} status page"
                        ) from exc
                    raise BgwConnectionError(
                        f"Failed to fetch {page} status page ({code})"
                    ) from exc
                failures[page] = code

        system = parsed["system"]
        broadband = parsed["broadband"]

        model = _text(system.get("Model Number"))
        connection = _status(broadband.get("Broadband Connection"))
        if not model or not connection:
            raise BgwParseError("Gateway response missing model or broadband state")

        gateway_info = GatewayInfo(
            model=model,
            manufacturer=_text(system.get("Manufacturer")),
            firmware=_text(system.get("Software Version")),
            uptime_seconds=_duration_seconds(system.get("Time Since Last Reboot")),
            mac_address=_mac_address(system.get("MAC Address")),
            serial_number=_text(system.get("Serial Number")),
        )

        broadband_info = BroadbandInfo(
            connection=connection,
            network_type=_text(broadband.get("Broadband Network Type")),
            line_state=_status(broadband.get("Line State")),
            speed_mbps=_number(broadband.get("Current Speed (Mbps)")),
            duplex=_status(broadband.get("Current Duplex")),
            rx_packets=_int_counter(broadband.get("Receive Packets")),
            tx_packets=_int_counter(broadband.get("Transmit Packets")),
            rx_bytes=_int_counter(broadband.get("Receive Bytes")),
            tx_bytes=_int_counter(broadband.get("Transmit Bytes")),
            rx_drops=_int_counter(broadband.get("Receive Drops")),
            tx_drops=_int_counter(broadband.get("Transmit Drops")),
            rx_errors=_int_counter(broadband.get("Receive Errors")),
            tx_errors=_int_counter(broadband.get("Transmit Errors")),
            collisions=_int_counter(broadband.get("Collisions")),
            tx_discards=_int_counter(broadband.get("Transmit Discards")),
        )

        firewall_info: FirewallInfo | None = None
        if "firewall" in parsed:
            fw = parsed["firewall"]
            firewall_info = FirewallInfo(
                packet_filter=_status(fw.get("Packet Filter")),
                ip_passthrough=_status(fw.get("IP Passthrough")),
                nat_default_server=_status(fw.get("NAT Default Server")),
                advanced=_status(fw.get("Firewall Advanced")),
            )

        return BgwSnapshot(
            gateway=gateway_info,
            broadband=broadband_info,
            firewall=firewall_info,
            failed_pages=failures,
        )
