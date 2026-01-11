import json
from datetime import datetime, timedelta
from pyunifi.controller import Controller
from nicegui import app, ui
from nicegui.events import ValueChangeEventArguments
import os
import subprocess
import platform
import threading
import time

# Logging configuration
# Can be set via environment variable DEBUG_MODE=true
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'

def debug_log(message):
    """Only log if DEBUG_MODE is enabled"""
    if DEBUG_MODE:
        print(message)

# Load configuration
def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

def load_devices():
    with open('devices.json', 'r') as f:
        return json.load(f)

def save_devices(devices):
    with open('devices.json', 'w') as f:
        json.dump(devices, f, indent=2)

def toggle_schedule(friendly_name):
    """Toggle schedule enabled/disabled for a device"""
    if friendly_name in devices_config:
        schedule = devices_config[friendly_name].get("schedule", {})
        current_enabled = schedule.get("enabled", False)
        devices_config[friendly_name]["schedule"]["enabled"] = not current_enabled
        save_devices(devices_config)
        print(f"[SCHEDULE] {'Enabled' if not current_enabled else 'Disabled'} schedule for {friendly_name}")
        return not current_enabled
    return False

def update_schedule_times(friendly_name, block_time_str, unblock_time_str):
    """Update schedule times for a device"""
    if friendly_name in devices_config:
        if "schedule" not in devices_config[friendly_name]:
            devices_config[friendly_name]["schedule"] = {}
        devices_config[friendly_name]["schedule"]["block_time"] = block_time_str
        devices_config[friendly_name]["schedule"]["unblock_time"] = unblock_time_str
        devices_config[friendly_name]["schedule"]["enabled"] = True
        save_devices(devices_config)
        print(f"[SCHEDULE] Updated schedule for {friendly_name}: {unblock_time_str} - {block_time_str}")
        # Update UI
        update_schedule_display(friendly_name)
        return True
    return False

def update_schedule_display(friendly_name):
    """Update the schedule label and button in the UI"""
    if friendly_name in devices_config:
        schedule = devices_config[friendly_name].get("schedule", {})
        schedule_enabled = schedule.get("enabled", False)
        
        # Update schedule label
        if friendly_name in schedule_labels and schedule_labels[friendly_name]:
            if schedule_enabled:
                block_time = schedule.get("block_time", "N/A")
                unblock_time = schedule.get("unblock_time", "N/A")
                schedule_labels[friendly_name].text = f"📅 Schedule: {unblock_time} - {block_time}"
                schedule_labels[friendly_name].style('display: block')
            else:
                schedule_labels[friendly_name].text = "📅 Schedule Disabled"
                schedule_labels[friendly_name].style('display: block')
        
        # Update schedule button color
        if friendly_name in schedule_buttons and schedule_buttons[friendly_name]:
            if schedule_enabled:
                schedule_buttons[friendly_name].classes('bg-blue-500 text-white', remove='bg-gray-500')
            else:
                schedule_buttons[friendly_name].classes('bg-gray-500 text-white', remove='bg-blue-500')

# Persistence for temporary access and device state
PERSISTENCE_FILE = 'device_state.json'

def load_persistence():
    """Load temporary access and device state history from file"""
    global temporary_access, device_state_history, manual_overrides, event_log
    # Initialize if not already initialized
    if 'temporary_access' not in globals():
        temporary_access = {}
    if 'device_state_history' not in globals():
        device_state_history = {}
    if 'manual_overrides' not in globals():
        manual_overrides = {}
    if 'event_log' not in globals():
        event_log = []
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, 'r') as f:
                data = json.load(f)
                # Convert datetime strings back to datetime objects
                if 'temporary_access' in data:
                    restored_count = 0
                    for name, time_str in data['temporary_access'].items():
                        try:
                            temp_time = datetime.fromisoformat(time_str)
                            # Only restore if it's in the future
                            if temp_time > datetime.now():
                                temporary_access[name] = temp_time
                                restored_count += 1
                                print(f"[PERSISTENCE] Restored temporary access for {name}, expires at {temp_time.strftime('%H:%M:%S')}")
                            else:
                                print(f"[PERSISTENCE] Skipped expired temporary access for {name}")
                        except Exception as e:
                            print(f"[PERSISTENCE] Error restoring temporary access for {name}: {e}")
                    if restored_count > 0:
                        print(f"[PERSISTENCE] Restored {restored_count} active temporary access timers")
                if 'device_state_history' in data:
                    restored_history_count = 0
                    for name, history in data['device_state_history'].items():
                        device_state_history[name] = {}
                        if 'last_enabled' in history and history['last_enabled']:
                            try:
                                device_state_history[name]['last_enabled'] = datetime.fromisoformat(history['last_enabled'])
                                restored_history_count += 1
                            except Exception as e:
                                print(f"[PERSISTENCE] Error restoring enabled time for {name}: {e}")
                        if 'last_disabled' in history and history['last_disabled']:
                            try:
                                device_state_history[name]['last_disabled'] = datetime.fromisoformat(history['last_disabled'])
                                restored_history_count += 1
                            except Exception as e:
                                print(f"[PERSISTENCE] Error restoring disabled time for {name}: {e}")
                    if restored_history_count > 0:
                        print(f"[PERSISTENCE] Restored state history for {len(device_state_history)} devices")
                # Load manual overrides
                if 'manual_overrides' in data:
                    manual_overrides.update(data['manual_overrides'])
                    if len(data['manual_overrides']) > 0:
                        print(f"[PERSISTENCE] Restored {len(data['manual_overrides'])} manual overrides")
                # Load event log
                if 'event_log' in data:
                    event_log.clear()
                    for event in data['event_log']:
                        try:
                            event['timestamp'] = datetime.fromisoformat(event['timestamp'])
                            event_log.append(event)
                        except Exception as e:
                            print(f"[PERSISTENCE] Error restoring event: {e}")
                    if len(data['event_log']) > 0:
                        print(f"[PERSISTENCE] Restored {len(data['event_log'])} events from log")
        except Exception as e:
            print(f"Error loading persistence: {e}")

def save_persistence():
    """Save temporary access and device state history to file"""
    try:
        data = {
            'temporary_access': {
                name: time.isoformat() 
                for name, time in temporary_access.items()
            },
            'device_state_history': {
                name: {
                    'last_enabled': history.get('last_enabled').isoformat() if history.get('last_enabled') else None,
                    'last_disabled': history.get('last_disabled').isoformat() if history.get('last_disabled') else None
                }
                for name, history in device_state_history.items()
            },
            'manual_overrides': manual_overrides.copy(),
            'event_log': [
                {
                    'timestamp': event['timestamp'].isoformat(),
                    'device': event['device'],
                    'event': event['event'],
                    'details': event.get('details', '')
                }
                for event in event_log[-100:]  # Keep last 100 events
            ]
        }
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[PERSISTENCE] Saved {len(temporary_access)} temporary access timers and state history for {len(device_state_history)} devices")
    except Exception as e:
        print(f"[PERSISTENCE] Error saving persistence: {e}")

config = load_config()
devices_config = load_devices()

unifi_username = config['unifi_username']
unifi_password = config['unifi_password']
unifi_controller = config['unifi_controller']
# Optional: verification delay in seconds (default 10)
VERIFICATION_DELAY = config.get('verification_delay', 10)
# Optional: number of pings to perform during verification (default 5)
RECOVERY_PING_COUNT = config.get('recovery_ping_count', 5)

# Track consecutive ping failures for recovery mechanism
# Only tracks failures when device should be online but is offline
ping_failure_count = {}  # Device name -> consecutive failure count

# Store switch references and temporary access timers
switches = {}
temporary_access = {}  # {device_name: datetime when it should be blocked again}
schedule_timers = {}  # Track scheduled block/unblock timers
status_label_ref = [None]  # Will be set when UI is built (using list for mutable reference)
device_state_history = {}  # {device_name: {"last_enabled": datetime, "last_disabled": datetime}}
event_log = []  # List of events: [{"timestamp": datetime, "device": str, "event": str, "details": str}, ...]
countdown_labels = {}  # {device_name: ui.label} for countdown display
enabled_labels = {}  # {device_name: ui.label} for enabled time display
disabled_labels = {}  # {device_name: ui.label} for disabled time display
schedule_labels = {}  # {device_name: ui.label} for schedule display
schedule_buttons = {}  # {device_name: ui.button} for schedule button references
status_chips = {}  # {device_name: ui.chip} for online status display
_programmatic_switch_update = set()  # Track devices being updated programmatically to prevent handler clearing temporary_access
manual_overrides = {}  # {device_name: True/False} - tracks manual toggle state (True=enabled, False=disabled)

