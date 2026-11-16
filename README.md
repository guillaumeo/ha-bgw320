# AT&T BGW320

<p align="center">
  <img src="custom_components/bgw320/brand/icon@2x.png" alt="AT&T BGW320 Logo" width="128" height="128">
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/marketplace_repository/?owner=guillaumeo&repository=ha-bgw320&category=integration"><img src="https://my.home-assistant.io/badges/marketplace_repository.svg" alt="Open your Home Assistant instance and open this repository in the Marketplace."></a>
  <a href="https://github.com/guillaumeo/ha-bgw320/actions/workflows/validate.yaml"><img src="https://github.com/guillaumeo/ha-bgw320/actions/workflows/validate.yaml/badge.svg" alt="HACS Validation"></a>
  <a href="https://github.com/guillaumeo/ha-bgw320/actions/workflows/hassfest.yaml"><img src="https://github.com/guillaumeo/ha-bgw320/actions/workflows/hassfest.yaml/badge.svg" alt="Validate with hassfest"></a>
</p>

The **AT&T BGW320** integration connects Home Assistant directly to [AT&T Fiber](https://www.att.com/internet/fiber/) BGW320 residential gateways for local, read-only broadband and gateway health monitoring. Use it to detect fiber outages, alert when the negotiated link speed degrades, track cumulative WAN data transfer, monitor packet error and drop counters, and verify firewall or IP Passthrough settings—without deploying an external probe container or entering gateway credentials.

## Supported devices

The following gateway models are supported:

- **AT&T BGW320-500** (manufactured by HUMAX; verified on firmware `6.40.4`)
- **AT&T BGW320-505** (manufactured by Nokia; verified against `6.28.7`+ status-page layout)

## Unsupported devices

The following AT&T gateways are not supported:

- **AT&T BGW620-700** (All-Fi Pro Wi-Fi 7 gateway; untested firmware interface)
- **Pace 5268AC** and **ARRIS NVG589 / NVG599** gateways (different web UI without compatible `/cgi-bin/*.ha` status tables)
- **AT&T Internet Air (5G)** cellular hubs (`CGW450`, `BGW530`)

## Prerequisites

Before adding the integration, verify the following:

1. Ensure your AT&T BGW320 gateway is powered on and reachable from your Home Assistant host over HTTP or HTTPS (default gateway URL: `https://192.168.1.254`).
2. If you run the BGW320 in **IP Passthrough** mode behind your own router (such as UniFi, OPNsense, or pfSense), make sure your router routes traffic from your Home Assistant network to the gateway's LAN subnet (for example, `192.168.1.0/24`) on TCP port `443` (or `80`).
3. Confirm unauthenticated status-page access works from your network by opening `https://192.168.1.254/cgi-bin/sysinfo.ha` in a browser (accepting the gateway's self-signed TLS warning). No device access code or password is needed.

## Installation

### Home Assistant Marketplace / HACS

1. Select the button below to open this repository directly in the **Marketplace** (Home Assistant `2026.11` and newer) or add it manually under **Settings** > **Marketplace** (or **HACS**) > **⋮** > **Custom repositories** with URL `https://github.com/guillaumeo/ha-bgw320` and category **Integration**:

   [![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=guillaumeo&repository=ha-bgw320&category=integration)

2. Install **AT&T BGW320**.
3. Restart Home Assistant when prompted.

### Manual installation

1. Copy the `custom_components/bgw320` folder from this repository into `<config>/custom_components/bgw320` in your Home Assistant configuration directory.
2. Restart Home Assistant.

## Configuration

This integration is configured from the Home Assistant UI:

1. Go to **Settings** > **Devices & services**.
2. In the bottom-right corner, select **Add integration**.
3. Search for and select **AT&T BGW320**, or use the shortcut below:

   [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bgw320)

4. Fill in the setup form and select **Submit**.

### Configuration parameters

- **Gateway URL**: Root URL of your AT&T BGW320 gateway without a path or query string. Defaults to `https://192.168.1.254`. Both `https://` and `http://` (and custom ports such as `https://192.168.1.254:8443`) are supported.
- **Verify SSL certificate**: Whether to validate the gateway's TLS certificate against trusted certificate authorities. Leave disabled (`false`, the default) when using the gateway's built-in self-signed certificate.

## Configuration options

To update connection settings after initial setup without losing entity IDs, area assignments, or long-term statistics:

1. Go to **Settings** > **Devices & services** > **AT&T BGW320**.
2. Select **⋮** next to your gateway entry and choose **Reconfigure**.
3. Update **Gateway URL** or **Verify SSL certificate** and select **Submit**.

> [!NOTE]
> Reconfiguration verifies that the gateway hardware identifier (MAC address or serial number) matches the existing device entry so historical statistics are never mixed across two different physical gateways.

## Supported functionality

The **AT&T BGW320** integration creates one device in the Home Assistant Device Registry (populated with manufacturer, model, firmware version, MAC connection, and gateway configuration link) and provides the following entities.

### Binary sensors

- **Broadband connection**
  - **Description**: Reports `On` (`Connected`) when both `Broadband Connection` and `Line State` report `up`, and `Off` (`Disconnected`) otherwise.
  - **Available for devices**: All supported models
  - **Remarks**: Device class `connectivity`; enabled by default.

### Sensors

#### Enabled by default

- **Last reboot**
  - **Description**: UTC timestamp of the gateway's most recent boot, computed from `Time Since Last Reboot`.
  - **Available for devices**: All supported models
  - **Remarks**: Device class `timestamp`, diagnostic category. Stabilized with a 120-second drift tolerance so polling jitter does not write duplicate states to the Home Assistant database.
- **Negotiated speed**
  - **Description**: Current negotiated broadband link rate in `Mbit/s` (for example, `1000`, `2500`, `5000`, or `10000`).
  - **Available for devices**: All supported models
  - **Remarks**: Device class `data_rate`, state class `measurement`.
- **Broadband received**
  - **Description**: Cumulative bytes received on the WAN interface since the last gateway reboot.
  - **Available for devices**: All supported models
  - **Remarks**: Device class `data_size`, state class `total_increasing`. Native value is tracked with exact 64-bit integer byte precision and displayed in `GB` by default.
- **Broadband transmitted**
  - **Description**: Cumulative bytes transmitted on the WAN interface since the last gateway reboot.
  - **Available for devices**: All supported models
  - **Remarks**: Device class `data_size`, state class `total_increasing`. Native value is tracked in bytes and displayed in `GB` by default.
- **Received packets**
  - **Description**: Cumulative packets received on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: State class `total_increasing`.
- **Transmitted packets**
  - **Description**: Cumulative packets transmitted on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: State class `total_increasing`.
- **Receive errors**
  - **Description**: Cumulative receive errors reported on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category, state class `total_increasing`.
- **Transmit errors**
  - **Description**: Cumulative transmit errors reported on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category, state class `total_increasing`.

#### Disabled by default (extended diagnostics)

Enable any of the following entities in **Settings** > **Devices & services** > **AT&T BGW320** under **Sensors** if you want deeper link or firewall visibility:

- **Broadband network type**
  - **Description**: Upstream access technology reported by the gateway (such as `PON` or `XGS-PON`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default.
- **Line state**
  - **Description**: Raw optical/physical line state reported by the gateway (such as `up` or `down`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default.
- **Duplex**
  - **Description**: Current WAN link duplex mode (such as `full`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default.
- **Receive drops**
  - **Description**: Cumulative inbound packets dropped on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category, state class `total_increasing`; disabled by default.
- **Transmit drops**
  - **Description**: Cumulative outbound packets dropped on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category, state class `total_increasing`; disabled by default.
- **Collisions**
  - **Description**: Cumulative Ethernet collisions recorded on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category, state class `total_increasing`; disabled by default.
- **Transmit discards**
  - **Description**: Cumulative outbound packets discarded on the WAN interface.
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category, state class `total_increasing`; disabled by default.
- **Firewall packet filter**
  - **Description**: Status of the gateway's packet filter ruleset (`on` or `off`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default. Marks itself `Unavailable` if `/cgi-bin/firewall.ha` cannot be fetched.
- **IP passthrough**
  - **Description**: Status of the gateway's IP Passthrough feature (`on` or `off`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default. Useful to detect if a firmware update or factory reset disables IP Passthrough.
- **NAT default server**
  - **Description**: Status of the gateway's NAT Default Server feature (`on` or `off`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default.
- **Firewall advanced**
  - **Description**: Status of the gateway's advanced drop rules (`on` or `off`).
  - **Available for devices**: All supported models
  - **Remarks**: Diagnostic category; disabled by default.

## Automation examples

Here are practical automations you can build with the entities provided by this integration. To paste a YAML example into the visual automation editor, go to **Settings** > **Automations & scenes** > **Create automation** > **Create new automation**, select **⋮** > **Edit in YAML**, paste the snippet (replacing entity IDs with your own), and select **Save**.

### Automation: Notify when fiber broadband goes down

Create a persistent notification in Home Assistant if the fiber connection stays disconnected for at least 1 minute.

- **Trigger**: State of **Broadband connection** changes to `Disconnected` (`off`) for `00:01:00`
- **Action**: **Notifications: Send a persistent notification**

<details>
<summary>YAML example for broadband outage alert</summary>

```yaml
alias: "Alert when AT&T Fiber broadband disconnects"
triggers:
  - trigger: state
    entity_id: binary_sensor.bgw320_500_broadband_connection
    to: "off"
    for: "00:01:00"
actions:
  - action: persistent_notification.create
    data:
      title: "AT&T Fiber disconnected"
      message: "The BGW320 gateway has reported broadband link down for 1 minute."
```

</details>

### Automation: Alert when negotiated link speed degrades

Detect degraded Ethernet/ONT link negotiation (for example, dropping from `10000` or `5000` Mbit/s down to `1000` Mbit/s).

- **Trigger**: Numeric state of **Negotiated speed** drops below `2500` for `00:02:00`
- **Action**: **Notifications: Send a persistent notification**

<details>
<summary>YAML example for link-speed degradation alert</summary>

```yaml
alias: "Alert when AT&T BGW320 negotiated speed degrades"
triggers:
  - trigger: numeric_state
    entity_id: sensor.bgw320_500_negotiated_speed
    below: 2500
    for: "00:02:00"
actions:
  - action: persistent_notification.create
    data:
      title: "AT&T BGW320 speed degraded"
      message: >
        Negotiated speed dropped to {{ states('sensor.bgw320_500_negotiated_speed') }} Mbit/s.
```

</details>

### Automation: Notify when the gateway reboots

Get notified whenever the BGW320 restarts (such as after an overnight AT&T firmware update or power blink).

- **Trigger**: State of **Last reboot** changes
- **Condition**: Previous and new states are neither `unavailable` nor `unknown`
- **Action**: **Notifications: Send a persistent notification**

<details>
<summary>YAML example for gateway reboot notification</summary>

```yaml
alias: "Notify when AT&T BGW320 reboots"
triggers:
  - trigger: state
    entity_id: sensor.bgw320_500_last_reboot
    not_from:
      - unavailable
      - unknown
    not_to:
      - unavailable
      - unknown
actions:
  - action: persistent_notification.create
    data:
      title: "AT&T BGW320 rebooted"
      message: >
        Gateway restarted at {{ states('sensor.bgw320_500_last_reboot') }}.
```

</details>

## Data updates

The **AT&T BGW320** integration polls the gateway locally every **60 seconds** over Home Assistant's shared `aiohttp` connection pool (`local_polling`).

Each poll fetches up to three read-only status pages sequentially with an 8-second request timeout and a 1 MB response cap:

1. `/cgi-bin/sysinfo.ha` (required — hardware metadata, firmware version, and uptime)
2. `/cgi-bin/broadbandstatistics.ha` (required — broadband state, negotiated speed, and interface counters)
3. `/cgi-bin/firewall.ha` (optional — high-level firewall and IP Passthrough states)

If `/cgi-bin/sysinfo.ha` fails, the poll aborts immediately without issuing further requests until the next 60-second interval. If `/cgi-bin/firewall.ha` fails while the required pages succeed, broadband and system entities remain available and only the four firewall diagnostic sensors become `Unavailable`. When a firmware update changes `Software Version`, the Home Assistant Device Registry entry updates automatically.

## Known limitations

- **Read-only monitoring**: The integration cannot reboot the gateway, toggle Wi-Fi radios, or change IP Passthrough settings. Perform configuration changes in the gateway's web interface (`https://192.168.1.254`) using the device access code printed on the gateway label, or in the AT&T Smart Home Manager app.
- **No automatic discovery**: AT&T BGW320 gateways are frequently deployed in IP Passthrough mode on a separate subnet from Home Assistant (`192.168.1.0/24` vs. a downstream LAN), where broadcast/mDNS discovery does not cross routers. You enter the gateway URL once during UI setup.
- **Counter resets on gateway reboot**: Byte, packet, error, drop, collision, and discard values reflect cumulative gateway counters since boot. All counter sensors use `SensorStateClass.TOTAL_INCREASING`, so Home Assistant's Recorder automatically accounts for counter resets without corrupting long-term statistics.
- **Privacy boundary and redacted diagnostics**: Public/WAN IPv4 and IPv6 addresses, DNS servers, Wi-Fi settings, connected client lists, and gateway logs are never stored or exposed as entities. Downloading diagnostics (**Settings** > **Devices & services** > **AT&T BGW320** > **⋮** > **Download diagnostics**) automatically redacts `url`, `mac_address`, `serial_number`, and `unique_id`.

## Troubleshooting

<details>
<summary>Can't set up the device ("Failed to connect to the gateway")</summary>

### Symptom: "Failed to connect to the gateway"

When setting up or reconfiguring the integration, the form displays **Failed to connect to the gateway**.

#### Description

Home Assistant could not establish an HTTP/HTTPS connection to `/cgi-bin/sysinfo.ha` or `/cgi-bin/broadbandstatistics.ha` within 8 seconds. This most commonly happens when the gateway uses a non-default IP address or when a downstream router in **IP Passthrough** mode blocks or fails to route traffic to the gateway's management subnet.

#### Resolution

1. Confirm your gateway's IP address. If your downstream LAN already uses `192.168.1.0/24`, the BGW320 may have been changed to another subnet (such as `192.168.254.254` or `172.16.0.1`).
2. If you use **IP Passthrough** with your own router (UniFi, OPNsense, pfSense, etc.), ensure your router allows outbound traffic from your Home Assistant host/VLAN to the gateway's IP on TCP port `443` (or `80`).
3. Leave **Verify SSL certificate** disabled unless you have installed a certificate signed by a trusted CA.

</details>

<details>
<summary>URL rejected ("Enter a valid http:// or https:// root URL without a path")</summary>

### Symptom: "Enter a valid http:// or https:// root URL without a path"

The setup form highlights **Gateway URL** with an invalid URL error.

#### Description

The URL is missing its `http://` or `https://` scheme, or includes a path such as `/cgi-bin/sysinfo.ha`.

#### Resolution

Enter only the scheme, host, and optional port—for example, `https://192.168.1.254` or `http://192.168.1.254`.

</details>

<details>
<summary>Unexpected page response ("Connected, but the response did not match an AT&T BGW status page")</summary>

### Symptom: "Connected, but the response did not match an AT&T BGW status page"

Home Assistant connected to the host, but could not find a BGW model number or broadband connection state on the returned HTML pages.

#### Description

The target IP belongs to another router/web server on your network, or an unsupported gateway model that does not serve AT&T `.ha` status tables.

#### Resolution

1. Open `<gateway-url>/cgi-bin/sysinfo.ha` in a browser and confirm it displays **Model Number** (`BGW320-500` or `BGW320-505`).
2. Verify that no reverse proxy or captive portal is intercepting requests to that IP address.

</details>

<details>
<summary>Firewall diagnostic sensors show "Unavailable"</summary>

### Symptom: Firewall sensors are "Unavailable" while broadband sensors work

Enabled firewall entities (`IP passthrough`, `Firewall packet filter`, `NAT default server`, `Firewall advanced`) report `Unavailable`, while `Broadband connection` and traffic counters update normally.

#### Description

The optional `/cgi-bin/firewall.ha` endpoint timed out or returned an HTTP error, so the integration degraded gracefully rather than taking all entities offline.

#### Resolution

1. Open `<gateway-url>/cgi-bin/firewall.ha` in a browser to check whether the page responds.
2. Check **Settings** > **System** > **Logs** for a warning from `custom_components.bgw320` showing the non-sensitive failure code (`timeout` or `http_<status>`).

</details>

## Community notes

- Inspiration and metric parity credit goes to [CCOSTAN/bgw-probe](https://github.com/CCOSTAN/bgw-probe).
- Older AT&T gateways that expose identical `/cgi-bin/sysinfo.ha` and `/cgi-bin/broadbandstatistics.ha` status tables (such as the **BGW210-700**) may also work, though this integration is developed and tested against the **BGW320** series.

## Removing the integration

This integration follows standard Home Assistant integration removal:

1. Go to **Settings** > **Devices & services** and select **AT&T BGW320**.
2. Next to your gateway entry, select **⋮** > **Delete**.
3. To remove the custom component files as well, uninstall **AT&T BGW320** from **Settings** > **Marketplace** (or **HACS**, or delete `<config>/custom_components/bgw320` manually) and restart Home Assistant.
