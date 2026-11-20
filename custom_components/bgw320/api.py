"""Async client and HTML status-page parser for AT&T BGW gateways."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import aiohttp

PAGE_PATHS: dict[str, str] = {
    "system": "/cgi-bin/sysinfo.ha",
    "broadband": "/cgi-bin/broadbandstatistics.ha",
    "firewall": "/cgi-bin/firewall.ha",
}
REQUIRED_PAGE_LABELS: dict[str, tuple[str, ...]] = {
    "system": ("Model Number", "Model", "Device Model"),
    "broadband": ("Broadband Connection", "Connection Status"),
}

MAX_RESPONSE_BYTES = 1_000_000
MAX_UPTIME_SECONDS = 3_153_600_000
USER_AGENT = "ha-bgw320/0.2"
_HEADERS: dict[str, str] = {"User-Agent": USER_AGENT}

_MAC_RE = re.compile(
    r"(?:[0-9a-fA-F]{2}([-:]))(?:[0-9a-fA-F]{2}\1){4}[0-9a-fA-F]{2}"
    r"|[0-9a-fA-F]{12}"
)
_INVALID_MACS: frozenset[str] = frozenset({"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"})
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DURATION_RE = re.compile(
    r"^(?:(\d+)\s*(?:days?|d)?[\s,:]+)?(\d+):(\d{1,2}):(\d{1,2})$",
    re.IGNORECASE,
)
_IGNORED_TAGS: frozenset[str] = frozenset({"script", "style"})


class BgwError(Exception):
    """Base exception for AT&T BGW320 errors."""


class BgwInvalidUrlError(BgwError):
    """Raised when the configured gateway URL is invalid."""


class BgwConnectionError(BgwError):
    """Raised when the gateway cannot be reached."""


class BgwParseError(BgwError):
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
    try:
        parsed = urlparse(raw_url.strip().rstrip("/"))
        port = parsed.port
    except ValueError as err:
        raise BgwInvalidUrlError("Invalid gateway URL") from err
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or any(ch.isspace() or ord(ch) < 32 or ch in "@;" for ch in parsed.netloc)
        or parsed.netloc.endswith(":")
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise BgwInvalidUrlError("Gateway URL must be a root http:// or https:// URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_label(label: str) -> str:
    """Normalize a table label for case- and punctuation-insensitive lookup."""
    return _NON_ALNUM_RE.sub(" ", label.lower()).strip()


def _build_label_index(rows: Mapping[str, str]) -> dict[str, str]:
    """Build a normalized first-seen label map from parsed HTML rows."""
    index: dict[str, str] = {}
    for label, value in rows.items():
        key = _normalize_label(label)
        if key and key not in index:
            index[key] = value
    return index


def _lookup(index: Mapping[str, str], *labels: str) -> str | None:
    """Return the first matching label value from a normalized label index."""
    for label in labels:
        if (value := index.get(_normalize_label(label))) is not None:
            return value
    return None


@dataclass(slots=True)
class _TableScope:
    """Active row and cell buffers for a single HTML table level."""

    row: list[str] | None = None
    cell: list[str] | None = None


class _TableRowParser(HTMLParser):
    """Extract label/value rows across flat, nested, or unclosed-cell HTML tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._scopes: list[_TableScope] = [_TableScope()]
        self._skip = 0

    def _flush_cell(self) -> None:
        scope = self._scopes[-1]
        if scope.cell is not None and scope.row is not None and len(scope.row) < 2:
            scope.row.append(" ".join("".join(scope.cell).split()))
        scope.cell = None

    def _flush_row(self) -> None:
        self._flush_cell()
        scope = self._scopes[-1]
        if scope.row is not None and len(scope.row) >= 2 and scope.row[0]:
            self.rows.append(scope.row)
        scope.row = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORED_TAGS:
            self._skip += 1
        elif self._skip:
            return
        elif tag == "table":
            self._scopes.append(_TableScope())
        elif tag == "tr":
            self._flush_row()
            self._scopes[-1].row = []
        elif tag in {"td", "th"} and self._scopes[-1].row is not None:
            self._flush_cell()
            if len(self._scopes[-1].row) < 2:
                self._scopes[-1].cell = []
        elif tag == "br" and self._scopes[-1].cell is not None:
            self._scopes[-1].cell.append(" ")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag not in _IGNORED_TAGS:
            super().handle_startendtag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if not self._skip and self._scopes[-1].cell is not None:
            self._scopes[-1].cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORED_TAGS and self._skip:
            self._skip -= 1
        elif self._skip:
            return
        elif tag in {"td", "th"}:
            self._flush_cell()
        elif tag in {"tr", "tbody", "thead", "tfoot"}:
            self._flush_row()
        elif tag == "table":
            self._flush_row()
            if len(self._scopes) > 1:
                self._scopes.pop()

    def close(self) -> None:
        super().close()
        while self._scopes:
            self._flush_row()
            self._scopes.pop()


