# VPS Deployment Guide - Flask App with PostgreSQL, Redis, and Celery

This guide covers deploying a Flask application to any VPS provider (Hetzner, DigitalOcean, Linode, Vultr, etc.) without Docker, using Cloudflare Tunnel for secure access.

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Choose Your VPS Provider](#choose-your-vps-provider)
3. [Initial Server Setup](#initial-server-setup)
4. [Install Dependencies](#install-dependencies)
5. [Setup PostgreSQL](#setup-postgresql)
6. [Setup Redis](#setup-redis)
7. [Deploy Application](#deploy-application)
8. [Setup Systemd Services](#setup-systemd-services)
9. [Setup Cloudflare Tunnel](#setup-cloudflare-tunnel)
10. [Setup Backups](#setup-backups)
11. [Performance Optimization](#performance-optimization)
12. [Maintenance Commands](#maintenance-commands)
13. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### What You Need
- VPS account with any provider (see next section)
- Domain name (for Cloudflare Tunnel)
- Cloudflare account with domain configured
- SSH client (PuTTY for Windows, Terminal for Mac/Linux)
- Your GitHub repository URL
- Basic command line knowledge

### Recommended Server Specs
- **Minimum:** 2 vCPU, 4GB RAM, 40GB storage
- **Location:** Choose closest to your users for best performance

---

## Choose Your VPS Provider

This guide works with any VPS provider. Here are popular options:

| Provider |
|----------|
| **Hetzner** |
| **DigitalOcean** |
| **Linode** |
| **Vultr** |
| **Contabo** |
| **OVH** |


### Steps for Any Provider:

1. **Create account** and add payment method
2. **Create new server/droplet/instance:**
   - **OS:** Ubuntu 22.04 LTS (or latest Ubuntu LTS)
   - **Plan:** At least 2 vCPU, 4GB RAM
   - **Location:** Closest to your target users
   - **SSH Key:** Add your public SSH key (recommended)
   - **Hostname:** Choose a meaningful name
3. **Note your server's IP address** - you'll need this to connect

> **Note:** The exact steps vary by provider, but all offer similar options. Look for "Create Server," "Create Droplet," or "Deploy Instance."

---

## Initial Server Setup

Once you have your server and IP address, the rest is identical regardless of provider.

### 1. Connect to Server

Replace `YOUR_SERVER_IP` with the IP address your provider gave you:

```bash
ssh root@YOUR_SERVER_IP
```

### 2. Update System

```bash
apt update && apt upgrade -y
```

### 3. Create Application User

```bash
# Create dedicated user (never run apps as root!)
adduser --system --group --home /var/www/translator --shell /bin/bash translator

# Allow user to read system logs
usermod -aG systemd-journal translator
```

### 4. Setup Firewall

```bash
# Install and configure firewall
apt install -y ufw

# Allow SSH (IMPORTANT - don't lock yourself out!)
ufw allow OpenSSH

# Enable firewall (type 'y' when prompted)
ufw enable

# Verify
ufw status
```

> **Note:** We don't need to open ports 80/443 because Cloudflare Tunnel connects outbound.

### 5. Setup Automatic Security Updates

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
# Select "Yes" when prompted
```

### 6. Set Timezone

```bash
# Set to UTC (recommended for servers)
timedatectl set-timezone UTC

# Or your local timezone:
# timedatectl set-timezone America/New_York
```

---

## Install Dependencies

### 1. Install Python and Build Tools

```bash
apt install -y python3 python3-pip python3-venv python3-dev build-essential libpq-dev git curl wget

# Verify Python version (should be 3.10+)
python3 --version
```

> **Note:** Ubuntu 22.04 comes with Python 3.10, which works fine for most Flask apps.

---

## Setup PostgreSQL

### 1. Install PostgreSQL

```bash
apt install -y postgresql postgresql-contrib
```

### 2. Find PostgreSQL Version

```bash
# Check which version was installed
ls /etc/postgresql/
```

This will show a version number (e.g., `14`, `15`, or `16`). Use this version number in the next steps.

### 3. Create Database and User

```bash
# Switch to postgres user
sudo -u postgres psql
```

In the PostgreSQL prompt, run these commands:

```sql
-- Create user with a strong password
CREATE USER translator WITH PASSWORD 'your_secure_password_here';

-- Create database
CREATE DATABASE translator_db OWNER translator;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE translator_db TO translator;

-- Connect to database
\c translator_db

-- Enable UUID extension (if needed)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Exit
\q
```

> **Important:** Choose a strong password and save it! You'll need it later.

### 4. Configure PostgreSQL Authentication

Replace `14` with your actual PostgreSQL version:

```bash
nano /etc/postgresql/14/main/pg_hba.conf
```

Find this line:
```
local   all             all                                     peer
```

Change `peer` to `md5`:
```
local   all             all                                     md5
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 5. Restart PostgreSQL

```bash
systemctl restart postgresql
```

### 6. Test Connection

```bash
psql -U translator -d translator_db -h localhost
# Enter your password when prompted
# Type \q to exit if successful
```

---

## Setup Redis

### 1. Install Redis

```bash
apt install -y redis-server
```

### 2. Configure Redis

```bash
nano /etc/redis/redis.conf
```

Find and modify these settings:

1. Search for `supervised` (press `Ctrl+W`, type `supervised`, press `Enter`)
   - Change to: `supervised systemd`

2. Search for `maxmemory` (press `Ctrl+W`, type `maxmemory`, press `Enter`)
   - Add these lines:
   ```
   maxmemory 256mb
   maxmemory-policy allkeys-lru
   ```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 3. Start Redis

```bash
systemctl enable redis-server
systemctl start redis-server
```

### 4. Test Redis

```bash
redis-cli ping
# Should return: PONG
```

---

## Deploy Application

### 1. Create Directory Structure

```bash
mkdir -p /var/www/translator
mkdir -p /var/www/translator/data
mkdir -p /var/www/translator/logs
chown -R translator:translator /var/www/translator
```

> **Note:** Create additional data directories based on your app's needs (e.g., `/data/images`, `/data/exports`)

### 2. Clone Your Repository

```bash
# Switch to translator user
su - translator

# Navigate to app directory
cd /var/www/translator

# Clone your repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .
# The dot (.) at the end is important!

# Verify files are there
ls -la

# Exit back to root
exit
```

### 3. Create Virtual Environment

```bash
# Switch to translator user
su - translator
cd /var/www/translator

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Install production server
pip install gunicorn

# Exit back to root
exit
```

### 4. Create Environment File

First, generate a secure secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output, then create the `.env` file:

```bash
nano /var/www/translator/.env
```

Paste this configuration (update the values):

```env
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=paste_your_generated_secret_key_here

# Database (use the password you created earlier)
DATABASE_URL=postgresql://translator:your_secure_password_here@localhost/translator_db

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Data directories (adjust based on your app)
DATA_DIR=/var/www/translator/data

# Optional: Registration settings
REGISTRATION_ENABLED=true
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

Set secure permissions:

```bash
chmod 600 /var/www/translator/.env
chown translator:translator /var/www/translator/.env
```

### 5. Initialize Database

```bash
su - translator
cd /var/www/translator
source venv/bin/activate

# Create tables without starting the server
python - <<'PY'
from database.database import init_db
init_db()
print("✅ Database tables created successfully")
PY

exit
```

### 6. Fix Log Permissions

```bash
chown -R translator:translator /var/www/translator/logs
chmod -R 755 /var/www/translator/logs
```

---

## Setup Systemd Services

### 1. Create Gunicorn Service

```bash
nano /etc/systemd/system/translator.service
```

Paste this configuration:

```ini
[Unit]
Description=LunaFrost Translator Gunicorn Service
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
User=translator
Group=translator
WorkingDirectory=/var/www/translator
Environment="PATH=/var/www/translator/venv/bin"
EnvironmentFile=/var/www/translator/.env
ExecStart=/var/www/translator/venv/bin/gunicorn \
    --workers 7 \
    --worker-class gthread \
    --threads 2 \
    --bind 127.0.0.1:5000 \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile /var/www/translator/logs/access.log \
    --error-logfile /var/www/translator/logs/error.log \
    --capture-output \
    --enable-stdio-inheritance \
    wsgi:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 2. Create Celery Worker Service

```bash
nano /etc/systemd/system/translator-celery.service
```

Paste this:

```ini
[Unit]
Description=LunaFrost Translator Celery Worker
After=network.target redis.service postgresql.service
Requires=redis.service

[Service]
User=translator
Group=translator
WorkingDirectory=/var/www/translator
Environment="PATH=/var/www/translator/venv/bin"
EnvironmentFile=/var/www/translator/.env
ExecStart=/var/www/translator/venv/bin/celery \
    -A celery_app worker \
    --loglevel=info \
    --concurrency=6 \
    --logfile=/var/www/translator/logs/celery.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 3. Create Celery Beat Service

```bash
nano /etc/systemd/system/translator-celery-beat.service
```

Paste this:

```ini
[Unit]
Description=LunaFrost Translator Celery Beat Scheduler
After=network.target redis.service
Requires=redis.service

[Service]
User=translator
Group=translator
WorkingDirectory=/var/www/translator
Environment="PATH=/var/www/translator/venv/bin"
EnvironmentFile=/var/www/translator/.env
ExecStart=/var/www/translator/venv/bin/celery \
    -A celery_app beat \
    --loglevel=info \
    --logfile=/var/www/translator/logs/celery-beat.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 4. Enable and Start Services

```bash
# Reload systemd
systemctl daemon-reload

# Enable services to start on boot
systemctl enable translator
systemctl enable translator-celery
systemctl enable translator-celery-beat

# Start all services
systemctl start translator
systemctl start translator-celery
systemctl start translator-celery-beat

# Check status
systemctl status translator
systemctl status translator-celery
systemctl status translator-celery-beat
```

All three should show **"active (running)"** in green.

---

## Setup Cloudflare Tunnel

### 1. Install Cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
dpkg -i cloudflared.deb
rm cloudflared.deb
```

### 2. Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This will output a URL. **Copy the entire URL**, paste it into your browser, log in to Cloudflare, select your domain, and authorize.

### 3. Create Tunnel

```bash
cloudflared tunnel create YOUR_APP_NAME
```

This creates a tunnel and outputs a tunnel ID like:
```
Created tunnel YOUR_APP_NAME with id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Copy this tunnel ID!** You'll need it in the next step.

### 4. Create Tunnel Configuration

```bash
mkdir -p /etc/cloudflared
nano /etc/cloudflared/config.yml
```

Paste this (replace with your tunnel ID and domain):

```yaml
tunnel: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
credentials-file: /root/.cloudflared/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.json

ingress:
  - hostname: yourdomain.com
    service: http://127.0.0.1:5000
  - service: http_status:404
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 5. Route DNS

```bash
cloudflared tunnel route dns YOUR_APP_NAME yourdomain.com
```

### 6. Install and Start Tunnel Service

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
systemctl status cloudflared
```

### 7. Verify

Visit **https://yourdomain.com** in your browser. Your app should be live! 🎉

---

## Setup Backups

### 1. Create Backup Script

```bash
nano /var/www/translator/backup.sh
```

Paste this (update the password):

```bash
#!/bin/bash

# Configuration
BACKUP_DIR="/var/www/translator/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
echo "Backing up PostgreSQL..."
PGPASSWORD="your_secure_password_here" pg_dump -U translator -h localhost translator_db > "$BACKUP_DIR/db_$DATE.sql"
gzip "$BACKUP_DIR/db_$DATE.sql"

# Backup user data
echo "Backing up user data..."
tar -czf "$BACKUP_DIR/data_$DATE.tar.gz" -C /var/www/translator data/

# Backup configuration
echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" /var/www/translator/.env /etc/cloudflared/config.yml 2>/dev/null

# Delete old backups
echo "Cleaning old backups..."
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### 2. Set Permissions

```bash
chmod +x /var/www/translator/backup.sh
chown translator:translator /var/www/translator/backup.sh
mkdir -p /var/www/translator/backups
chown translator:translator /var/www/translator/backups
```

### 3. Test Backup

```bash
/var/www/translator/backup.sh
```

Should output "Backup completed: [timestamp]"

### 4. Schedule Daily Backups

```bash
crontab -e
```

If asked which editor, choose `1` for nano.

Add this line at the bottom:

```
0 3 * * * /var/www/translator/backup.sh >> /var/www/translator/logs/backup.log 2>&1
```

This runs backups daily at 3 AM.

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

---

## Performance Optimization

### 1. Add Swap Space

```bash
# Create 2GB swap file
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Verify
free -h
```

### 2. Verify Worker Configuration

Check your worker counts:

```bash
# Should show 7 workers + 1 master = 8 processes
ps aux | grep gunicorn | grep -v grep | wc -l

# Should show 6 workers + 1 main = 7 processes
ps aux | grep celery | grep worker | grep -v grep | wc -l
```

**Current capacity:**
- **Web:** 7 workers × 2 threads = **14 concurrent users**
- **Background:** 6 workers = **6 simultaneous tasks**

### 3. Monitor Resources

```bash
# Check memory
free -h

# Check disk space
df -h

# Check CPU and processes
htop
# Press 'q' to exit
```

**Target metrics:**
- Memory used: Under 70%
- Swap used: 0-10%
- CPU: Under 80% average

---

## Maintenance Commands

### Quick Reference

```bash
# View application status
systemctl status translator

# Restart application (graceful - no downtime)
systemctl reload translator

# Restart all services (full restart)
systemctl restart translator translator-celery translator-celery-beat

# View live application logs
tail -f /var/www/translator/logs/error.log
journalctl -u translator -f

# View Celery logs
tail -f /var/www/translator/logs/celery.log

# Check disk usage
df -h

# Check memory usage
free -h

# Check running processes
htop

# Run manual backup
/var/www/translator/backup.sh

# Update system packages (monthly)
apt update && apt upgrade -y
systemctl restart translator translator-celery translator-celery-beat
```

### Deployment Scripts

#### Restart Script

Create `/var/www/translator/restart.sh`:

```bash
nano /var/www/translator/restart.sh
```

Paste this:

```bash
#!/bin/bash
set -e

echo "========================================="
echo "  LunaFrost Translator Restart"
echo "========================================="
echo ""

# Restart services
echo "🔄 Restarting services..."
systemctl reload translator 2>/dev/null || systemctl restart translator
systemctl restart translator-celery
systemctl restart translator-celery-beat
echo "✅ Services restarted"
echo ""

# Check service status
echo "📊 Service Status:"
systemctl is-active translator && echo "   ✅ Gunicorn: Running" || echo "   ❌ Gunicorn: Failed"
systemctl is-active translator-celery && echo "   ✅ Celery Worker: Running" || echo "   ❌ Celery Worker: Failed"
systemctl is-active translator-celery-beat && echo "   ✅ Celery Beat: Running" || echo "   ❌ Celery Beat: Failed"
echo ""

echo "========================================="
echo "  ✨ Restart Complete!"
echo "========================================="
```

Make executable:

```bash
chmod +x /var/www/translator/restart.sh
```

#### Deploy Script (with Git)

Create `/var/www/translator/deploy.sh`:

```bash
nano /var/www/translator/deploy.sh
```

Paste this:

```bash
#!/bin/bash
set -e

echo "========================================="
echo "  LunaFrost Translator Deployment"
echo "========================================="
echo ""

cd /var/www/translator

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
sudo -u translator git fetch origin
sudo -u translator git reset --hard origin/main
sudo -u translator git clean -fd
echo "✅ Code updated"
echo ""

# Update dependencies
echo "📦 Updating dependencies..."
sudo -u translator /var/www/translator/venv/bin/pip install -r requirements.txt --quiet
echo "✅ Dependencies updated"
echo ""

# Restart services
echo "🔄 Restarting services..."
systemctl reload translator 2>/dev/null || systemctl restart translator
systemctl restart translator-celery
systemctl restart translator-celery-beat
echo "✅ Services restarted"
echo ""

# Check service status
echo "📊 Service Status:"
systemctl is-active translator && echo "   ✅ Gunicorn: Running" || echo "   ❌ Gunicorn: Failed"
systemctl is-active translator-celery && echo "   ✅ Celery Worker: Running" || echo "   ❌ Celery Worker: Failed"
systemctl is-active translator-celery-beat && echo "   ✅ Celery Beat: Running" || echo "   ❌ Celery Beat: Failed"
echo ""

echo "========================================="
echo "  ✨ Deployment Complete!"
echo "========================================="
```

Make executable:

```bash
chmod +x /var/www/translator/deploy.sh
```

**Usage:**
```bash
# Just restart services
/var/www/translator/restart.sh

# Pull from GitHub and restart
/var/www/translator/deploy.sh
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
journalctl -u translator -n 50 --no-pager
tail -n 100 /var/www/translator/logs/error.log

# Test manually as translator user
su - translator
cd /var/www/translator
source venv/bin/activate
python3 app.py
# Look for error messages
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
systemctl status postgresql

# Test connection manually
psql -U translator -d translator_db -h localhost
# If it fails, check password in .env file

# Check PostgreSQL version and config
ls /etc/postgresql/
# Make sure pg_hba.conf has 'md5' not 'peer'
```

### Redis Connection Issues

```bash
# Check Redis is running
systemctl status redis-server

# Test connection
redis-cli ping
# Should return PONG

# View Redis logs
journalctl -u redis-server -n 50
```

### Cloudflare Tunnel Issues

```bash
# Check tunnel status
systemctl status cloudflared

# View tunnel logs
journalctl -u cloudflared -f

# Test tunnel manually
cloudflared tunnel run YOUR_TUNNEL_NAME
# Press Ctrl+C to stop

# Verify tunnel info
cloudflared tunnel info YOUR_TUNNEL_NAME
```

### Permission Issues

```bash
# Fix ownership
chown -R translator:translator /var/www/translator

# Fix log permissions specifically
chown -R translator:translator /var/www/translator/logs
chmod -R 755 /var/www/translator/logs

# Fix data directory permissions
chmod -R 755 /var/www/translator/data
```

### Out of Memory

```bash
# Check memory usage
free -h

# Check what's using memory
ps aux --sort=-%mem | head -n 10

# If needed, reduce workers temporarily
nano /etc/systemd/system/translator.service
# Change --workers 7 to --workers 5
systemctl daemon-reload
systemctl restart translator
```

### High CPU Usage

```bash
# Check CPU usage
top
# Press '1' to see per-core usage
# Press 'q' to exit

# Reduce workers if needed
nano /etc/systemd/system/translator.service
# Change --workers 7 to --workers 5
systemctl daemon-reload
systemctl restart translator
```

### Can't Connect via SSH

If you've locked yourself out:

1. Log into Hetzner Cloud Console
2. Access server via web-based console
3. Check firewall: `ufw status`
4. Ensure SSH is allowed: `ufw allow OpenSSH`

### Database Password Issues

If you need to change the PostgreSQL password:

```bash
# Temporarily allow access without password
nano /etc/postgresql/14/main/pg_hba.conf
# Change the 'md5' to 'trust' for local connections
systemctl restart postgresql

# Change password
sudo -u postgres psql -c "ALTER USER translator WITH PASSWORD 'new_password';"

# Change back to 'md5'
nano /etc/postgresql/14/main/pg_hba.conf
systemctl restart postgresql

# Update .env file
nano /var/www/translator/.env
# Update DATABASE_URL with new password

# Update backup script
nano /var/www/translator/backup.sh
# Update PGPASSWORD with new password

# Restart services
/var/www/translator/restart.sh
```

## Security Checklist

After deployment, verify:

- [ ] Firewall enabled (UFW)
- [ ] Only SSH port open
- [ ] SSH key authentication (disable password login)
- [ ] Automatic security updates enabled
- [ ] App runs as non-root user (translator)
- [ ] Database password is strong
- [ ] .env file has restricted permissions (600)
- [ ] Cloudflare Tunnel hides server IP
- [ ] Regular backups configured and tested
- [ ] Swap space configured

### Optional: Disable Password SSH Login


---

## Additional Resources

### VPS Providers
- **Hetzner:** https://www.hetzner.com/cloud
- **DigitalOcean:** https://www.digitalocean.com/
- **Linode:** https://www.linode.com/
- **Vultr:** https://www.vultr.com/

### Documentation
- **Cloudflare Tunnel Docs:** https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- **Flask Production:** https://flask.palletsprojects.com/en/latest/deploying/
- **Gunicorn Docs:** https://docs.gunicorn.org/
- **Celery Docs:** https://docs.celeryq.dev/
- **Ubuntu Server Guide:** https://ubuntu.com/server/docs

---

## Getting Help

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs: `tail -f /var/www/translator/logs/error.log`
3. Check service status: `systemctl status translator`
4. Search the error message online
5. Ask in online forums
6. Shoot me an email with what happened and what you have tried to fix the issue.

---

## License

This is a universal VPS deployment guide for Flask applications with PostgreSQL, Redis, and Celery.

**Works with:** Hetzner, DigitalOcean, Linode, Vultr, Contabo, OVH, and most VPS providers running Ubuntu.

---

**Deployed successfully?**

Remember to:
1. Test all features thoroughly
2. Create your first admin user
3. Set up monitoring (optional)
4. Share with beta testers!

Good luck with your deployment!
