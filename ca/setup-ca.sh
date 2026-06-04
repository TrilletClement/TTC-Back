#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup-ca.sh — One-time Device CA initialisation
#
# Run this script ONCE on the production server to create:
#   Root CA       (EC P-384, 10-year validity)
#   Intermediate CA (EC P-256, 5-year validity, signed by Root CA)
#
# After it completes:
#   1. COPY  ./root/private/ca.key  to an offline encrypted USB drive.
#   2. DELETE ./root/private/ca.key from this server immediately.
#   3. Keep ./intermediate/ — it stays on the server and is mounted into
#      the API Docker container for device cert signing.
#
# The script is idempotent: it skips steps already done.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/root"
INTER_DIR="$SCRIPT_DIR/intermediate"

# Substitute real path into OpenSSL configs
ROOT_CNF="$SCRIPT_DIR/openssl-root.cnf"
ROOT_CNF_TMP="$SCRIPT_DIR/.openssl-root-resolved.cnf"
sed "s|DIR_PLACEHOLDER|$SCRIPT_DIR|g" "$ROOT_CNF" > "$ROOT_CNF_TMP"

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------
for d in \
    "$ROOT_DIR/private" \
    "$ROOT_DIR/certs" \
    "$ROOT_DIR/newcerts" \
    "$INTER_DIR/private" \
    "$INTER_DIR/certs" \
    "$INTER_DIR/csr"; do
    mkdir -p "$d"
done

chmod 700 "$ROOT_DIR/private" "$INTER_DIR/private"
touch "$ROOT_DIR/index.txt" 2>/dev/null || true
[ -f "$ROOT_DIR/serial" ] || echo "1000" > "$ROOT_DIR/serial"

# ---------------------------------------------------------------------------
# Step 1 — Root CA key + self-signed certificate
# ---------------------------------------------------------------------------
if [ ! -f "$ROOT_DIR/private/ca.key" ]; then
    echo "==> Generating Root CA key (EC P-384)..."
    openssl ecparam -name secp384r1 -genkey -noout \
        -out "$ROOT_DIR/private/ca.key"
    chmod 400 "$ROOT_DIR/private/ca.key"
else
    echo "--> Root CA key already exists, skipping."
fi

if [ ! -f "$ROOT_DIR/certs/ca.crt" ]; then
    echo "==> Self-signing Root CA certificate (10 years)..."
    openssl req -new -x509 \
        -config "$ROOT_CNF_TMP" \
        -extensions v3_ca \
        -days 3650 \
        -key "$ROOT_DIR/private/ca.key" \
        -out "$ROOT_DIR/certs/ca.crt"
    echo "Root CA certificate: $ROOT_DIR/certs/ca.crt"
else
    echo "--> Root CA certificate already exists, skipping."
fi

# ---------------------------------------------------------------------------
# Step 2 — Intermediate CA key + CSR
# ---------------------------------------------------------------------------
if [ ! -f "$INTER_DIR/private/inter.key" ]; then
    echo "==> Generating Intermediate CA key (EC P-256)..."
    openssl ecparam -name prime256v1 -genkey -noout \
        -out "$INTER_DIR/private/inter.key"
    chmod 400 "$INTER_DIR/private/inter.key"
else
    echo "--> Intermediate CA key already exists, skipping."
fi

if [ ! -f "$INTER_DIR/csr/inter.csr" ]; then
    echo "==> Generating Intermediate CA CSR..."
    openssl req -new \
        -config "$SCRIPT_DIR/openssl-inter.cnf" \
        -key "$INTER_DIR/private/inter.key" \
        -out "$INTER_DIR/csr/inter.csr"
else
    echo "--> Intermediate CA CSR already exists, skipping."
fi

# ---------------------------------------------------------------------------
# Step 3 — Sign Intermediate CA with Root CA
# ---------------------------------------------------------------------------
if [ ! -f "$INTER_DIR/certs/inter.crt" ]; then
    echo "==> Signing Intermediate CA certificate (5 years)..."
    openssl ca \
        -config "$ROOT_CNF_TMP" \
        -extensions v3_intermediate_ca \
        -days 1825 \
        -notext \
        -batch \
        -md sha256 \
        -in "$INTER_DIR/csr/inter.csr" \
        -out "$INTER_DIR/certs/inter.crt"
    chmod 444 "$INTER_DIR/certs/inter.crt"
else
    echo "--> Intermediate CA certificate already exists, skipping."
fi

# ---------------------------------------------------------------------------
# Step 4 — Build CA chain (Intermediate + Root — nginx uses this)
# ---------------------------------------------------------------------------
if [ ! -f "$INTER_DIR/certs/ca-chain.pem" ]; then
    echo "==> Building CA chain PEM..."
    cat "$INTER_DIR/certs/inter.crt" \
        "$ROOT_DIR/certs/ca.crt" \
        > "$INTER_DIR/certs/ca-chain.pem"
    chmod 444 "$INTER_DIR/certs/ca-chain.pem"
else
    echo "--> CA chain already exists, skipping."
fi

# ---------------------------------------------------------------------------
# Cleanup temp config
# ---------------------------------------------------------------------------
rm -f "$ROOT_CNF_TMP"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "======================================================================"
echo " Device CA setup complete."
echo "======================================================================"
echo ""
echo " Files that stay on the server (mounted into Docker containers):"
echo "   $INTER_DIR/private/inter.key   (API container: signs device certs)"
echo "   $INTER_DIR/certs/inter.crt"
echo "   $INTER_DIR/certs/ca-chain.pem  (nginx: verifies client certs)"
echo ""
echo " *** ACTION REQUIRED ***"
echo "   Copy $ROOT_DIR/private/ca.key"
echo "   to an OFFLINE encrypted USB drive, then delete it from this server:"
echo ""
echo "   cp $ROOT_DIR/private/ca.key /path/to/usb/"
echo "   shred -u $ROOT_DIR/private/ca.key"
echo ""
echo " The Root CA cert is safe to keep:"
echo "   $ROOT_DIR/certs/ca.crt"
echo "======================================================================"
