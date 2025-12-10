#!/bin/bash
set -e

echo "========================================="
echo "  LunaFrost Translator Restart"
echo "========================================="
echo ""

echo "🔐 Fixing file permissions..."
chown -R translator:translator /var/www/translator
chmod -R 755 /var/www/translator
echo "✅ Permissions fixed"
echo ""

echo "🔄 Restarting services..."
systemctl reload translator 2>/dev/null || systemctl restart translator
systemctl restart translator-celery
systemctl restart translator-celery-beat
echo "✅ Services restarted"
echo ""

echo "📊 Service Status:"
systemctl is-active translator && echo "   ✅ Gunicorn: Running" || echo "   ❌ Gunicorn: Failed"
systemctl is-active translator-celery && echo "   ✅ Celery Worker: Running" || echo "   ❌ Celery Worker: Failed"
systemctl is-active translator-celery-beat && echo "   ✅ Celery Beat: Running" || echo "   ❌ Celery Beat: Failed"
echo ""

echo "========================================="
echo "  ✨ Restart Complete!"
echo "========================================="
echo ""
echo "Visit: https://lunafrost.moe"
echo ""
echo "View logs with:"
echo "  tail -f /var/www/translator/logs/error.log"
echo "  journalctl -u translator -f"
echo ""