load_persistence()  # Load persisted state on startup (after variables are initialized)

# Initialize controller as None - will be created lazily
c = None

# Global flag to control background thread
_schedule_thread_running = True
_schedule_thread_lock = threading.Lock()

def background_schedule_checker():
    """Background thread that checks schedules independently of browser connections"""
    global _schedule_thread_running, devices_config
    while _schedule_thread_running:
        try:
            # Reload devices.json periodically to pick up changes from other UI instances
            try:
                with _schedule_thread_lock:
                    new_devices_config = load_devices()
                    # Only update if file has actually changed (simple check)
                    if new_devices_config != devices_config:
                        devices_config = new_devices_config
                        print(f"[SCHEDULE] Reloaded devices.json - detected changes")
            except Exception as e:
                print(f"[SCHEDULE] Error reloading devices.json: {e}")
            
            # Check schedules
            check_schedules()
        except Exception as e:
            print(f"[SCHEDULE] Error in background schedule checker: {e}")
        
        # Sleep for 10 seconds before next check
        time.sleep(10)

# Start background thread for schedule checks (runs independently of browser connections)
schedule_thread = threading.Thread(target=background_schedule_checker, daemon=True)
schedule_thread.start()
print("[SCHEDULE] Background schedule checker thread started")

# Rate limiting and caching
last_api_call = None
rate_limit_until = None  # datetime when we can make API calls again
cached_device_status = None  # Cache the last known device status
cache_valid_until = None  # When the cache expires
MIN_API_INTERVAL = 5  # Minimum seconds between API calls
CACHE_DURATION = 30  # Cache device status for 30 seconds

def check_rate_limit():
    """Check if we're rate limited and should wait"""
    global rate_limit_until
    if rate_limit_until and datetime.now() < rate_limit_until:
        remaining = (rate_limit_until - datetime.now()).total_seconds()
        # Only log rate limit status every 10 seconds to reduce verbosity
        if not hasattr(check_rate_limit, '_last_log_time') or \
           (datetime.now() - check_rate_limit._last_log_time).total_seconds() >= 10:
            debug_log(f"Rate limited, waiting {int(remaining)} more seconds...")
            check_rate_limit._last_log_time = datetime.now()
        return True
    return False

def ensure_controller():
    """Ensure controller is connected, create if needed"""
    global c, rate_limit_until
    if check_rate_limit():
        return False
    if c is None:
        try:
            c = Controller(unifi_controller, unifi_username, unifi_password, ssl_verify=False, version='UDMP-unifiOS')
            print("Connected to controller.")
            return True
        except Exception as e:
            error_str = str(e)
            # Check for rate limit error (429)
            if '429' in error_str or 'rate limit' in error_str.lower():
                print("Rate limited by UniFi controller, backing off for 60 seconds...")
                rate_limit_until = datetime.now() + timedelta(seconds=60)
                c = None
            else:
                print(f"Failed to connect to controller: {e}")
            return False
    return True

def reconnect_controller():
    global c, rate_limit_until
    if check_rate_limit():
        return False
    try:
        c = Controller(unifi_controller, unifi_username, unifi_password, ssl_verify=False, version='UDMP-unifiOS')
        print("Reconnected to controller.")
        rate_limit_until = None  # Clear rate limit on successful reconnect
        return True
    except Exception as e:
        error_str = str(e)
        if '429' in error_str or 'rate limit' in error_str.lower():
            print("Rate limited during reconnect, backing off...")
            rate_limit_until = datetime.now() + timedelta(seconds=60)
        else:
            print(f"Failed to reconnect: {e}")
        c = None
        return False

def ping_device(ip_address, count=2, timeout=2):
    """
    Ping a device to check if it's online
    Returns True if device responds, False otherwise, None on error
    """
    if not ip_address:
        return None  # No IP address configured
    
    try:
        # Determine ping command based on OS
        if platform.system().lower() == 'windows':
            cmd = ['ping', '-n', str(count), '-w', str(timeout * 1000), ip_address]
        else:
            cmd = ['ping', '-c', str(count), '-W', str(timeout), ip_address]
        
        # Run ping command
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout * count + 2
        )
        
        # Check if ping was successful (exit code 0 means success)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        print(f"[VERIFY] Error pinging {ip_address}: {e}")
        return None

def verify_device_state(friendly_name, expected_blocked):
    """
    Verify that a device's actual state matches the expected state by pinging it
    expected_blocked: True if device should be blocked (offline), False if should be enabled (online)
    """
    global ping_failure_count
    
    if friendly_name not in devices_config:
        return
    
    device_info = devices_config[friendly_name]
    ip_address = device_info.get("ip_address")
    
    if not ip_address:
        debug_log(f"[VERIFY] {friendly_name}: No IP address configured, skipping verification")
        return
    
    # Ping the device multiple times to check responsiveness (configurable)
    ping_results = []
    for i in range(RECOVERY_PING_COUNT):
        is_online = ping_device(ip_address, count=1, timeout=2)
        ping_results.append(is_online)
        if i < RECOVERY_PING_COUNT - 1:  # Don't sleep after last ping
            time.sleep(1)  # 1 second between pings
    
    # Count successful pings (True values, ignoring None/errors)
    successful_pings = sum(1 for result in ping_results if result is True)
    failed_pings = sum(1 for result in ping_results if result is False)
    
    # Determine if device is online based on ping results
    # Device is considered online if at least 1 ping succeeds (device is responsive)
    # Device is considered offline if all pings fail
    if successful_pings == 0 and failed_pings == 0:
        # All pings returned None (errors) - can't determine status
        print(f"[VERIFY] {friendly_name}: Could not ping {ip_address} (error on all attempts)")
        return
    
    is_online = successful_pings > 0
    
    # Verify state matches expectation
    # If expected_blocked=True, device should be offline (ping fails)
    # If expected_blocked=False, device should be online (ping succeeds)
    state_matches = (is_online == (not expected_blocked))
    
    if state_matches:
        # Verification passed - reset failure counter
        if friendly_name in ping_failure_count:
            del ping_failure_count[friendly_name]
        status = "blocked (offline)" if expected_blocked else "enabled (online)"
        print(f"[VERIFY] ✓ {friendly_name}: Verification passed - device is {status} as expected ({successful_pings}/{RECOVERY_PING_COUNT} pings successful)")
        add_event_log(friendly_name, 'Verification Passed', f'Device is {"offline" if expected_blocked else "online"} as expected ({successful_pings}/{RECOVERY_PING_COUNT} pings successful)')
    else:
        status_expected = "offline" if expected_blocked else "online"
        status_actual = "online" if is_online else "offline"
        print(f"[VERIFY] ✗ {friendly_name}: Verification FAILED - expected {status_expected}, but device is {status_actual} ({successful_pings}/{RECOVERY_PING_COUNT} pings successful, {failed_pings}/{RECOVERY_PING_COUNT} failed)")
        
        # Only track failures when device should be online but is offline
        if not expected_blocked and not is_online:
            # Device should be online but is offline
            # If all pings failed in this verification check, trigger recovery immediately
            if failed_pings >= RECOVERY_PING_COUNT:
                # All pings failed - device is completely unresponsive, trigger recovery
                print(f"[VERIFY] {friendly_name}: Device unresponsive after {RECOVERY_PING_COUNT} pings (all failed) - triggering recovery (disable/enable cycle)")
                add_event_log(friendly_name, 'Verification Failed', f'Device unresponsive after {RECOVERY_PING_COUNT} pings (all {failed_pings}/{RECOVERY_PING_COUNT} pings failed) - triggering recovery')
                
                # Trigger recovery: disable then enable
                mac_address = device_info.get("mac")
                if mac_address:
                    # First, disable the device
                    print(f"[RECOVERY] {friendly_name}: Disabling device for recovery...")
                    if turn_off(friendly_name, mac_address, is_manual=False):
                        # Schedule enable after 5 seconds
                        def recovery_enable():
                            print(f"[RECOVERY] {friendly_name}: Re-enabling device after recovery disable...")
                            if turn_on(friendly_name, mac_address, is_manual=False):
                                # Reset failure counter after recovery cycle completes successfully
                                if friendly_name in ping_failure_count:
                                    del ping_failure_count[friendly_name]
                                    print(f"[RECOVERY] {friendly_name}: Reset ping failure counter after successful recovery")
                                
                                add_event_log(friendly_name, 'Resent Enable as device unresponsive', f'Device was unresponsive after {RECOVERY_PING_COUNT} pings - recovery cycle completed')
                                print(f"[RECOVERY] {friendly_name}: Recovery cycle completed - device re-enabled")
                                # Schedule another verification after delay to check if recovery worked
                                def verify_after_recovery():
                                    verify_device_state(friendly_name, expected_blocked=False)
                                try:
                                    ui.timer(VERIFICATION_DELAY + 5, verify_after_recovery, once=True)
                                except:
                                    timer = threading.Timer(VERIFICATION_DELAY + 5, verify_after_recovery)
                                    timer.daemon = True
                                    timer.start()
                            else:
                                print(f"[RECOVERY] {friendly_name}: Failed to re-enable device after recovery")
                                add_event_log(friendly_name, 'Recovery Failed', 'Failed to re-enable device after recovery disable')
                                # Keep failure counter since recovery failed
                        
                        try:
                            ui.timer(5.0, recovery_enable, once=True)
                        except:
                            timer = threading.Timer(5.0, recovery_enable)
                            timer.daemon = True
                            timer.start()
                    else:
                        print(f"[RECOVERY] {friendly_name}: Failed to disable device for recovery")
                        add_event_log(friendly_name, 'Recovery Failed', 'Failed to disable device for recovery')
                else:
                    print(f"[RECOVERY] {friendly_name}: Cannot trigger recovery - MAC address not found")
            else:
                # Some pings failed but not all - just log the failure
                # Track consecutive failures for monitoring
                ping_failure_count[friendly_name] = ping_failure_count.get(friendly_name, 0) + 1
                failure_count = ping_failure_count[friendly_name]
                add_event_log(friendly_name, 'Verification Failed', f'Expected {status_expected}, but device is {status_actual} ({failed_pings}/{RECOVERY_PING_COUNT} pings failed, {failure_count} consecutive verification failures)')
        else:
            # Other type of verification failure (should be offline but is online) - reset counter
            if friendly_name in ping_failure_count:
                del ping_failure_count[friendly_name]
            add_event_log(friendly_name, 'Verification Failed', f'Expected {status_expected}, but device is {status_actual} ({successful_pings}/{RECOVERY_PING_COUNT} pings successful)')

