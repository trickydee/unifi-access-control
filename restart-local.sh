#!/bin/bash
# Restart script for local testing with logging

# Stop any running instances
pkill -9 -f "unifi-access-control.py" 2>/dev/null
sleep 2

# Change to script directory
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Enable debug mode by setting environment variable
export DEBUG_MODE=true

# Start the app with logging
python unifi-access-control.py > /tmp/unifi-app.log 2>&1 &

echo "App started with logging enabled"
echo "Log file: /tmp/unifi-app.log"
echo "View logs: tail -f /tmp/unifi-app.log"
echo "App URL: http://localhost:8080"


