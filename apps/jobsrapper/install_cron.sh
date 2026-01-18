#!/bin/bash
# Local Cron Setup Script for Job Hunter Sentinel
# Sets up crontab to run job scraper 3 times daily: 8 AM, 12 PM, 6 PM

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
MAIN_SCRIPT="$SCRIPT_DIR/main.py"
LOG_DIR="$SCRIPT_DIR/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

echo "🔧 Job Hunter Sentinel - Cron Setup"
echo "===================================="
echo ""
echo "Script Directory: $SCRIPT_DIR"
echo "Python: $VENV_PYTHON"
echo "Main Script: $MAIN_SCRIPT"
echo ""

# Check if virtual environment exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Virtual environment not found at $VENV_PYTHON"
    echo "Please run ./setup.sh first to create the virtual environment"
    exit 1
fi

# Check if main.py exists
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "❌ main.py not found at $MAIN_SCRIPT"
    exit 1
fi

# Create cron job entries
CRON_JOB_08="0 8 * * * cd $SCRIPT_DIR && $VENV_PYTHON $MAIN_SCRIPT >> $LOG_DIR/cron_08.log 2>&1"
CRON_JOB_12="0 12 * * * cd $SCRIPT_DIR && $VENV_PYTHON $MAIN_SCRIPT >> $LOG_DIR/cron_12.log 2>&1"
CRON_JOB_18="0 18 * * * cd $SCRIPT_DIR && $VENV_PYTHON $MAIN_SCRIPT >> $LOG_DIR/cron_18.log 2>&1"

echo "📋 Cron jobs to be added:"
echo ""
echo "1. 8:00 AM  - $CRON_JOB_08"
echo "2. 12:00 PM - $CRON_JOB_12"
echo "3. 6:00 PM  - $CRON_JOB_18"
echo ""

# Ask for confirmation
read -p "Do you want to add these cron jobs? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Installation cancelled"
    exit 0
fi

# Backup existing crontab
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || true
echo "💾 Backed up existing crontab to /tmp/"

# Remove existing Job Hunter entries (if any)
crontab -l 2>/dev/null | grep -v "Job Hunter Sentinel" | grep -v "$MAIN_SCRIPT" > /tmp/crontab_new.txt || true

# Add header comment
echo "" >> /tmp/crontab_new.txt
echo "# Job Hunter Sentinel - Auto-generated cron jobs" >> /tmp/crontab_new.txt
echo "$CRON_JOB_08" >> /tmp/crontab_new.txt
echo "$CRON_JOB_12" >> /tmp/crontab_new.txt
echo "$CRON_JOB_18" >> /tmp/crontab_new.txt

# Install new crontab
crontab /tmp/crontab_new.txt

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Cron jobs successfully installed!"
    echo ""
    echo "📅 Schedule:"
    echo "   - 8:00 AM  daily"
    echo "   - 12:00 PM daily"
    echo "   - 6:00 PM  daily"
    echo ""
    echo "📝 Logs will be saved to: $LOG_DIR/"
    echo ""
    echo "🔍 To view current cron jobs, run:"
    echo "   crontab -l"
    echo ""
    echo "🗑️  To remove these cron jobs, run:"
    echo "   ./uninstall_cron.sh"
    echo ""
else
    echo "❌ Failed to install cron jobs"
    exit 1
fi

# Cleanup
rm /tmp/crontab_new.txt