def add_event_log(device, event_type, details=""):
    """Add an event to the event log"""
    global event_log
    event_log.append({
        'timestamp': datetime.now(),
        'device': device,
        'event': event_type,
        'details': details
    })
    # Keep log size manageable
    if len(event_log) > 100:
        event_log.pop(0)  # Remove oldest event
    save_persistence()  # Save log immediately

def get_blocked(force_refresh=False):
    """Get blocked device status, using cache if available"""
    global cached_device_status, cache_valid_until, last_api_call, rate_limit_until, c
    
    # Check cache first (unless forced refresh)
    now = datetime.now()
    if not force_refresh and cached_device_status and cache_valid_until and now < cache_valid_until:
        return cached_device_status
    
    # Check rate limit
    if check_rate_limit():
        # Return cached data if available, even if expired
        if cached_device_status:
            return cached_device_status
        # Otherwise return default
        return {
            name: {
                "mac": info["mac"],
                "blocked": False
            }
            for name, info in devices_config.items()
        }
    
    # Check minimum interval between API calls
    if last_api_call:
        time_since_last = (now - last_api_call).total_seconds()
        if time_since_last < MIN_API_INTERVAL:
            # Use cache if available
            if cached_device_status:
                return cached_device_status
    
    if not ensure_controller() or c is None:
        # Return cached or default state if controller not available
        if cached_device_status:
            return cached_device_status
        return {
            name: {
                "mac": info["mac"],
                "blocked": False
            }
            for name, info in devices_config.items()
        }
    
    try:
        last_api_call = datetime.now()
        if c is None:
            raise Exception("Controller not initialized")
        clients = c.get_users()
        blocked_macs = {client.get("mac") for client in clients if client.get("blocked")}
        result = {
            name: {
                "mac": info["mac"],
                "blocked": info["mac"] in blocked_macs
            }
            for name, info in devices_config.items()
        }
        # Update cache
        cached_device_status = result
        cache_valid_until = now + timedelta(seconds=CACHE_DURATION)
        return result
    except Exception as e:
        error_str = str(e)
        # Check for rate limit error (429)
        if '429' in error_str or 'rate limit' in error_str.lower() or 'APIError' in str(type(e)):
            print(f"Rate limited: {e}")
            # Set rate limit backoff (exponential: 60s, 120s, 240s max)
            if rate_limit_until:
                # Already rate limited, increase backoff
                current_backoff = (rate_limit_until - now).total_seconds()
                new_backoff = min(current_backoff * 2, 240)  # Max 4 minutes
            else:
                new_backoff = 60  # Start with 1 minute
            rate_limit_until = now + timedelta(seconds=new_backoff)
            c = None  # Force reconnect after backoff
        else:
            print(f"Error getting blocked status: {e}")
        
        # Return cached data if available
        if cached_device_status:
            return cached_device_status
        # Otherwise return default state on error
    return {
        name: {
                "mac": info["mac"],
                "blocked": False
            }
            for name, info in devices_config.items()
        }

def turn_on(friendly_name, mac_address, is_manual=True):
    global cached_device_status, cache_valid_until, rate_limit_until, c, device_state_history, manual_overrides
    if check_rate_limit():
        print(f"Rate limited, cannot unblock {friendly_name} right now")
        return False
    if not ensure_controller():
        print(f"Failed to unblock {friendly_name}: Controller not available")
        return False
    try:
        debug_log(f"Unblocking {friendly_name}...")
        c.unblock_client(mac_address)
        # Clear cache to force refresh on next call
        cached_device_status = None
        cache_valid_until = None
        # Clear any temporary access timer if manually unblocked
        # BUT: Don't clear if this was triggered programmatically (e.g., from turn_on_temporary)
        if friendly_name in temporary_access:
            if friendly_name in _programmatic_switch_update:
                debug_log(f"[DEBUG] turn_on: NOT clearing temporary_access for {friendly_name} (programmatic update)")
            else:
                debug_log(f"[DEBUG] turn_on: DELETING {friendly_name} from temporary_access (device was manually unblocked via switch)")
                del temporary_access[friendly_name]
                debug_log(f"[DEBUG] turn_on: temporary_access now has {len(temporary_access)} entries: {list(temporary_access.keys())}")
        # Record enable time
        if friendly_name not in device_state_history:
            device_state_history[friendly_name] = {}
        device_state_history[friendly_name]['last_enabled'] = datetime.now()
        
        # Add to event log (only if not a programmatic update from schedule/temporary access)
        # Programmatic updates are already logged by the schedule/temporary access functions
        if friendly_name not in _programmatic_switch_update:
            event_type = "Enabled (Manual)" if is_manual else "Enabled (Schedule)"
            add_event_log(friendly_name, event_type, '')
        
        # Track manual override if this was a manual action
        if is_manual and friendly_name not in _programmatic_switch_update:
            manual_overrides[friendly_name] = True  # Manual override: enabled
            debug_log(f"[MANUAL] Set manual override for {friendly_name}: enabled")
        elif not is_manual:
            # Schedule/temporary access is taking control, clear manual override
            if friendly_name in manual_overrides:
                del manual_overrides[friendly_name]
                debug_log(f"[MANUAL] Cleared manual override for {friendly_name} (schedule/temporary access taking control)")
        
        save_persistence()
        
        # Schedule verification after delay
        # Use threading.Timer for background thread safety, ui.timer for UI thread
        def verify_after_delay():
            verify_device_state(friendly_name, expected_blocked=False)
        try:
            # Try ui.timer first (works in UI context)
            ui.timer(VERIFICATION_DELAY, verify_after_delay, once=True)
        except:
            # Fallback to threading.Timer if ui.timer doesn't work (e.g., from background thread)
            timer = threading.Timer(VERIFICATION_DELAY, verify_after_delay)
            timer.daemon = True
            timer.start()
        
        return True
    except Exception as e:
        error_str = str(e)
        if '429' in error_str or 'rate limit' in error_str.lower():
            print(f"Rate limited while unblocking {friendly_name}")
            rate_limit_until = datetime.now() + timedelta(seconds=60)
            c = None
        else:
            print(f"Error unblocking {friendly_name}: {e}")
        return False

