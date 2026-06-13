#!/bin/bash
# db-backup.sh — Sauvegarde PostgreSQL quotidienne avec rotation
#
# Rétention :
#   - 7 sauvegardes quotidiennes  (daily_YYYY-MM-DD_HHMMSS.sql.gz)
#   - 4 sauvegardes hebdomadaires (weekly_YYYY-MM-DD_HHMMSS.sql.gz)
#     → créées automatiquement chaque dimanche à partir du daily
#
# Résultat : au moins 7 jours glissants + 4 semaines d'ancienneté.
#
# Installation (en root sur le serveur de prod) :
#   cp /chemin/vers/db-backup.sh /root/scripts/db-backup.sh
#   chmod +x /root/scripts/db-backup.sh
#   crontab -e
#     0 3 * * * /root/scripts/db-backup.sh >> /root/db-backups/backup.log 2>&1
#
# Restauration :
#   gunzip -c /root/db-backups/daily_XXXX.sql.gz \
#     | docker compose -f /root/docker-compose.yml exec -T db psql -U mylocaldb mylocaldb

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
BACKUP_DIR=/root/db-backups
COMPOSE_FILE=/root/docker-compose.yml
DB_USER=mylocaldb
DB_NAME=mylocaldb
DAILY_KEEP=7
WEEKLY_KEEP=4
# ─────────────────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

mkdir -p "$BACKUP_DIR"

log "=== Début de la sauvegarde ==="

# Vérifier que le container DB tourne
if ! docker compose -f "$COMPOSE_FILE" ps -q db 2>/dev/null | grep -q .; then
    log "ERREUR : container DB non démarré — sauvegarde annulée."
    exit 1
fi

# ── Dump complet ──────────────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
DAILY_FILE="$BACKUP_DIR/daily_${TIMESTAMP}.sql.gz"

docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$DAILY_FILE"

SIZE=$(du -sh "$DAILY_FILE" | cut -f1)
log "Sauvegarde quotidienne : $DAILY_FILE ($SIZE)"

# ── Copie hebdomadaire (chaque dimanche) ──────────────────────────────────────
DAY_OF_WEEK=$(date +%u)  # 1=lundi … 7=dimanche
if [ "$DAY_OF_WEEK" = "7" ]; then
    WEEKLY_FILE="$BACKUP_DIR/weekly_${TIMESTAMP}.sql.gz"
    cp "$DAILY_FILE" "$WEEKLY_FILE"
    log "Sauvegarde hebdomadaire : $WEEKLY_FILE"
fi

# ── Rotation des quotidiennes (garder les $DAILY_KEEP dernières) ─────────────
DELETED=0
while IFS= read -r old_file; do
    rm -f "$old_file"
    log "  Supprimé (quotidien) : $old_file"
    DELETED=$((DELETED + 1))
done < <(ls -t "$BACKUP_DIR"/daily_*.sql.gz 2>/dev/null | tail -n +$((DAILY_KEEP + 1)))
[ "$DELETED" -eq 0 ] && log "  Rotation quotidienne : rien à supprimer."

# ── Rotation des hebdomadaires (garder les $WEEKLY_KEEP dernières) ───────────
DELETED=0
while IFS= read -r old_file; do
    rm -f "$old_file"
    log "  Supprimé (hebdomadaire) : $old_file"
    DELETED=$((DELETED + 1))
done < <(ls -t "$BACKUP_DIR"/weekly_*.sql.gz 2>/dev/null | tail -n +$((WEEKLY_KEEP + 1)))
[ "$DELETED" -eq 0 ] && log "  Rotation hebdomadaire : rien à supprimer."

# ── Résumé ────────────────────────────────────────────────────────────────────
DAILY_COUNT=$(ls "$BACKUP_DIR"/daily_*.sql.gz 2>/dev/null | wc -l)
WEEKLY_COUNT=$(ls "$BACKUP_DIR"/weekly_*.sql.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

log "=== Sauvegarde terminée : ${DAILY_COUNT} daily / ${WEEKLY_COUNT} weekly — ${TOTAL_SIZE} utilisés ==="
