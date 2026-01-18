#!/bin/bash
# Uninstall Job Hunter Sentinel cron jobs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SCRIPT="$SCRIPT_DIR/main.py"

echo "🗑️  Job Hunter Sentinel - Cron Uninstall"
echo "========================================"
echo ""

# Backup existing crontab
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || true
echo "💾 Backed up existing crontab to /tmp/"

# Remove Job Hunter entries
crontab -l 2>/dev/null | grep -v "Job Hunter Sentinel" | grep -v "$MAIN_SCRIPT" > /tmp/crontab_new.txt || true

# Install cleaned crontab
crontab /tmp/crontab_new.txt

if [ $? -eq 0 ]; then
    echo "✅ Job Hunter Sentinel cron jobs removed successfully"
    echo ""
    echo "🔍 To verify, run:"
    echo "   crontab -l"
else
    echo "❌ Failed to remove cron jobs"
    exit 1
fi

# Cleanup
rm /tmp/crontab_new.txt