def turn_off(friendly_name, mac_address, is_manual=True):
    global cached_device_status, cache_valid_until, rate_limit_until, c, device_state_history, manual_overrides, event_log
    if check_rate_limit():
        print(f"Rate limited, cannot block {friendly_name} right now")
        return False
    if not ensure_controller():
        print(f"Failed to block {friendly_name}: Controller not available")
        return False
    try:
        # Check current device status BEFORE blocking to determine if we're actually changing state
        if friendly_name not in device_state_history:
            device_state_history[friendly_name] = {}
        
        # Get current device status from cache to check if it's already blocked
        device_map = get_blocked(force_refresh=False)
        device_info = device_map.get(friendly_name)
        was_already_blocked = device_info.get("blocked", False) if device_info else False
        
        debug_log(f"Blocking {friendly_name}...")
        c.block_client(mac_address)
        # Clear cache to force refresh on next call
        cached_device_status = None
        cache_valid_until = None
        
        # Clear any temporary access timer if manually blocked
        if friendly_name in temporary_access:
            debug_log(f"[DEBUG] turn_off: DELETING {friendly_name} from temporary_access (device was manually blocked)")
            del temporary_access[friendly_name]
            debug_log(f"[DEBUG] turn_off: temporary_access now has {len(temporary_access)} entries: {list(temporary_access.keys())}")
        
        # Only update last_disabled if device was NOT already blocked (we're transitioning from enabled to disabled)
        # OR if we don't have a last_disabled time yet (first time disabling this device)
        if not was_already_blocked or 'last_disabled' not in device_state_history[friendly_name] or not device_state_history[friendly_name]['last_disabled']:
            device_state_history[friendly_name]['last_disabled'] = datetime.now()
        # Otherwise, preserve the existing last_disabled time (device was already disabled, we're just re-applying the block)
        
        # Add to event log (only if not a programmatic update from schedule/temporary access)
        # Programmatic updates are already logged by the schedule/temporary access functions
        if friendly_name not in _programmatic_switch_update:
            event_type = "Disabled (Manual)" if is_manual else "Disabled (Schedule)"
            add_event_log(friendly_name, event_type, '')
        
        # Track manual override if this was a manual action
        if is_manual and friendly_name not in _programmatic_switch_update:
            manual_overrides[friendly_name] = False  # Manual override: disabled
            debug_log(f"[MANUAL] Set manual override for {friendly_name}: disabled")
        elif not is_manual:
            # Schedule/temporary access is taking control, clear manual override
            if friendly_name in manual_overrides:
                del manual_overrides[friendly_name]
                debug_log(f"[MANUAL] Cleared manual override for {friendly_name} (schedule/temporary access taking control)")
        
        save_persistence()
        
        # Schedule verification after delay
        # Use threading.Timer for background thread safety, ui.timer for UI thread
        def verify_after_delay():
            verify_device_state(friendly_name, expected_blocked=True)
        try:
            # Try ui.timer first (works in UI context)
            ui.timer(VERIFICATION_DELAY, verify_after_delay, once=True)
        except:
            # Fallback to threading.Timer if ui.timer doesn't work (e.g., from background thread)
            timer = threading.Timer(VERIFICATION_DELAY, verify_after_delay)
            timer.daemon = True
            timer.start()
        
        return True
    except Exception as e:
        error_str = str(e)
        if '429' in error_str or 'rate limit' in error_str.lower():
            print(f"Rate limited while blocking {friendly_name}")
            rate_limit_until = datetime.now() + timedelta(seconds=60)
            c = None
        else:
            print(f"Error blocking {friendly_name}: {e}")
        return False

def turn_on_temporary(friendly_name, mac_address, minutes):
    """Unblock a device temporarily for X minutes"""
    global cached_device_status, cache_valid_until, rate_limit_until, c, device_state_history, manual_overrides, event_log
    if check_rate_limit():
        print(f"Rate limited, cannot grant temporary access to {friendly_name} right now")
        return False
    if not ensure_controller():
        print(f"Failed to grant temporary access to {friendly_name}: Controller not available")
        return False
    try:
        debug_log(f"Unblocking {friendly_name} temporarily for {minutes} minutes")
        c.unblock_client(mac_address)
        # Clear cache to force refresh on next call
        cached_device_status = None
        cache_valid_until = None
        # Schedule auto-block
        block_time = datetime.now() + timedelta(minutes=minutes)
        temporary_access[friendly_name] = block_time
        debug_log(f"[DEBUG] turn_on_temporary: Set temporary_access[{friendly_name}] = {block_time}")
        debug_log(f"[DEBUG] turn_on_temporary: temporary_access dict now has {len(temporary_access)} entries: {list(temporary_access.keys())}")
        # Verify it was actually set
        if friendly_name not in temporary_access:
            debug_log(f"[DEBUG] turn_on_temporary: ERROR - {friendly_name} was NOT added to temporary_access!")
        else:
            debug_log(f"[DEBUG] turn_on_temporary: Verified {friendly_name} is in temporary_access: {temporary_access[friendly_name]}")
        
        # Record enable time
        if friendly_name not in device_state_history:
            device_state_history[friendly_name] = {}
        device_state_history[friendly_name]['last_enabled'] = datetime.now()
        
        # Add to event log
        add_event_log(friendly_name, 'Temporary Access Granted', f'{minutes} minutes (expires at {block_time.strftime("%H:%M:%S")})')
        
        # Clear manual override when temporary access is granted (temporary access takes priority)
        if friendly_name in manual_overrides:
            del manual_overrides[friendly_name]
            debug_log(f"[MANUAL] Cleared manual override for {friendly_name} (temporary access granted)")
        
        save_persistence()
        
        # Immediately update switch to enabled state (don't wait for controller refresh)
        # IMPORTANT: Mark this as programmatic update to prevent turn_on() from clearing temporary_access
        if friendly_name in switches:
            _programmatic_switch_update.add(friendly_name)
            switches[friendly_name].value = True
            debug_log(f"[DEBUG] turn_on_temporary: Set switch[{friendly_name}] to True (marked as programmatic)")
            # Remove from programmatic set after a short delay to allow handler to complete
            def clear_programmatic_flag():
                _programmatic_switch_update.discard(friendly_name)
                debug_log(f"[DEBUG] turn_on_temporary: Cleared programmatic flag for {friendly_name}")
            ui.timer(0.1, clear_programmatic_flag, once=True)
            # Verify temporary_access is still there
            if friendly_name not in temporary_access:
                debug_log(f"[DEBUG] turn_on_temporary: ERROR - {friendly_name} was REMOVED from temporary_access!")
                # Re-add it immediately
                temporary_access[friendly_name] = block_time
                debug_log(f"[DEBUG] turn_on_temporary: Re-added {friendly_name} to temporary_access")
            else:
                debug_log(f"[DEBUG] turn_on_temporary: Verified {friendly_name} still in temporary_access")
        else:
            debug_log(f"[DEBUG] turn_on_temporary: WARNING - switch[{friendly_name}] not found in switches dict")
        
        # Check if countdown label exists
        if friendly_name in countdown_labels:
            debug_log(f"[DEBUG] turn_on_temporary: countdown_labels[{friendly_name}] exists: {countdown_labels[friendly_name] is not None}")
        else:
            debug_log(f"[DEBUG] turn_on_temporary: WARNING - countdown_labels[{friendly_name}] NOT FOUND")
            debug_log(f"[DEBUG] turn_on_temporary: Available countdown_labels keys: {list(countdown_labels.keys())}")
        
        debug_log(f"[DEBUG] turn_on_temporary: Temporary access granted for {friendly_name}, will block at {block_time.strftime('%H:%M:%S')}")
        print(f"{friendly_name} will be blocked again at {block_time.strftime('%H:%M:%S')}")
        return True
    except Exception as e:
        error_str = str(e)
        if '429' in error_str or 'rate limit' in error_str.lower():
            print(f"Rate limited while granting temporary access to {friendly_name}")
            rate_limit_until = datetime.now() + timedelta(seconds=60)
            c = None
        else:
            print(f"Error granting temporary access to {friendly_name}: {e}")
        return False

