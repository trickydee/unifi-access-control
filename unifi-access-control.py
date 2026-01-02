import json
from datetime import datetime, timedelta
from pyunifi.controller import Controller
from nicegui import app, ui
from nicegui.events import ValueChangeEventArguments
import os

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

# Persistence for temporary access and device state
PERSISTENCE_FILE = 'device_state.json'

def load_persistence():
    """Load temporary access and device state history from file"""
    global temporary_access, device_state_history
    # Initialize if not already initialized
    if 'temporary_access' not in globals():
        temporary_access = {}
    if 'device_state_history' not in globals():
        device_state_history = {}
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, 'r') as f:
                data = json.load(f)
                # Convert datetime strings back to datetime objects
                if 'temporary_access' in data:
                    for name, time_str in data['temporary_access'].items():
                        try:
                            temp_time = datetime.fromisoformat(time_str)
                            # Only restore if it's in the future
                            if temp_time > datetime.now():
                                temporary_access[name] = temp_time
                        except:
                            pass
                if 'device_state_history' in data:
                    for name, history in data['device_state_history'].items():
                        device_state_history[name] = {}
                        if 'last_enabled' in history and history['last_enabled']:
                            try:
                                device_state_history[name]['last_enabled'] = datetime.fromisoformat(history['last_enabled'])
                            except:
                                pass
                        if 'last_disabled' in history and history['last_disabled']:
                            try:
                                device_state_history[name]['last_disabled'] = datetime.fromisoformat(history['last_disabled'])
                            except:
                                pass
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
            }
        }
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving persistence: {e}")

config = load_config()
devices_config = load_devices()

unifi_username = config['unifi_username']
unifi_password = config['unifi_password']
unifi_controller = config['unifi_controller']

# Store switch references and temporary access timers
switches = {}
temporary_access = {}  # {device_name: datetime when it should be blocked again}
schedule_timers = {}  # Track scheduled block/unblock timers
status_label_ref = [None]  # Will be set when UI is built (using list for mutable reference)
device_state_history = {}  # {device_name: {"last_enabled": datetime, "last_disabled": datetime}}
countdown_labels = {}  # {device_name: ui.label} for countdown display
enabled_labels = {}  # {device_name: ui.label} for enabled time display
disabled_labels = {}  # {device_name: ui.label} for disabled time display

load_persistence()  # Load persisted state on startup (after variables are initialized)

# Initialize controller as None - will be created lazily
c = None

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
        print(f"Rate limited, waiting {int(remaining)} more seconds...")
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

def turn_on(friendly_name, mac_address):
    global cached_device_status, cache_valid_until, rate_limit_until, c, device_state_history
    if check_rate_limit():
        print(f"Rate limited, cannot unblock {friendly_name} right now")
        return False
    if not ensure_controller():
        print(f"Failed to unblock {friendly_name}: Controller not available")
        return False
    try:
        print("Unblocking...", friendly_name)
        c.unblock_client(mac_address)
        # Clear cache to force refresh on next call
        cached_device_status = None
        cache_valid_until = None
        # Clear any temporary access timer if manually unblocked
        if friendly_name in temporary_access:
            del temporary_access[friendly_name]
        # Record enable time
        if friendly_name not in device_state_history:
            device_state_history[friendly_name] = {}
        device_state_history[friendly_name]['last_enabled'] = datetime.now()
        save_persistence()
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

def turn_off(friendly_name, mac_address):
    global cached_device_status, cache_valid_until, rate_limit_until, c, device_state_history
    if check_rate_limit():
        print(f"Rate limited, cannot block {friendly_name} right now")
        return False
    if not ensure_controller():
        print(f"Failed to block {friendly_name}: Controller not available")
        return False
    try:
        print("Blocking...", friendly_name)
        c.block_client(mac_address)
        # Clear cache to force refresh on next call
        cached_device_status = None
        cache_valid_until = None
        # Clear any temporary access timer if manually blocked
        if friendly_name in temporary_access:
            del temporary_access[friendly_name]
        # Record disable time
        if friendly_name not in device_state_history:
            device_state_history[friendly_name] = {}
        device_state_history[friendly_name]['last_disabled'] = datetime.now()
        save_persistence()
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
    global cached_device_status, cache_valid_until, rate_limit_until, c, device_state_history
    if check_rate_limit():
        print(f"Rate limited, cannot grant temporary access to {friendly_name} right now")
        return False
    if not ensure_controller():
        print(f"Failed to grant temporary access to {friendly_name}: Controller not available")
        return False
    try:
        print(f"Unblocking {friendly_name} temporarily for {minutes} minutes")
        c.unblock_client(mac_address)
        # Clear cache to force refresh on next call
        cached_device_status = None
        cache_valid_until = None
        # Schedule auto-block
        block_time = datetime.now() + timedelta(minutes=minutes)
        temporary_access[friendly_name] = block_time
        # Record enable time
        if friendly_name not in device_state_history:
            device_state_history[friendly_name] = {}
        device_state_history[friendly_name]['last_enabled'] = datetime.now()
        save_persistence()
        # Show countdown label if it exists
        if friendly_name in countdown_labels and countdown_labels[friendly_name]:
            countdown_labels[friendly_name].style('display: block')
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
    """Check and apply scheduled block/unblock times"""
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
        current_status = get_blocked().get(friendly_name, {}).get("blocked", False)
        
        # Handle schedule logic
        # If block time is before unblock time (e.g., 22:00 to 07:00), it spans midnight
        if block_time < unblock_time:
            # Normal case: block_time to unblock_time same day
            should_be_blocked = block_time <= now < unblock_time
        else:
            # Spans midnight: block_time to midnight, then midnight to unblock_time
            should_be_blocked = now >= block_time or now < unblock_time
        
        # Apply schedule if needed
        if should_be_blocked and not current_status:
            print(f"Scheduled block: {friendly_name}")
            turn_off(friendly_name, mac)
            if friendly_name in switches:
                switches[friendly_name].value = False
        elif not should_be_blocked and current_status:
            print(f"Scheduled unblock: {friendly_name}")
            turn_on(friendly_name, mac)
            if friendly_name in switches:
                switches[friendly_name].value = True

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
                ui.button('Grant Access', on_click=lambda: [
                    turn_on_temporary(friendly_name, mac_address, int(minutes_input.value)),
                    dialog.close(),
                    refresh_status()
                ])
        dialog.open()
    return handler

