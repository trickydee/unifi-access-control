# UniFi Access Control - Technical Specification

## Project Overview

**Project Name:** UniFi Access Control  
**Version:** 4.0.7  
**Purpose:** Web-based control panel for managing device access on Ubiquiti UniFi networks  
**Technology Stack:** Python 3.9+, NiceGUI (web framework), PyUniFi (UniFi API client)

## Architecture Overview

### Core Components

1. **Main Application (`unifi-access-control.py`)**
   - Single-file application (~1446 lines)
   - Combines web UI, API integration, scheduling, and persistence
   - Uses NiceGUI for reactive web interface
   - Uses PyUniFi for UniFi Controller API interaction

2. **Configuration Files**
   - `config.json`: UniFi controller credentials and settings
   - `devices.json`: Device definitions (MAC addresses, schedules, IP addresses)
   - `device_state.json`: Runtime state persistence (auto-managed)

3. **Background Threading**
   - Independent schedule checker thread (runs every 10 seconds)
   - UI timers for temporary access checks and status updates
   - Separate from web server lifecycle

### Key Technical Decisions

#### 1. Single-File Application
- **Rationale:** Simplicity, easy deployment, no complex module structure
- **Trade-off:** Larger file, but clear logical separation via functions

#### 2. Background Threading for Schedules
- **Critical Decision:** Schedule checks run in a daemon thread, independent of UI
- **Rationale:** Schedules must work even without active browser connections
- **Implementation:** `threading.Thread` with daemon=True, checks every 10 seconds
- **Thread Safety:** Uses file-based locking via JSON writes, global state variables

#### 3. State Persistence
- **Approach:** JSON file-based persistence (`device_state.json`)
- **Persisted Data:**
  - Temporary access timers (with expiration times)
  - Device state history (last enabled/disabled timestamps)
  - Manual overrides (devices manually toggled)
  - Event log (last 100 events)
- **Persistence Frequency:** On every state change

#### 4. Rate Limiting & Caching
- **Problem:** UniFi API rate limiting (429 errors)
- **Solution:** 
  - Status caching (30 second cache duration)
  - Exponential backoff on rate limit errors (60s, 120s, 240s max)
  - Automatic reconnection after backoff period
  - Force refresh only when cache is stale (>30 seconds)

#### 5. Manual Override Persistence
- **Behavior:** Manual toggles persist until next scheduled event or temporary access expires
- **Implementation:** `manual_overrides` dict stores device override state
- **Clear Logic:** Override cleared when schedule successfully takes action (`is_manual=False`)

#### 6. Schedule Logic
- **Midnight-Spanning Support:** Handles schedules that cross midnight
- **Two Cases:**
  1. `unblock_time > block_time`: Unblocked period spans midnight
  2. `unblock_time < block_time`: Blocked period spans midnight
- **Check Frequency:** Every 10 seconds in background thread

#### 7. Ping Verification
- **Purpose:** Verify block/enable actions actually worked
- **Implementation:** Cross-platform ICMP ping (subprocess)
- **Timing:** Configurable delay (default 10 seconds) after action
- **Threading:** Uses `threading.Timer` or `ui.timer()` with fallback

#### 8. UI Synchronization
- **Problem:** Multiple browser instances don't reflect changes
- **Solution:** Periodic `devices.json` reload in UI (every 30 seconds)
- **Background Thread:** Also reloads `devices.json` during schedule checks

## Technical Constraints

### Dependencies
```
pyunifi>=2.21
nicegui>=3.4.1
```

### Python Version
- **Minimum:** Python 3.9
- **Tested On:** Python 3.9+

### Operating System
- **Tested:** macOS, Linux (systemd)
- **Windows:** Should work, but systemd service file not applicable

### Network Requirements
- Access to UniFi Controller API (HTTP/HTTPS)
- ICMP ping capability (for verification)
- Port 8080 available (default, configurable)

### File System
- Write access to application directory (for JSON persistence)
- Read access to `config.json` and `devices.json`
- Write access for `device_state.json`

## Data Flow

### Device Status Check Flow
```
UI/Background Thread
  ↓
get_blocked(force_refresh)
  ↓
Check rate limit → If limited, return cached data
  ↓
Check cache validity → If fresh, return cached data
  ↓
Connect to UniFi Controller (if needed)
  ↓
Get blocked MAC addresses from controller
  ↓
Map to friendly names
  ↓
Update cache
  ↓
Return device status map
```

### Schedule Check Flow (Background Thread)
```
background_schedule_checker() [every 10 seconds]
  ↓
Load devices.json (reload for sync)
  ↓
check_schedules()
  ↓
For each device with enabled schedule:
  ├─ Skip if temporary access active
  ├─ Get current status (cached or fresh)
  ├─ Calculate should_be_blocked based on time
  ├─ Compare with current status
  └─ If mismatch: call turn_on() or turn_off()
     ├─ UniFi API call
     ├─ Clear manual override if is_manual=False
     ├─ Update UI switch (if UI active)
     ├─ Schedule ping verification
     └─ Log event
```

### Manual Toggle Flow
```
UI Switch Toggle
  ↓
Switch handler
  ↓
Check current status
  ↓
If enabling: turn_on(friendly_name, mac, is_manual=True)
If disabling: turn_off(friendly_name, mac, is_manual=True)
  ↓
UniFi API call
  ↓
Set manual override
  ↓
Update UI
  ↓
Schedule ping verification
  ↓
Log event
```