def check_temporary_access():
    """Check if any temporary access periods have expired"""
    global temporary_access
    now = datetime.now()
    to_block = []
    for friendly_name, block_time in list(temporary_access.items()):
        if now >= block_time:
            to_block.append(friendly_name)
    
    for friendly_name in to_block:
        if friendly_name in devices_config:
            mac = devices_config[friendly_name]["mac"]
            print(f"Temporary access expired for {friendly_name}, blocking...")
            turn_off(friendly_name, mac)
            del temporary_access[friendly_name]
            save_persistence()  # Save after removing expired access
            # Update UI switch
            if friendly_name in switches:
                switches[friendly_name].value = False

def parse_time(time_str):
    """Parse time string (HH:MM) into datetime time object"""
    if not time_str:
        return None
    return datetime.strptime(time_str, "%H:%M").time()

def check_schedules():
    """Check and apply scheduled block/unblock times - called every second"""
    global devices_config
    now = datetime.now().time()
    
    for friendly_name, info in devices_config.items():
        schedule = info.get("schedule", {})
        if not schedule.get("enabled", False):
            continue
        
        block_time_str = schedule.get("block_time")
        unblock_time_str = schedule.get("unblock_time")
        
        if not block_time_str or not unblock_time_str:
            continue
        
        block_time = parse_time(block_time_str)
        unblock_time = parse_time(unblock_time_str)
        
        if not block_time or not unblock_time:
            continue
        
        mac = info["mac"]
        # Get current status from controller (but respect temporary access)
        # If device has temporary access, don't apply schedule
        if friendly_name in temporary_access:
            debug_log(f"[SCHEDULE] {friendly_name}: Skipping (temporary access active)")
            continue  # Skip schedule check if temporary access is active
        
        # Get current status - use cached data to avoid rate limiting
        # For schedule checks, we need reasonably fresh data, but don't force refresh every time
        # Check cache age and refresh if stale (older than 60 seconds) to ensure accurate status
        device_map = get_blocked(force_refresh=False)
        device_info = device_map.get(friendly_name)
        if device_info is None:
            print(f"[SCHEDULE] WARNING: {friendly_name} not found in device map, skipping")
            continue
        current_status = device_info.get("blocked", False)
        
        # If cache is very stale (older than 60 seconds), try to refresh once
        # This helps ensure schedule actions are based on current device status
        global cache_valid_until
        if cache_valid_until and datetime.now() > cache_valid_until + timedelta(seconds=30):
            # Cache is more than 30 seconds expired, try a refresh (but don't force if rate limited)
            if not check_rate_limit():
                device_map = get_blocked(force_refresh=True)
                device_info = device_map.get(friendly_name)
                if device_info:
                    current_status = device_info.get("blocked", False)
        now_str = now.strftime('%H:%M:%S')
        
        # Handle schedule logic
        # Schedule interpretation:
        # - block_time: when device should be BLOCKED
        # - unblock_time: when device should be UNBLOCKED
        # 
        # Example: "enable 15:00, disable 02:00" means:
        #   - Blocked from 02:00 to 15:00 (same day)
        #   - Unblocked from 15:00 to 02:00 next day (spans midnight)
        #
        # If unblock_time > block_time: Midnight-spanning schedule
        #   - Unblocked: from unblock_time to block_time next day (spans midnight)
        #   - Blocked: from block_time to unblock_time (same day)
        #   - Logic: unblocked if (now >= unblock_time) OR (now < block_time)
        #            blocked if (block_time <= now < unblock_time)
        #
        # If unblock_time < block_time: Normal same-day schedule (no midnight crossing)
        #   - Blocked: from block_time to unblock_time next day (spans midnight)
        #   - Unblocked: from unblock_time to block_time (same day)
        #   - Logic: blocked if now >= block_time OR now < unblock_time
        if unblock_time > block_time:
            # Midnight-spanning: unblocked from unblock_time to block_time next day
            # Blocked from block_time to unblock_time
            should_be_blocked = block_time <= now < unblock_time
        else:
            # Normal same-day schedule: blocked from block_time to unblock_time next day
            should_be_blocked = now >= block_time or now < unblock_time
        
        # Enhanced logging for debugging schedule issues
        print(f"[SCHEDULE] {friendly_name}: now={now_str}, block={block_time_str}, unblock={unblock_time_str}, should_be_blocked={should_be_blocked}, current_status={current_status}, has_manual_override={friendly_name in manual_overrides}")
        
        # Check if there's a manual override
        has_manual_override = friendly_name in manual_overrides
        manual_override_value = manual_overrides.get(friendly_name)
        
        # Apply schedule if needed
        # Manual overrides persist until schedule successfully takes action, then they are cleared
        if should_be_blocked and not current_status:
            # Schedule wants to block - attempt action regardless of manual override
            # If there's a manual override, log it but still attempt the schedule action
            if has_manual_override and manual_override_value is True:
                print(f"[SCHEDULE] {friendly_name}: Blocking (scheduled: {block_time_str} - {unblock_time_str}) - clearing manual override")
            else:
                print(f"[SCHEDULE] Blocking {friendly_name} (scheduled: {block_time_str} - {unblock_time_str})")
            # Apply schedule - turn_off will clear the manual override since is_manual=False
            if turn_off(friendly_name, mac, is_manual=False):
                if friendly_name in switches:
                    # Mark as programmatic update to prevent switch handler from logging duplicate event
                    _programmatic_switch_update.add(friendly_name)
                    switches[friendly_name].value = False
                    # Remove from programmatic set after a short delay
                    def clear_programmatic_flag():
                        _programmatic_switch_update.discard(friendly_name)
                    try:
                        # Try ui.timer first (works in UI context)
                        ui.timer(0.1, clear_programmatic_flag, once=True)
                    except:
                        # Fallback to threading.Timer if ui.timer doesn't work (e.g., from background thread)
                        timer = threading.Timer(0.1, clear_programmatic_flag)
                        timer.daemon = True
                        timer.start()
            else:
                print(f"[SCHEDULE] ERROR: Failed to block {friendly_name} (manual override will persist until next successful schedule action)")
        elif not should_be_blocked and current_status:
            # Schedule wants to unblock - attempt action regardless of manual override
            # If there's a manual override, log it but still attempt the schedule action
            if has_manual_override and manual_override_value is False:
                print(f"[SCHEDULE] {friendly_name}: Unblocking (scheduled: {block_time_str} - {unblock_time_str}) - clearing manual override")
            else:
                print(f"[SCHEDULE] Unblocking {friendly_name} (scheduled: {block_time_str} - {unblock_time_str})")
            # Apply schedule - turn_on will clear the manual override since is_manual=False
            if turn_on(friendly_name, mac, is_manual=False):
                if friendly_name in switches:
                    # Mark as programmatic update to prevent switch handler from logging duplicate event
                    _programmatic_switch_update.add(friendly_name)
                    switches[friendly_name].value = True
                    # Remove from programmatic set after a short delay
                    def clear_programmatic_flag():
                        _programmatic_switch_update.discard(friendly_name)
                    try:
                        # Try ui.timer first (works in UI context)
                        ui.timer(0.1, clear_programmatic_flag, once=True)
                    except:
                        # Fallback to threading.Timer if ui.timer doesn't work (e.g., from background thread)
                        timer = threading.Timer(0.1, clear_programmatic_flag)
                        timer.daemon = True
                        timer.start()
            else:
                print(f"[SCHEDULE] ERROR: Failed to unblock {friendly_name} (manual override will persist until next successful schedule action)")
        elif not should_be_blocked and not current_status:
            # Device should be unblocked and already is - this is fine, just log for debugging
            debug_log(f"[SCHEDULE] {friendly_name}: Already unblocked (as scheduled)")