# Build UI
with ui.column().classes('w-full h-screen items-start justify-center gap-4 px-8'):
    ui.label('Home Network - Control Panel v2.2').classes('text-2xl mb-6')
    
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
    
    device_map = get_blocked()
    for friendly_name, info in device_map.items():
        with ui.column().classes('w-full gap-1 mb-2'):
            with ui.row().classes('items-center gap-4 w-full'):
                sw = ui.switch(
                    friendly_name,
                    value=not info["blocked"],
                    on_change=make_switch_handler(friendly_name, info["mac"])
                ).classes('flex-1')
                switches[friendly_name] = sw
                
                # Temporary access button
                ui.button('+30 min', on_click=make_temporary_button_handler(friendly_name, info["mac"]))
            
            # Info row with countdown, schedule, and state history
            info_row = ui.row().classes('items-center gap-4 w-full pl-4 flex-wrap min-h-[20px]')
            with info_row:
                # Show temporary access countdown (always create, show/hide based on state)
                countdown_label = ui.label('').classes('text-xs text-orange-500 font-mono font-bold')
                countdown_labels[friendly_name] = countdown_label
                if friendly_name not in temporary_access:
                    countdown_label.style('display: none')
                
                # Show schedule status if enabled
                schedule = devices_config.get(friendly_name, {}).get("schedule", {})
                if schedule.get("enabled", False):
                    block_time = schedule.get("block_time", "N/A")
                    unblock_time = schedule.get("unblock_time", "N/A")
                    ui.label(f"📅 Schedule: {unblock_time} - {block_time}").classes('text-xs text-gray-500')
                
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
            turn_off(friendly_name, mac)
            del temporary_access[friendly_name]
            save_persistence()
            # Update UI switch
            if friendly_name in switches:
                switches[friendly_name].value = False
    
    # Update countdown labels
    for friendly_name, countdown_label in countdown_labels.items():
        if countdown_label is None:
            continue
        if friendly_name in temporary_access:
            block_time = temporary_access[friendly_name]
            remaining = block_time - now
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
                countdown_label.text = countdown_text
                countdown_label.style('display: block')
            else:
                countdown_label.style('display: none')
        else:
            countdown_label.style('display: none')
    
    # Update enabled/disabled time labels
    for friendly_name in devices_config.keys():
        history = device_state_history.get(friendly_name, {})
        
        # Update enabled label
        if friendly_name in enabled_labels and enabled_labels[friendly_name]:
            if history.get('last_enabled'):
                enabled_time = history['last_enabled']
                time_str = enabled_time.strftime('%H:%M:%S')
                enabled_labels[friendly_name].text = f"✅ Enabled: {time_str}"
                enabled_labels[friendly_name].style('display: block')
            else:
                enabled_labels[friendly_name].style('display: none')
        
        # Update disabled label
        if friendly_name in disabled_labels and disabled_labels[friendly_name]:
            if history.get('last_disabled'):
                disabled_time = history['last_disabled']
                time_str = disabled_time.strftime('%H:%M:%S')
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
    
    # Update countdowns every refresh
    update_countdowns()
    
    # Only refresh device status if not rate limited and cache expired
    if not check_rate_limit():
        device_map = get_blocked()  # This will use cache if available
        for name, info in device_map.items():
            if name in switches:
                new_value = not info["blocked"]
                if switches[name].value != new_value:
                    switches[name].value = new_value

# Check temporary access - now handled in update_countdowns() every second
def check_timers():
    # check_temporary_access() is now called in update_countdowns() every second
    check_schedules()
    refresh_status()

# Try to connect periodically if not connected (but respect rate limits)
def try_connect():
    if c is None and not check_rate_limit():
        ensure_controller()

# Reduced frequency to avoid rate limits:
# - Refresh UI every 20 seconds (was 10) - uses cache most of the time
# - Update countdowns every second for real-time display
# - Try to connect every 60 seconds if not connected (was 30)
# - Check timers and schedules every 2 minutes (was 1 minute)
# - Reconnect every 2 hours (was 1 hour)
ui.timer(1.0, update_countdowns)  # Update countdowns every second
ui.timer(20.0, refresh_status)  # Refresh UI every 20 seconds (uses cache)
ui.timer(60.0, try_connect)  # Try to connect every 60 seconds if not connected
ui.timer(120.0, check_timers)  # Check timers and schedules every 2 minutes
ui.timer(7200.0, reconnect_controller)  # Reconnect every 2 hours

ui.run(dark=True, port=8081)