## Error Handling

### API Errors
- **Rate Limiting (429):** Exponential backoff, retry with cached data
- **Connection Errors:** Automatic reconnection on next attempt
- **Authentication Errors:** Logged, UI shows connection status

### File Errors
- **Missing config.json:** Application won't start
- **Missing devices.json:** Application won't start
- **Missing device_state.json:** Created on first use
- **Read/Write Errors:** Logged, application continues

### Thread Safety
- **JSON Writes:** File-based locking via atomic write operations
- **Global State:** Mostly read-only, writes are infrequent
- **UI Updates:** NiceGUI handles WebSocket synchronization

## Performance Characteristics

### Resource Usage
- **Memory:** ~50-100MB (Python + dependencies)
- **CPU:** Low (mostly idle, periodic checks)
- **Network:** Minimal (API calls cached, background checks every 10s)

### Scalability
- **Device Limit:** Tested with ~20 devices, should scale to 100+
- **API Rate Limits:** Primary constraint (handled via caching/backoff)
- **UI Connections:** Multiple browser tabs supported

## Security Considerations

### Credentials Storage
- **config.json:** Contains UniFi username/password
- **Git Ignored:** Not committed to repository
- **Recommendation:** Use environment variables or secrets management in production

### Network Security
- **UniFi Controller:** Should use HTTPS in production
- **Web UI:** No authentication (assumes trusted network)
- **Recommendation:** Add authentication or use reverse proxy with auth

### File Permissions
- **config.json:** Should be readable only by application user
- **Recommendation:** `chmod 600 config.json`

## Deployment Considerations

### Development
- **Local Testing:** `python unifi-access-control.py`
- **With Logging:** `./restart-local.sh` or `DEBUG_MODE=true python unifi-access-control.py`

### Production
- **Systemd Service:** `unifi-access-control.service`
- **Process Management:** Automatic restart on failure
- **Logging:** Systemd journal or file-based logs
- **Debug Mode:** Configurable via environment variable

### Monitoring
- **Logs:** Check systemd journal or log files
- **Event Log:** View in UI (last 100 events)
- **Connection Status:** Shown in UI
- **Schedule Status:** Logged during checks

## Known Limitations

1. **No Authentication:** UI is open to anyone on network
2. **Single Controller:** Supports one UniFi controller at a time
3. **IP Address Changes:** Static IP addresses assumed for ping verification
4. **Event Log Size:** Limited to 100 events (older events lost)
5. **No Backup:** No automatic backup of device_state.json

## Future Enhancement Possibilities

1. **Authentication:** Add user authentication to UI
2. **Multi-Controller:** Support multiple UniFi controllers
3. **Database:** Replace JSON with SQLite or PostgreSQL
4. **API:** REST API for programmatic control
5. **Notifications:** Email/SMS alerts for events
6. **Backup:** Automatic backup of state files
7. **Dashboard:** Historical analytics and charts
8. **Groups:** Device groups for bulk operations

## Development Notes

### Code Structure
- **Functions:** Organized by responsibility (UI, API, persistence, scheduling)
- **Global State:** Used for controller connection, cached status, overrides
- **No Classes:** Procedural style for simplicity

### Testing Considerations
- **Manual Testing:** Primary testing method
- **Mock Controller:** Could mock PyUniFi for unit tests
- **Integration Tests:** Would require UniFi controller instance

### Debugging
- **DEBUG_MODE:** Set via environment variable or code
- **Logging:** Print statements for key events
- **Event Log:** UI-based event history
- **Schedule Logs:** Detailed logging of schedule checks

## Migration Notes

### Upgrading from Previous Versions
- **State File:** Automatically migrated (backward compatible)
- **Config File:** May need new fields (verification_delay)
- **Devices File:** May need new fields (ip_address)

### Starting Development on New Instance

1. **Clone Repository:**
   ```bash
   git clone <repository-url>
   cd unifi-access-control
   ```

2. **Create Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create Configuration:**
   - Copy `config.json` template
   - Add UniFi controller credentials
   - Add devices to `devices.json`

5. **Run Application:**
   ```bash
   python unifi-access-control.py
   ```

6. **For Production:**
   - Follow `SYSTEMD_SETUP.md` guide
   - Configure systemd service file
   - Set up log rotation if needed

## Critical Code Sections

### Background Schedule Thread (Lines ~223-240)
- **Location:** `background_schedule_checker()`
- **Purpose:** Independent schedule checking
- **Critical:** Must not block on UI operations

### Schedule Check Logic (Lines ~742-880)
- **Location:** `check_schedules()`
- **Purpose:** Evaluate and apply schedules
- **Critical:** Handles midnight-spanning schedules correctly

### Manual Override Clearing (Lines ~555-622, ~837)
- **Location:** `turn_off()` when `is_manual=False`
- **Purpose:** Clear manual overrides on scheduled actions
- **Critical:** Prevents manual overrides from blocking schedules

### Rate Limiting (Lines ~396-475)
- **Location:** `get_blocked()`
- **Purpose:** Handle API rate limits gracefully
- **Critical:** Prevents excessive API calls and errors

### UI Timer Fallback (Lines ~593-620, ~518-537)
- **Location:** `turn_on()` and `turn_off()` verification scheduling
- **Purpose:** Handle `ui.timer()` from background thread
- **Critical:** Allows ping verification to work from background thread

---

**Last Updated:** 2026-01-07  
**Version:** 4.0.7