def make_switch_handler(friendly_name, mac_address):
    def handler(e: ValueChangeEventArguments):
        if e.value:
            turn_on(friendly_name, mac_address)
        else:
            turn_off(friendly_name, mac_address)
    return handler

def make_temporary_button_handler(friendly_name, mac_address):
    """Create handler for temporary access buttons"""
    def handler():
        # Show dialog to get minutes
        with ui.dialog() as dialog, ui.card():
            ui.label(f'Grant temporary access to {friendly_name}').classes('text-lg font-bold')
            minutes_input = ui.number('Minutes', value=30, min=1, max=1440).classes('w-full')
            with ui.row():
                ui.button('Cancel', on_click=dialog.close)
                def grant_and_update():
                    debug_log(f"[DEBUG] grant_and_update: Starting for {friendly_name}")
                    # Grant temporary access first
                    success = turn_on_temporary(friendly_name, mac_address, int(minutes_input.value))
                    debug_log(f"[DEBUG] grant_and_update: turn_on_temporary returned {success}")
                    dialog.close()
                    if success:
                        # Wait a moment for the device switch to update, then show countdown
                        def show_countdown_after_delay():
                            debug_log(f"[DEBUG] show_countdown_after_delay: Called for {friendly_name}")
                            debug_log(f"[DEBUG] show_countdown_after_delay: {friendly_name} in temporary_access: {friendly_name in temporary_access}")
                            debug_log(f"[DEBUG] show_countdown_after_delay: {friendly_name} in countdown_labels: {friendly_name in countdown_labels}")
                            # Force update countdown after UI has settled
                            update_countdowns()
                            # Also ensure the countdown label is visible
                            if friendly_name in countdown_labels and countdown_labels[friendly_name]:
                                if friendly_name in temporary_access:
                                    debug_log(f"[DEBUG] show_countdown_after_delay: Forcing display for {friendly_name}")
                                    countdown_labels[friendly_name].style('display: block !important')
                                else:
                                    debug_log(f"[DEBUG] show_countdown_after_delay: WARNING - {friendly_name} not in temporary_access when trying to show")
                            else:
                                debug_log(f"[DEBUG] show_countdown_after_delay: WARNING - countdown_label not found for {friendly_name}")
                        
                        # Show countdown after a short delay to let switch update first
                        debug_log(f"[DEBUG] grant_and_update: Setting timer to show countdown in 0.3s")
                        ui.timer(0.3, show_countdown_after_delay, once=True)
                        # Refresh status after a longer delay
                        ui.timer(1.0, lambda: refresh_status(), once=True)
                    else:
                        debug_log(f"[DEBUG] grant_and_update: turn_on_temporary failed for {friendly_name}")
                
                ui.button('Grant Access', on_click=grant_and_update)
        dialog.open()
    return handler

def show_event_log():
    """Show event log dialog with scrollable list of events"""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-2xl max-h-[80vh]'):
        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('Event Log').classes('text-xl font-bold')
            ui.button('🗑️ Clear Log', on_click=lambda: clear_event_log(dialog)).classes('bg-red-600 text-white')
        # Scrollable container for events
        with ui.column().classes('w-full gap-2 overflow-y-auto max-h-[60vh]'):
            if not event_log:
                ui.label('No events recorded yet').classes('text-gray-500 text-center py-4')
            else:
                # Show events in reverse chronological order (newest first)
                for event in reversed(event_log[-50:]):  # Show last 50 events
                    timestamp = event['timestamp']
                    time_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    device = event['device']
                    event_type = event['event']
                    details = event.get('details', '')
                    
                    # Color code by event type
                    if 'Enabled' in event_type:
                        bg_color = 'bg-green-900'
                        icon = '✅'
                    elif 'Disabled' in event_type:
                        bg_color = 'bg-red-900'
                        icon = '❌'
                    elif 'Temporary' in event_type:
                        bg_color = 'bg-orange-900'
                        icon = '⏱'
                    else:
                        bg_color = 'bg-gray-800'
                        icon = 'ℹ'
                    
                    with ui.card().classes(f'{bg_color} p-2 text-sm'):
                        with ui.row().classes('items-center gap-2 w-full'):
                            ui.label(icon).classes('text-lg')
                            ui.label(f'{time_str}').classes('text-gray-300 font-mono text-xs')
                            ui.label(f'{device}').classes('font-bold flex-1')
                            ui.label(f'{event_type}').classes('text-gray-200')
                        if details:
                            ui.label(details).classes('text-gray-400 text-xs pl-6')
        
        ui.button('Close', on_click=dialog.close).classes('mt-4')
        dialog.open()

def clear_event_log(dialog):
    """Clear the event log"""
    global event_log
    event_log.clear()
    save_persistence()
    ui.notify('Event log cleared', type='positive')
    dialog.close()
    # Reopen the dialog to show empty log
    show_event_log()

def make_schedule_handler(friendly_name):
    """Create handler for schedule button"""
    def handler():
        schedule = devices_config.get(friendly_name, {}).get("schedule", {})
        current_enabled = schedule.get("enabled", False)
        block_time = schedule.get("block_time", "22:00")
        unblock_time = schedule.get("unblock_time", "07:00")
        
        with ui.dialog() as dialog, ui.card().classes('p-4 gap-4'):
            ui.label(f'Schedule Settings for {friendly_name}').classes('text-lg font-bold')
            
            # Toggle switch for enabling/disabling schedule
            schedule_enabled_switch = ui.switch(
                'Enable Scheduled Blocking',
                value=current_enabled
            ).classes('w-full')
            
            # Time inputs (only enabled when schedule is on)
            with ui.column().classes('w-full gap-2'):
                ui.label('Block Time (24-hour format):').classes('text-sm')
                block_time_input = ui.input(
                    'Block Time',
                    value=block_time,
                    placeholder='22:00'
                ).classes('w-full').bind_enabled_from(schedule_enabled_switch, 'value')
                
                ui.label('Unblock Time (24-hour format):').classes('text-sm')
                unblock_time_input = ui.input(
                    'Unblock Time',
                    value=unblock_time,
                    placeholder='07:00'
                ).classes('w-full').bind_enabled_from(schedule_enabled_switch, 'value')
            
            ui.label('Example: Block at 22:00 (10 PM), Unblock at 07:00 (7 AM)').classes('text-xs text-gray-500')
            
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dialog.close)
                def save_schedule():
                    enabled = schedule_enabled_switch.value
                    
                    # Get values safely (handle None when inputs are disabled)
                    block = block_time_input.value.strip() if block_time_input.value else None
                    unblock = unblock_time_input.value.strip() if unblock_time_input.value else None
                    
                    # Validate time format
                    try:
                        if enabled:
                            if not block or not unblock:
                                ui.notify('Please provide both block and unblock times', type='negative')
                                return
                            # Validate time format
                            datetime.strptime(block, "%H:%M")
                            datetime.strptime(unblock, "%H:%M")
                            update_schedule_times(friendly_name, block, unblock)
                        else:
                            toggle_schedule(friendly_name)
                        dialog.close()
                        # Reload devices config to get updated schedule
                        global devices_config
                        devices_config = load_devices()
                        # Update UI display
                        update_schedule_display(friendly_name)
                        refresh_status()
                    except ValueError:
                        ui.notify('Invalid time format. Use HH:MM (e.g., 22:00)', type='negative')
                
                ui.button('Save', on_click=save_schedule).classes('bg-blue-500')
        dialog.open()
    return handler

