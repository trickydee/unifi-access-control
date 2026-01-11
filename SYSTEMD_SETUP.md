# Systemd Service Setup for Production

## Installation Steps

1. **Edit the service file** (`unifi-access-control.service`):
   - Replace `YOUR_USERNAME` with the user account that should run the service
   - Replace `/path/to/unifi-access-control` with the actual path to your application directory
   - Adjust log paths if needed (ensure the log directory exists)

2. **Create log directory** (if using custom log paths):
   ```bash
   sudo mkdir -p /var/log/unifi-access-control
   sudo chown YOUR_USERNAME:YOUR_USERNAME /var/log/unifi-access-control
   ```

3. **Copy service file to systemd directory**:
   ```bash
   sudo cp unifi-access-control.service /etc/systemd/system/
   ```

4. **Reload systemd**:
   ```bash
   sudo systemctl daemon-reload
   ```

5. **Enable service to start on boot**:
   ```bash
   sudo systemctl enable unifi-access-control.service
   ```

6. **Start the service**:
   ```bash
   sudo systemctl start unifi-access-control.service
   ```

## Managing the Service

- **Check status**: `sudo systemctl status unifi-access-control.service`
- **View logs**: `sudo journalctl -u unifi-access-control.service -f`
- **View app logs** (if using file logging): `tail -f /var/log/unifi-access-control/app.log`
- **View error logs**: `tail -f /var/log/unifi-access-control/error.log`
- **Restart service**: `sudo systemctl restart unifi-access-control.service`
- **Stop service**: `sudo systemctl stop unifi-access-control.service`
- **Disable auto-start**: `sudo systemctl disable unifi-access-control.service`

## Debugging Configuration

The service file includes `Environment="DEBUG_MODE=true"` which enables debug logging.

To disable debugging, edit `/etc/systemd/system/unifi-access-control.service` and change:
```
Environment="DEBUG_MODE=false"
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart unifi-access-control.service
```

## Alternative: Using Journald Only

If you prefer to use systemd's journald instead of file logging, you can modify the service file:

Remove or comment out these lines:
```
StandardOutput=append:/var/log/unifi-access-control/app.log
StandardError=append:/var/log/unifi-access-control/error.log
```

Then view logs with:
```bash
sudo journalctl -u unifi-access-control.service -f
```