def parse_label_value_rows(html: str) -> dict[str, str]:
    """Parse HTML table rows into a first-seen label -> value mapping."""
    parser = _TableRowParser()
    parser.feed(html)
    parser.close()
    values: dict[str, str] = {}
    seen_normalized: set[str] = set()
    for row in parser.rows:
        label = row[0].rstrip(": ")
        norm = _normalize_label(label)
        if norm and norm not in seen_normalized:
            seen_normalized.add(norm)
            values[label] = row[1]
    return values


def _text(value: str | None) -> str | None:
    return " ".join(value.split())[:128] or None if value is not None else None


def _status(value: str | None) -> str | None:
    return cleaned.lower() if (cleaned := _text(value)) else None


def _mac_address(value: str | None) -> str | None:
    """Validate and format a 6-octet MAC address, rejecting placeholders."""
    cleaned = _text(value)
    if not cleaned or not _MAC_RE.fullmatch(cleaned):
        return None
    hex_digits = cleaned.replace(":", "").replace("-", "").lower()
    formatted = ":".join(hex_digits[i : i + 2] for i in range(0, 12, 2))
    return None if formatted in _INVALID_MACS else formatted


def _first_numeric_token(value: str | None) -> str | None:
    tokens = value.replace(",", "").split(maxsplit=1) if value else []
    return tokens[0] if tokens else None