def update_chip_statuses():
    """Update online status chips by pinging devices"""
    for friendly_name in devices_config.keys():
        if friendly_name not in status_chips or status_chips[friendly_name] is None:
            continue
        
        device_info = devices_config[friendly_name]
        ip_address = device_info.get("ip_address")
        
        if not ip_address:
            # No IP address configured, hide chip
            status_chips[friendly_name].style('display: none')
            continue
        
        # Show chip
        status_chips[friendly_name].style('display: block')
        
        # Ping the device
        is_online = ping_device(ip_address, count=1, timeout=2)
        
        # Update chip based on ping result
        # Delete old chip and create new one using NiceGUI native chip function
        chip = status_chips[friendly_name]
        chip_containers = globals().get('chip_containers', {})
        
        try:
            # Delete the old chip
            chip.delete()
            
            # Get container and create new chip with correct state using native NiceGUI chip function
            if friendly_name in chip_containers:
                container = chip_containers[friendly_name]
                # Clear container and add new chip
                container.clear()
                with container:
                    if is_online is True:
                        # Device is online - green outlined chip with checkmark
                        status_chips[friendly_name] = ui.chip('Online', icon='check', color='green').props('square')
                    elif is_online is False:
                        # Device is offline - gray outlined chip  
                        status_chips[friendly_name] = ui.chip('Offline', icon='close', color='grey').props('square')
                    else:
                        # Error pinging - red outlined chip
                        status_chips[friendly_name] = ui.chip('Unknown', icon='warning', color='red').props('square')
            else:
                # Container not found - create chip without container (may appear in wrong location)
                if is_online is True:
                    status_chips[friendly_name] = ui.chip('Online', icon='check', color='green').props('square')
                elif is_online is False:
                    status_chips[friendly_name] = ui.chip('Offline', icon='close', color='grey').props('square')
                else:
                    status_chips[friendly_name] = ui.chip('Unknown', icon='warning', color='red').props('square')
        except Exception as e:
            debug_log(f"Error updating chip for {friendly_name}: {e}")
            # If deletion/recreation fails, try to recreate chip anyway
            try:
                if is_online is True:
                    status_chips[friendly_name] = ui.chip('Online', icon='check', color='green').props('square')
                elif is_online is False:
                    status_chips[friendly_name] = ui.chip('Offline', icon='close', color='grey').props('square')
                else:
                    status_chips[friendly_name] = ui.chip('Unknown', icon='warning', color='red').props('square')
            except:
                pass

# Build UI
with ui.column().classes('w-full h-screen items-start justify-center gap-4 px-8'):
    with ui.row().classes('w-full items-center justify-center gap-4 mb-4'):
        ui.label('Home Network - Control Panel v4.0.7').classes('text-2xl text-center')
        ui.button('📋 Event Log', on_click=lambda: show_event_log()).classes('bg-gray-600 text-white')
    
    # Connection status indicator
    status_label_ref[0] = ui.label('Connecting to UniFi controller...').classes('text-sm mb-2')
    
    def update_connection_status():
        if status_label_ref[0]:
            if ensure_controller():
                status_label_ref[0].text = '✓ Connected to UniFi controller'
                status_label_ref[0].classes('text-sm mb-2 text-green-500')
            else:
                status_label_ref[0].text = '⚠ Unable to connect to UniFi controller (will retry)'
                status_label_ref[0].classes('text-sm mb-2 text-orange-500')
    
    # Try initial connection (non-blocking)
    update_connection_status()
    
    # Initial chip status update
    ui.timer(2.0, update_chip_statuses, once=True)  # Update chip statuses once after UI loads
    
    device_map = get_blocked()
    for idx, (friendly_name, info) in enumerate(device_map.items()):
        # Alternate background colors: very dark blue (even) and lighter blue (odd)
        bg_color = 'bg-blue-950' if idx % 2 == 0 else 'bg-blue-800'
        with ui.column().classes(f'w-full gap-1 mb-0 {bg_color} p-2 rounded'):
            with ui.row().classes('items-center gap-4 w-full'):
                sw = ui.switch(
                    friendly_name,
                    value=not info["blocked"],
                    on_change=make_switch_handler(friendly_name, info["mac"])
                ).classes('flex-1')
                switches[friendly_name] = sw
                
                # Online status chip (only shown if IP address is configured)
                device_info = devices_config.get(friendly_name, {})
                ip_address = device_info.get("ip_address")
                if ip_address:
                    # Create a container div for the chip so we can replace it when updating
                    chip_container = ui.element('div').classes('inline-block')
                    with chip_container:
                        # Create chip with initial "Unknown" state (will be updated by timer)
                        status_chip = ui.chip('Unknown', icon='warning', color='red').props('square')
                        status_chips[friendly_name] = status_chip
                    # Store container reference for updates
                    if 'chip_containers' not in globals():
                        globals()['chip_containers'] = {}
                    globals()['chip_containers'][friendly_name] = chip_container
                else:
                    status_chips[friendly_name] = None
                
                # Temporary access button
                ui.button('+30 min', on_click=make_temporary_button_handler(friendly_name, info["mac"]))
                
                # Schedule button with calendar icon
                schedule = devices_config.get(friendly_name, {}).get("schedule", {})
                schedule_enabled = schedule.get("enabled", False)
                schedule_button = ui.button('📅', on_click=lambda fn=friendly_name: make_schedule_handler(fn)())
                if schedule_enabled:
                    schedule_button.classes('bg-blue-500 text-white')
                else:
                    schedule_button.classes('bg-gray-500 text-white')
            
            # Info row with countdown, schedule, and state history
            info_row = ui.row().classes('items-center gap-4 w-full pl-4 flex-wrap min-h-[16px]')
            with info_row:
                # Show temporary access countdown (always create, show/hide based on state)
                countdown_label = ui.label('').classes('text-xs text-orange-500 font-mono font-bold')
                countdown_labels[friendly_name] = countdown_label
                if friendly_name not in temporary_access:
                    countdown_label.style('display: none')
                
                # Show schedule status (create label and store reference)
                schedule = devices_config.get(friendly_name, {}).get("schedule", {})
                schedule_label = ui.label('').classes('text-xs text-gray-500')
                schedule_labels[friendly_name] = schedule_label  # Store reference for updates
                if schedule.get("enabled", False):
                    block_time = schedule.get("block_time", "N/A")
                    unblock_time = schedule.get("unblock_time", "N/A")
                    schedule_label.text = f"📅 Schedule: {unblock_time} - {block_time}"
                    schedule_label.style('display: block')
                else:
                    schedule_label.text = "📅 Schedule Disabled"
                    schedule_label.style('display: block')
                
                # Show last enabled/disabled times (create labels that will be updated dynamically)
                enabled_label = ui.label('').classes('text-xs text-green-500')
                enabled_labels[friendly_name] = enabled_label
                enabled_label.style('display: none')
                
                disabled_label = ui.label('').classes('text-xs text-red-500')
                disabled_labels[friendly_name] = disabled_label
                disabled_label.style('display: none')

