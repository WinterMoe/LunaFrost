#!/bin/bash

BACKUP_DIR="/var/www/translator/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

mkdir -p $BACKUP_DIR

echo "Backing up PostgreSQL..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -U translator -h localhost translator_db > "$BACKUP_DIR/db_$DATE.sql"
gzip "$BACKUP_DIR/db_$DATE.sql"

echo "Backing up user data..."
tar -czf "$BACKUP_DIR/data_$DATE.tar.gz" -C /var/www/translator data/

echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" /var/www/translator/.env /etc/cloudflared/config.yml

echo "Cleaning old backups..."
find $BACKUP_DIR -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
