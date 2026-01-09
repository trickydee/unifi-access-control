# UniFi Access Control

A web-based control panel for managing device access on a Ubiquiti UniFi network. This application allows you to block or enable devices by their MAC addresses, set up scheduled access times, grant temporary access, and view an event log of all access changes.

## Features

- **Manual Device Control**: Toggle device access on/off with a simple switch interface
- **Scheduled Access**: Configure automatic blocking/unblocking times for each device
- **Temporary Access**: Grant devices temporary access for a specified number of minutes with a countdown timer
- **Manual Override Persistence**: Manual toggles persist until the next scheduled event or temporary access expires
- **Ping Verification**: Automatically verify block/enable actions by pinging devices (optional IP address required)
- **Event Log**: View a scrollable history of all enable/disable events, including temporary access grants and verification results
- **Real-time Status**: See connection status, countdown timers, and last enabled/disabled times
- **Mobile-Friendly UI**: Responsive design optimized for mobile devices
- **Persistence**: All state (temporary access, device history, manual overrides, event log) persists across app restarts

## Requirements

- Python 3.9 or higher
- Ubiquiti UniFi Controller (tested with UDMP-unifiOS)
- Network access to the UniFi controller

## Installation

1. Clone the repository:
```bash
git clone https://github.com/trickydee/unifi-access-control.git
cd unifi-access-control
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create configuration files (see Configuration section below)

5. Run the application:
```bash
python unifi-access-control.py
```

The application will be available at `http://localhost:8080`

## Configuration

### config.json

This file contains your UniFi controller credentials. **This file is excluded from git for security reasons.**

Create `config.json` in the project root with the following format:

```json
{
  "unifi_username": "your_username",
  "unifi_password": "your_password",
  "unifi_controller": "192.168.0.5",
  "verification_delay": 10
}
```

**Fields:**
- `unifi_username`: Username for your UniFi controller
- `unifi_password`: Password for your UniFi controller
- `unifi_controller`: IP address or hostname of your UniFi controller
- `verification_delay` (optional): Seconds to wait after block/enable before ping verification (default: 10)

### devices.json

This file defines the devices you want to manage, their MAC addresses, and optional schedule configurations.

**Format:**
```json
{
  "Device Friendly Name": {
    "mac": "aa:bb:cc:dd:ee:ff",
    "ip_address": "192.168.1.100",
    "schedule": {
      "enabled": true,
      "block_time": "22:00",
      "unblock_time": "07:00"
    }
  }
}
```

**Fields:**
- `Device Friendly Name`: A descriptive name for the device (e.g., "Bobs PC", "Freds Laptop", "Sallys MacBook")
- `mac`: The MAC address of the device in `aa:bb:cc:dd:ee:ff` format
- `ip_address` (optional): IP address of the device for ping verification (e.g., "192.168.1.100")
- `schedule` (optional): Schedule configuration object
  - `enabled`: Boolean - whether the schedule is active
  - `block_time`: Time string in `HH:MM` format (24-hour) when the device should be blocked
  - `unblock_time`: Time string in `HH:MM` format (24-hour) when the device should be unblocked

**Schedule Logic:**
- If `unblock_time > block_time` (e.g., unblock 22:00, block 02:10): The unblocked period spans midnight
  - Device is unblocked from `unblock_time` to `block_time` (next day)
  - Device is blocked from `block_time` to `unblock_time` (same day)
- If `unblock_time < block_time` (e.g., unblock 07:00, block 22:00): The blocked period spans midnight
  - Device is blocked from `block_time` to `unblock_time` (next day)
  - Device is unblocked from `unblock_time` to `block_time` (same day)

**Example:**
```json
{
  "Bobs PC": {
    "mac": "aa:bb:cc:dd:ee:ff",
    "ip_address": "192.168.1.100",
    "schedule": {
      "enabled": true,
      "block_time": "22:00",
      "unblock_time": "07:00"
    }
  },
  "Freds Laptop": {
    "mac": "11:22:33:44:55:66",
    "ip_address": "192.168.1.101",
    "schedule": {
      "enabled": false
    }
  },
  "Sallys MacBook": {
    "mac": "aa:11:bb:22:cc:33",
    "ip_address": "192.168.1.102",
    "schedule": {
      "enabled": true,
      "block_time": "23:00",
      "unblock_time": "08:00"
    }
  }
}
```

### device_state.json

This file is automatically created and managed by the application. It stores runtime state including:
- Active temporary access timers
- Device state history (last enabled/disabled times)
- Manual overrides (when devices are manually toggled)
- Event log (last 100 events)

**Format:**
```json
{
  "temporary_access": {
    "Device Name": "2026-01-07T14:30:00.000000"
  },
  "device_state_history": {
    "Device Name": {
      "last_enabled": "2026-01-07T10:00:00.000000",
      "last_disabled": "2026-01-07T09:00:00.000000"
    }
  },
  "manual_overrides": {
    "Device Name": true
  },
  "event_log": [
    {
      "timestamp": "2026-01-07T10:00:00.000000",
      "device": "Device Name",
      "event": "Enabled (Manual)",
      "details": ""
    }
  ]
}
```