def update_countdowns():
    """Update all countdown labels with remaining time and check for expired access"""
    global temporary_access
    now = datetime.now()
    
    debug_log(f"[DEBUG] update_countdowns: Called at {now.strftime('%H:%M:%S')}")
    debug_log(f"[DEBUG] update_countdowns: temporary_access has {len(temporary_access)} entries: {list(temporary_access.keys())}")
    
    # Check for expired temporary access (check every second now)
    expired_devices = []
    for friendly_name, block_time in list(temporary_access.items()):
        if now >= block_time:
            expired_devices.append(friendly_name)
    
    # Block expired devices
    for friendly_name in expired_devices:
        if friendly_name in devices_config:
            mac = devices_config[friendly_name]["mac"]
            print(f"Temporary access expired for {friendly_name}, blocking...")
            # Add to event log before blocking
            add_event_log(friendly_name, 'Temporary Access Expired', 'Auto-blocked after temporary access period ended')
            turn_off(friendly_name, mac, is_manual=False)
            del temporary_access[friendly_name]
            save_persistence()
            # Update UI switch
            if friendly_name in switches:
                switches[friendly_name].value = False
    
    # Check schedules every second (same frequency as temporary access)
    check_schedules()
    
    # Update countdown labels - ALWAYS show if temporary_access exists
    debug_log(f"[DEBUG] update_countdowns: Processing {len(countdown_labels)} countdown labels")
    for friendly_name, countdown_label in countdown_labels.items():
        if countdown_label is None:
            debug_log(f"[DEBUG] update_countdowns: {friendly_name} has None countdown_label, skipping")
            continue
        
        if friendly_name in temporary_access:
            block_time = temporary_access[friendly_name]
            remaining = block_time - now
            debug_log(f"[DEBUG] update_countdowns: {friendly_name} has temporary_access, block_time={block_time.strftime('%H:%M:%S')}, remaining={remaining.total_seconds():.1f}s")
            
            if remaining.total_seconds() > 0:
                total_seconds = int(remaining.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                if hours > 0:
                    countdown_text = f"⏱ {hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    countdown_text = f"⏱ {minutes}m {seconds}s"
                else:
                    countdown_text = f"⏱ {seconds}s"
                
                debug_log(f"[DEBUG] update_countdowns: Setting countdown for {friendly_name} to '{countdown_text}'")
                # Force update - set both text and display style
                try:
                    countdown_label.text = countdown_text
                    debug_log(f"[DEBUG] update_countdowns: ✓ Set text for {friendly_name}")
                    # Force display with multiple methods
                    countdown_label.style('display: block !important')
                    debug_log(f"[DEBUG] update_countdowns: ✓ Set display:block for {friendly_name}")
                    countdown_label.classes('text-xs text-orange-500 font-mono font-bold', remove='hidden')
                    debug_log(f"[DEBUG] update_countdowns: ✓ Set classes for {friendly_name}")
                except Exception as e:
                    print(f"ERROR updating countdown for {friendly_name}: {e}")
            else:
                # Time expired, hide countdown
                debug_log(f"[DEBUG] update_countdowns: {friendly_name} time expired, hiding countdown")
                try:
                    countdown_label.style('display: none')
                except Exception as e:
                    debug_log(f"[DEBUG] update_countdowns: ✗ ERROR hiding countdown for {friendly_name}: {e}")
        else:
            # No temporary access, hide countdown
            debug_log(f"[DEBUG] update_countdowns: {friendly_name} NOT in temporary_access, hiding countdown")
            try:
                countdown_label.style('display: none')
            except Exception as e:
                debug_log(f"[DEBUG] update_countdowns: ✗ ERROR hiding countdown for {friendly_name}: {e}")
    
    # Update enabled/disabled time labels
    for friendly_name in devices_config.keys():
        history = device_state_history.get(friendly_name, {})
        
        # Update enabled label
        if friendly_name in enabled_labels and enabled_labels[friendly_name]:
            if history.get('last_enabled'):
                enabled_time = history['last_enabled']
                # Format with date and time to show when device was actually enabled
                # Use date if enabled time is from a different day, otherwise just show time
                now = datetime.now()
                if enabled_time.date() == now.date():
                    # Same day - just show time
                    time_str = enabled_time.strftime('%H:%M:%S')
                else:
                    # Different day - show date and time
                    time_str = enabled_time.strftime('%Y-%m-%d %H:%M:%S')
                enabled_labels[friendly_name].text = f"✅ Enabled: {time_str}"
                enabled_labels[friendly_name].style('display: block')
            else:
                enabled_labels[friendly_name].style('display: none')
        
        # Update disabled label
        if friendly_name in disabled_labels and disabled_labels[friendly_name]:
            if history.get('last_disabled'):
                disabled_time = history['last_disabled']
                # Format with date and time to show when device was actually disabled
                # Use date if disabled time is from a different day, otherwise just show time
                now = datetime.now()
                if disabled_time.date() == now.date():
                    # Same day - just show time
                    time_str = disabled_time.strftime('%H:%M:%S')
                else:
                    # Different day - show date and time
                    time_str = disabled_time.strftime('%Y-%m-%d %H:%M:%S')
                disabled_labels[friendly_name].text = f"❌ Disabled: {time_str}"
                disabled_labels[friendly_name].style('display: block')
            else:
                disabled_labels[friendly_name].style('display: none')

# Periodically sync with UniFi - reduced frequency to avoid rate limits
def refresh_status():
    # Update connection status
    global rate_limit_until
    if status_label_ref[0]:
        try:
            if check_rate_limit():
                remaining = int((rate_limit_until - datetime.now()).total_seconds())
                status_label_ref[0].text = f'⏸ Rate limited - waiting {remaining}s before retry'
                status_label_ref[0].classes('text-sm mb-2 text-red-500')
            elif ensure_controller():
                status_label_ref[0].text = '✓ Connected to UniFi controller'
                status_label_ref[0].classes('text-sm mb-2 text-green-500')
            else:
                status_label_ref[0].text = '⚠ Unable to connect to UniFi controller (will retry)'
                status_label_ref[0].classes('text-sm mb-2 text-orange-500')
        except:
            pass  # Ignore errors updating status
    
    # CRITICAL: Update countdowns FIRST before any device status refresh
    # This ensures countdowns are set and visible before any UI updates
    update_countdowns()
    
    # Only refresh device status if not rate limited and cache expired
    # BUT: Don't override switch value if device has temporary access (countdown is active)
    if not check_rate_limit():
        device_map = get_blocked()  # This will use cache if available
    for name, info in device_map.items():
        if name in switches:
                # If device has temporary access, ALWAYS keep switch enabled and countdown visible
                if name in temporary_access:
                    # Force switch to enabled when temporary access is active
                    if not switches[name].value:
                        switches[name].value = True
                    # Ensure countdown is visible (double-check)
                    if name in countdown_labels and countdown_labels[name]:
                        if name in temporary_access:
                            block_time = temporary_access[name]
                            remaining = block_time - datetime.now()
                            if remaining.total_seconds() > 0:
                                countdown_labels[name].style('display: block !important')
                else:
                    # Only update switch if no temporary access is active
                    # BUT: Respect manual overrides - don't override switch if user manually set it
                    if name in manual_overrides:
                        # Manual override is set - respect it and don't update switch from controller state
                        manual_override_value = manual_overrides[name]
                        if switches[name].value != manual_override_value:
                            # Switch doesn't match manual override - update it to match
                            switches[name].value = manual_override_value
                    else:
                        # No manual override - sync switch with controller state
                        new_value = not info["blocked"]
                        if switches[name].value != new_value:
                            switches[name].value = new_value

# Check temporary access - now handled in update_countdowns() every second
def check_timers():
    # check_temporary_access() is now called in update_countdowns() every second
    check_schedules()  # Check schedules more frequently to catch trigger times
    refresh_status()

# Try to connect periodically if not connected (but respect rate limits)
def try_connect():
    if c is None and not check_rate_limit():
        ensure_controller()

# Timer frequencies optimized for rate limiting:
# - Update countdowns every second for real-time display
# - Schedules are checked by background thread every 10 seconds (independent of browser connections)
# - Refresh UI every 20 seconds (uses cache most of the time)
# - Reload devices.json every 30 seconds to sync changes across browser tabs
# - Try to connect every 60 seconds if not connected
# - Update chip statuses every 30 seconds (ping check)
# - Reconnect every 2 hours
ui.timer(1.0, update_countdowns)  # Update countdowns every second
ui.timer(20.0, refresh_status)  # Refresh UI every 20 seconds (uses cache)
ui.timer(30.0, update_chip_statuses)  # Update chip statuses every 30 seconds (ping check)

def reload_devices_for_ui():
    """Reload devices.json to sync changes across browser tabs"""
    global devices_config
    try:
        with _schedule_thread_lock:
            new_devices_config = load_devices()
            if new_devices_config != devices_config:
                devices_config = new_devices_config
                # Update schedule displays in UI
                for friendly_name in schedule_labels.keys():
                    update_schedule_display(friendly_name)
                print(f"[UI] Reloaded devices.json - schedule displays updated")
    except Exception as e:
        debug_log(f"[UI] Error reloading devices.json: {e}")

ui.timer(30.0, reload_devices_for_ui)  # Reload devices.json every 30 seconds to sync across browser tabs
ui.timer(60.0, try_connect)  # Try to connect every 60 seconds if not connected
ui.timer(7200.0, reconnect_controller)  # Reconnect every 2 hours

ui.run(dark=True, port=8080)
