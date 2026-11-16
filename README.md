# AT&T BGW320 for Home Assistant (`ha-bgw320`)

<p align="center">
  <img src="custom_components/bgw320/brand/icon@2x.png" alt="AT&T BGW320 Logo" width="128" height="128">
</p>

Native Home Assistant custom integration for read-only monitoring of **AT&T BGW320** gateways, inspired by [CCOSTAN/bgw-probe](https://github.com/CCOSTAN/bgw-probe).

Polls the gateway's unauthenticated status pages (`/cgi-bin/sysinfo.ha`, `/cgi-bin/broadbandstatistics.ha`, and `/cgi-bin/firewall.ha`) directly over Home Assistant's managed `aiohttp` client session—**no external Docker container or third-party PyPI dependency required**.

## Features

- **Direct Local Polling:** Sequential keep-alive HTTP/HTTPS requests every 60 seconds with self-signed TLS support.
- **Full `bgw-probe` Signal Parity:**
  - **Connectivity (`binary_sensor`):** Broadband connection (`connection == up` and `line_state == up`).
  - **Primary Telemetry (`sensor`, enabled by default):** Last reboot timestamp (drift-stabilized), negotiated link speed (`Mbit/s`), received/transmitted bytes (displayed in `GB`), received/transmitted packets, and receive/transmit errors.
  - **Extended Diagnostics (`sensor`, disabled by default):** Broadband network type, line state, duplex, receive/transmit drops, collisions, transmit discards, and firewall states (`packet_filter`, `ip_passthrough`, `nat_default_server`, `advanced`).
- **Privacy & Diagnostics:** Public IPs, Wi-Fi settings, credentials, and logs are never stored or exposed. Hardware MAC/serial are used solely for Home Assistant Device Registry linking and redacted in downloadable diagnostics.
- **Reconfiguration Flow:** Update the gateway URL or SSL verification from the UI without losing long-term statistics.

## Installation

### HACS (Custom Repository)
1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/guillaumeo/ha-bgw320` with category **Integration**.
3. Install **AT&T BGW320** and restart Home Assistant.

### Manual
1. Copy `custom_components/bgw320` into your Home Assistant `<config>/custom_components/bgw320` folder.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & services → Add Integration**.
2. Search for **AT&T BGW320**.
3. Enter your gateway root URL (default: `https://192.168.1.254`) and leave **Verify SSL certificate** disabled unless you have installed a trusted certificate on the gateway.

## Removal

1. Go to **Settings → Devices & services → AT&T BGW320**.
2. Select **⋮ → Delete**, then remove `custom_components/bgw320` (or uninstall via HACS) and restart Home Assistant.
