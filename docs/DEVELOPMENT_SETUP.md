# Development Setup Guide

This guide provides step-by-step instructions for setting up the UniFi Access Control application on a new development instance.

## Prerequisites

- Python 3.9 or higher
- Git
- Network access to UniFi Controller
- Terminal/command line access

## Step 1: Clone the Repository

```bash
git clone <repository-url>
cd unifi-access-control
```

## Step 2: Create Virtual Environment

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python3 -m venv venv
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt when activated.

## Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Expected output:**
- `pyunifi>=2.21`
- `nicegui>=3.4.1`

## Step 4: Create Configuration Files

### 4.1 Create `config.json`

Create `config.json` in the project root:

```json
{
  "unifi_username": "your_unifi_username",
  "unifi_password": "your_unifi_password",
  "unifi_controller": "192.168.0.5",
  "verification_delay": 10
}
```

**Fields:**
- `unifi_username`: Your UniFi controller username
- `unifi_password`: Your UniFi controller password
- `unifi_controller`: IP address or hostname of your UniFi controller
- `verification_delay`: (Optional) Seconds to wait before ping verification (default: 10)

**Security Note:** This file contains credentials and is excluded from git. Never commit it.

### 4.2 Create `devices.json`

Create `devices.json` in the project root:

```json
{
  "Device Friendly Name": {
    "mac": "aa:bb:cc:dd:ee:ff",
    "ip_address": "192.168.1.100",
    "schedule": {
      "enabled": false,
      "block_time": "22:00",
      "unblock_time": "07:00"
    }
  }
}
```

**Fields:**
- Device name: Friendly name for the device
- `mac`: MAC address in `aa:bb:cc:dd:ee:ff` format
- `ip_address`: (Optional) IP address for ping verification
- `schedule`: (Optional) Schedule configuration
  - `enabled`: Boolean - whether schedule is active
  - `block_time`: Time in `HH:MM` format (24-hour)
  - `unblock_time`: Time in `HH:MM` format (24-hour)

**Example with multiple devices:**
```json
{
  "Laptop": {
    "mac": "aa:bb:cc:dd:ee:ff",
    "ip_address": "192.168.1.100",
    "schedule": {
      "enabled": true,
      "block_time": "22:00",
      "unblock_time": "07:00"
    }
  },
  "Phone": {
    "mac": "11:22:33:44:55:66",
    "ip_address": "192.168.1.101",
    "schedule": {
      "enabled": false
    }
  }
}
```

## Step 5: Verify Setup

### 5.1 Test Configuration Loading

```bash
python -c "import json; print(json.load(open('config.json')))"
```

Should output your config without errors.

### 5.2 Test Dependencies

```bash
python -c "import pyunifi, nicegui; print('Dependencies OK')"
```

Should output "Dependencies OK" without errors.

## Step 6: Run the Application

### Development Mode

**Basic run:**
```bash
python unifi-access-control.py
```

**With debug logging:**
```bash
DEBUG_MODE=true python unifi-access-control.py
```

**With output logging:**
```bash
python unifi-access-control.py > app.log 2>&1 &
tail -f app.log
```

**Using restart script (macOS/Linux):**
```bash
chmod +x restart-local.sh
./restart-local.sh
```

The application will be available at `http://localhost:8080`

### Expected Startup Output

```
[PERSISTENCE] Loaded persistence file
[SCHEDULE] Background schedule checker starting...
Connected to UniFi controller at 192.168.0.5
```

## Step 7: Verify Functionality

### 7.1 Check Connection Status

- Open `http://localhost:8080` in a browser
- Check top of page for connection status indicator
- Should show "🟢 Connected" if working

### 7.2 Test Manual Toggle

- Find a device in the UI
- Toggle the switch to enable/disable
- Check event log for confirmation

### 7.3 Test Schedule (if configured)

- Enable a schedule for a device
- Wait for scheduled time
- Check event log for scheduled actions
- Check that background thread is logging schedule checks

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'pyunifi'`

**Solution:**
```bash
source venv/bin/activate  # Make sure venv is activated
pip install -r requirements.txt
```

### Connection Errors

**Problem:** Cannot connect to UniFi controller

**Checklist:**
1. Verify `config.json` has correct credentials
2. Verify controller IP address is accessible: `ping <controller_ip>`
3. Check if controller requires HTTPS (modify code if needed)
4. Check firewall rules

### Port Already in Use

**Problem:** `Address already in use` on port 8080

**Solution:**
1. Find process using port: `lsof -i :8080` (macOS/Linux)
2. Kill process: `kill -9 <PID>`
3. Or change port in code: `ui.run(dark=True, port=8081)`

### Schedule Not Working

**Checklist:**
1. Verify schedule is enabled in UI
2. Check background thread is running (look for `[SCHEDULE]` logs)
3. Verify time format is correct (`HH:MM`)
4. Check event log for schedule actions

### Permission Errors

**Problem:** Cannot write to `device_state.json`

**Solution:**
```bash
chmod 755 .  # Ensure directory is writable
touch device_state.json  # Create file if it doesn't exist
chmod 644 device_state.json  # Make it writable
```

## Development Workflow

### Making Changes

1. **Edit code:** Make changes to `unifi-access-control.py`
2. **Test locally:** Run with debug mode enabled
3. **Check logs:** Monitor output for errors
4. **Test UI:** Verify changes in browser
5. **Commit:** `git add . && git commit -m "Description"`

### Debugging

**Enable debug mode:**
```bash
DEBUG_MODE=true python unifi-access-control.py
```

**Watch logs in real-time:**
```bash
tail -f /tmp/unifi-app.log
```

**Check background thread:**
Look for `[SCHEDULE]` and `[PERSISTENCE]` log messages

### Testing Schedule Logic

**Manual test:**
1. Set schedule to current time ± 1 minute
2. Enable schedule
3. Wait and observe logs
4. Check event log for action

**Test midnight-spanning:**
1. Set `unblock_time` > `block_time` (e.g., 23:00 unblock, 02:00 block)
2. Verify correct behavior across midnight

### Code Structure

- **Main file:** `unifi-access-control.py` (~1446 lines)
- **Functions organized by:**
  - Configuration loading (lines ~21-33)
  - Persistence (lines ~87-221)
  - UI building (lines ~850+)
  - API interaction (lines ~250-475)
  - Schedule checking (lines ~742-880)
  - Background threading (lines ~223-240)

## Production Deployment

See `SYSTEMD_SETUP.md` for production deployment instructions.

## Additional Resources

- **Technical Spec:** See `TECHNICAL_SPEC.md`
- **Main README:** See `README.md`
- **Systemd Setup:** See `SYSTEMD_SETUP.md`

---

**Last Updated:** 2026-01-07

