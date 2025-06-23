#!/bin/bash

# Install DDQ Scorer Cron Job (Every 3 Days)
# Run this script once on your AWS EC2 instance to set up the cron job

set -euo pipefail

# Get the absolute path to the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_SCRIPT="$SCRIPT_DIR/run_ddq_scorer.sh"

echo "=== Installing DDQ Scorer Cron Job ==="
echo "Script directory: $SCRIPT_DIR"
echo "Cron script: $CRON_SCRIPT"

# Verify the cron script exists and is executable
if [ ! -f "$CRON_SCRIPT" ]; then
    echo "ERROR: Cron script not found: $CRON_SCRIPT"
    exit 1
fi

if [ ! -x "$CRON_SCRIPT" ]; then
    echo "Making cron script executable..."
    chmod +x "$CRON_SCRIPT"
fi

# Create the cron job entry
# Runs at midnight every 3 days (0 0 */3 * *)
CRON_ENTRY="0 0 */3 * * $CRON_SCRIPT"

echo "Installing cron job with schedule: every 3 days at midnight"
echo "Cron entry: $CRON_ENTRY"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$CRON_SCRIPT"; then
    echo "Cron job already exists. Removing old entry..."
    crontab -l 2>/dev/null | grep -v "$CRON_SCRIPT" | crontab -
fi

# Add the new cron job
echo "Adding new cron job..."
(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo "✓ Cron job installed successfully!"
echo ""
echo "The DDQ scorer will now run automatically every 3 days at midnight."
echo "To check the cron job:"
echo "  crontab -l"
echo ""
echo "To view logs:"
echo "  tail -f $SCRIPT_DIR/logs/cron_ddq_scorer.log"
echo ""
echo "To remove the cron job:"
echo "  crontab -e  # Then delete the line containing '$CRON_SCRIPT'" 