def _number(value: str | None) -> int | float | None:
    if (token := _first_numeric_token(value)) is None:
        return None
    try:
        parsed = float(token)
    except ValueError:
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _int_counter(value: str | None) -> int | None:
    """Parse non-negative integer counters directly without float precision loss."""
    if (token := _first_numeric_token(value)) is None:
        return None
    try:
        parsed = int(token)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _duration_seconds(value: str | None) -> int | None:
    if not value or not (match := _DURATION_RE.match(value.strip())):
        return None
    days_raw, hours_raw, minutes_raw, seconds_raw = match.groups()
    days = int(days_raw) if days_raw else 0
    hours, minutes, seconds = int(hours_raw), int(minutes_raw), int(seconds_raw)
    if minutes > 59 or seconds > 59:
        return None
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total if total <= MAX_UPTIME_SECONDS else None


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
    return "parse_error" if isinstance(exc, ValueError) else "unexpected_error"


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
        async with self._session.get(
            f"{self._base_url}{PAGE_PATHS[page]}",
            headers=_HEADERS,
            timeout=self._timeout,
        ) as response:
            if response.status >= 400:
                raise _HttpStatusError(response.status)
            content = response.content
            buf = bytearray()
            while (rem := MAX_RESPONSE_BYTES - len(buf)) > 0 and (
                chunk := await content.read(rem)
            ):
                buf.extend(chunk[:rem])
            return buf.decode("utf-8", "replace")

    async def async_collect(self) -> BgwSnapshot:
        """Sequentially fetch and normalize gateway status pages, failing fast on core errors."""
        parsed: dict[str, dict[str, str]] = {}
        failures: dict[str, str] = {}

        for page in PAGE_PATHS:
            try:
                rows = parse_label_value_rows(await self.async_fetch_page(page))
                index = _build_label_index(rows)
                if not index or (
                    (req_labels := REQUIRED_PAGE_LABELS.get(page)) is not None
                    and not _text(_lookup(index, *req_labels))
                ):
                    raise ValueError("missing required table rows")
                parsed[page] = index
            except Exception as exc:  # noqa: BLE001
                code = _safe_error_code(exc)
                if page in REQUIRED_PAGE_LABELS:
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

        model = _text(_lookup(system, *REQUIRED_PAGE_LABELS["system"]))
        connection = _status(_lookup(broadband, *REQUIRED_PAGE_LABELS["broadband"]))
        if not model or not connection:
            raise BgwParseError("Gateway response missing model or broadband state")

        firewall_info: FirewallInfo | None = None
        if (fw := parsed.get("firewall")) is not None:
            fw_vals = (
                _status(_lookup(fw, "Packet Filter")),
                _status(_lookup(fw, "IP Passthrough")),
                _status(_lookup(fw, "NAT Default Server")),
                _status(_lookup(fw, "Firewall Advanced", "Advanced")),
            )
            if any(fw_vals):
                firewall_info = FirewallInfo(*fw_vals)
            else:
                failures["firewall"] = "parse_error"

        return BgwSnapshot(
            gateway=GatewayInfo(
                model=model,
                manufacturer=_text(_lookup(system, "Manufacturer", "Vendor")),
                firmware=_text(
                    _lookup(
                        system, "Software Version", "Firmware Version", "Firmware"
                    )
                ),
                uptime_seconds=_duration_seconds(
                    _lookup(
                        system, "Time Since Last Reboot", "System Uptime", "Uptime"
                    )
                ),
                mac_address=_mac_address(_lookup(system, "MAC Address", "Device MAC")),
                serial_number=_text(_lookup(system, "Serial Number", "Serial")),
            ),
            broadband=BroadbandInfo(
                connection=connection,
                network_type=_text(
                    _lookup(broadband, "Broadband Network Type", "Network Type")
                ),
                line_state=_status(
                    _lookup(broadband, "Line State", "PON Link Status")
                ),
                speed_mbps=_number(
                    _lookup(
                        broadband,
                        "Current Speed (Mbps)",
                        "Current Speed",
                        "Negotiated Speed (Mbps)",
                    )
                ),
                duplex=_status(_lookup(broadband, "Current Duplex", "Duplex")),
                rx_packets=_int_counter(
                    _lookup(
                        broadband, "Receive Packets", "Received Packets", "RX Packets"
                    )
                ),
                tx_packets=_int_counter(
                    _lookup(
                        broadband,
                        "Transmit Packets",
                        "Transmitted Packets",
                        "TX Packets",
                    )
                ),
                rx_bytes=_int_counter(
                    _lookup(broadband, "Receive Bytes", "Received Bytes", "RX Bytes")
                ),
                tx_bytes=_int_counter(
                    _lookup(
                        broadband, "Transmit Bytes", "Transmitted Bytes", "TX Bytes"
                    )
                ),
                rx_drops=_int_counter(_lookup(broadband, "Receive Drops", "RX Drops")),
                tx_drops=_int_counter(
                    _lookup(broadband, "Transmit Drops", "TX Drops")
                ),
                rx_errors=_int_counter(
                    _lookup(broadband, "Receive Errors", "RX Errors")
                ),
                tx_errors=_int_counter(
                    _lookup(broadband, "Transmit Errors", "TX Errors")
                ),
                collisions=_int_counter(_lookup(broadband, "Collisions")),
                tx_discards=_int_counter(
                    _lookup(broadband, "Transmit Discards", "TX Discards")
                ),
            ),
            firewall=firewall_info,
            failed_pages=failures,
        )