**Note:** This file is automatically managed and should not be manually edited. It is excluded from git.

## Usage

### Manual Control

- Toggle the switch next to a device name to enable/disable access
- Manual toggles persist until the next scheduled event or temporary access expires

### Scheduled Access

1. Click the 📅 calendar button next to a device
2. Toggle "Enable Scheduled Blocking" to enable/disable the schedule
3. Enter block and unblock times in `HH:MM` format (24-hour)
4. Click "Save"

The schedule will automatically block/unblock the device at the specified times.

### Temporary Access

1. Click the "+30 min" button next to a device
2. Enter the number of minutes to grant access (default: 30)
3. Click "Grant Access"

A countdown timer will display showing when the device will be blocked again. The device will automatically be blocked when the time expires.

### Event Log

1. Click the "📋 Event Log" button at the top of the page
2. View a scrollable list of all enable/disable events
3. Events are color-coded:
   - Green: Enabled events
   - Red: Disabled events
   - Orange: Temporary access events
4. Click "🗑️ Clear Log" to clear all events

### Ping Verification

The application can automatically verify that block/enable actions were successful by pinging devices:

1. **Configure IP addresses**: Add an `ip_address` field to each device in `devices.json`
2. **Configure delay**: Set `verification_delay` in `config.json` (default: 10 seconds)
3. **Automatic verification**: After each block/enable action, the app will:
   - Wait for the configured delay (default 10 seconds)
   - Ping the device to check if it's online or offline
   - Verify the state matches the expected state (blocked = offline, enabled = online)
   - Log verification results to the event log

**Verification Results:**
- ✓ **Verification Passed**: Device state matches expectation (blocked devices are offline, enabled devices are online)
- ✗ **Verification Failed**: Device state doesn't match (e.g., device is still online after being blocked)

**Note**: If no IP address is configured for a device, verification is skipped (logged at debug level only).

## Features in Detail

### Ping Verification

The application includes automatic ping verification to ensure block/enable actions were successful:

- **How it works**: After a device is blocked or enabled, the app waits for a configurable delay (default 10 seconds), then pings the device's IP address
- **Verification logic**:
  - When a device is **blocked**, it should be **offline** (ping fails)
  - When a device is **enabled**, it should be **online** (ping succeeds)
- **Results**: Verification results are logged to the event log:
  - ✓ Verification Passed: Device state matches expectation
  - ✗ Verification Failed: Device state doesn't match (indicates the UniFi API action may not have worked)
- **Configuration**: 
  - Add `ip_address` field to devices in `devices.json` (optional)
  - Set `verification_delay` in `config.json` (optional, default: 10 seconds)
- **Cross-platform**: Works on Windows, Linux, and macOS
- **Graceful handling**: If no IP address is configured, verification is skipped (no error)

### Manual Override Persistence

When you manually enable or disable a device:
- The manual state persists until the opposite action is taken by:
  - A scheduled event (block/unblock time)
  - Temporary access expiration
  - Another manual toggle
- If you manually enable a device that's currently blocked by schedule, it will stay enabled until the next scheduled block time
- If you manually disable a device that's currently unblocked by schedule, it will stay disabled until the next scheduled unblock time

### Rate Limiting

The application includes built-in rate limiting and exponential backoff to handle UniFi controller API rate limits gracefully. Device status is cached for 30 seconds to reduce API calls.

### Persistence

All runtime state is automatically saved to `device_state.json`:
- Temporary access timers persist across restarts
- Device state history (last enabled/disabled times) is preserved
- Manual overrides are maintained
- Event log (last 100 events) is stored

## Troubleshooting

### Connection Issues

- Check that your UniFi controller is accessible from the machine running the app
- Verify credentials in `config.json`
- Check the connection status indicator at the top of the page

### Rate Limiting

If you see "Rate limited" messages:
- The app will automatically retry with exponential backoff
- Device status caching reduces API calls
- Wait for the rate limit to clear (indicated by countdown timer)

### Schedule Not Working

- Verify schedule is enabled in the calendar dialog
- Check that block and unblock times are correctly formatted (`HH:MM`)
- Ensure the device has a valid MAC address in `devices.json`
- Check the event log to see if schedule events are being logged

## Development

### Debug Mode

Set `DEBUG_MODE = True` in `unifi-access-control.py` to enable verbose logging for debugging.

### Port Configuration

The application runs on port 8080 by default. To change this, modify the `ui.run()` call at the end of `unifi-access-control.py`:

```python
ui.run(dark=True, port=8080)
```

## License

This project is provided as-is for personal use.

## Version

Current version: **v4.0.4**

## Contributing

This is a personal project, but suggestions and improvements are welcome!

