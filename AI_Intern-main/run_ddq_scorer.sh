#!/bin/bash

# DDQ Scorer Cron Job Script for AWS EC2
# Runs every 3 days to process completed DDQs

# Set strict error handling
set -euo pipefail

# Define paths (adjust these for your EC2 deployment)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/logs/cron_ddq_scorer.log"

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to cleanup on exit
cleanup() {
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log "DDQ scorer completed successfully"
    else
        log "DDQ scorer failed with exit code: $exit_code"
    fi
}

# Set trap for cleanup
trap cleanup EXIT

# Start logging
log "=== Starting DDQ Scorer Cron Job ==="
log "Script directory: $SCRIPT_DIR"
log "Root directory: $ROOT_DIR"

# Change to AI_Intern-main directory
cd "$SCRIPT_DIR"

# Activate virtual environment
log "Activating virtual environment..."
source "$SCRIPT_DIR/venv/bin/activate"

# Verify environment variables are available from root
log "Checking environment variables..."
if [ -f "$ROOT_DIR/.env" ]; then
    log "Found root .env file"
    # Export environment variables for this session
    set -a
    source "$ROOT_DIR/.env"
    set +a
else
    log "WARNING: No .env file found in root directory"
fi

# Check required environment variables
python3 -c "from src.config import check_required_env; check_required_env(); print('✓ Environment variables validated')" 2>&1 | tee -a "$LOG_FILE"

# Run the DDQ scorer
log "Starting DDQ scorer execution..."
python3 run.py 2>&1 | tee -a "$LOG_FILE"

log "=== DDQ Scorer Cron Job Completed ===" 