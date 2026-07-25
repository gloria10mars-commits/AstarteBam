#!/bin/bash
# NEMESIS API v1.5.4 - Installation compatible 32-bit et 64-bit
# Optimise pour hardware ancien (Pentium M, Celeron M, Atom 32-bit, etc.)
# Detecte l'architecture et installe les bons paquets
# Gere PEP 668 (externally-managed-environment) via venv local

set -e

echo "======================================================="
echo "  NEMESIS API - Installation"
echo "======================================================="
echo ""

# ---------------------------------------------------------------------------
# Detection architecture
# ---------------------------------------------------------------------------
ARCH=$(uname -m)
echo "Architecture detectee: $ARCH"

case "$ARCH" in
    x86_64|amd64)
        ARCH_DEB="amd64"
        ARCH_LABEL="64-bit x86"
        ANCIENT_HW=0
        ;;
    i386|i486|i586)
        ARCH_DEB="i386"
        ARCH_LABEL="32-bit x86 (pre-Pentium-Pro)"
        ANCIENT_HW=1
        ;;
    i686)
        ARCH_DEB="i386"
        ARCH_LABEL="32-bit x86 (Pentium M / Pentium 4 / Atom)"
        ANCIENT_HW=1
        ;;
    armv7l|armhf)
        ARCH_DEB="armhf"
        ARCH_LABEL="32-bit ARM (armhf)"
        ANCIENT_HW=0
        ;;
    aarch64|arm64)
        ARCH_DEB="arm64"
        ARCH_LABEL="64-bit ARM"
        ANCIENT_HW=0
        ;;
    *)
        ARCH_DEB=""
        ARCH_LABEL="$ARCH (architecture non reconnue)"
        ANCIENT_HW=0
        ;;
esac
echo "Label: $ARCH_LABEL"
echo "Paquet Debian: ${ARCH_DEB:-inconnu}"

# Verifier la memoire (warning si < 1GB)
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
MEM_TOTAL_MB=$((MEM_TOTAL_KB / 1024))
echo "Memoire totale: ${MEM_TOTAL_MB} MB"
if [ $MEM_TOTAL_MB -lt 1024 ]; then
    echo "  [!] Memoire faible (< 1GB) - hardware ancien detecte"
    echo "      Le demarrage du serveur sera lent (10-30s) - c'est normal"
    ANCIENT_HW=1
fi
echo ""

# Verifier Python 3
if ! command -v python3 &> /dev/null; then
    echo "[!] Python 3 non trouve"
    echo "    Installe-le: sudo apt install python3 python3-pip python3-venv python3-full"
    exit 1
fi

PY_VER=$(python3 --version 2>&1)
echo "Python: $PY_VER"
echo ""

# ---------------------------------------------------------------------------
# Installation des dependances systeme (xdotool, xclip)
# ---------------------------------------------------------------------------
echo "=== Verification des outils systeme ==="

NEEDS_INSTALL=0
if ! command -v xdotool &> /dev/null; then
    echo "  [!] xdotool absent"
    NEEDS_INSTALL=1
fi
if ! command -v xclip &> /dev/null; then
    echo "  [!] xclip absent"
    NEEDS_INSTALL=1
fi

if [ $NEEDS_INSTALL -eq 1 ]; then
    echo ""
    echo "  Installation de xdotool et xclip pour $ARCH_LABEL..."
    echo "  (sudo requis)"
    echo ""

    if [ "$ARCH" = "x86_64" ] && [ -n "$FORCE_32BIT" ]; then
        echo "  [multiarch] Ajout de l'architecture i386..."
        sudo dpkg --add-architecture i386
        sudo apt-get update -qq
        sudo apt-get install -y xdotool:i386 xclip:i386
    else
        sudo apt-get update -qq 2>/dev/null || true
        sudo apt-get install -y xdotool xclip
    fi
else
    echo "  [OK] xdotool et xclip deja installes"
fi

echo ""
echo "  Versions installees:"
xdotool --version 2>&1 | head -1 | sed 's/^/    xdotool: /'
xclip -version 2>&1 | head -1 | sed 's/^/    xclip: /'
echo ""

# ---------------------------------------------------------------------------
# Dependances Python via venv local (gere PEP 668)
# ---------------------------------------------------------------------------
echo "=== Installation des dependances Python ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Verifier que python3-venv est disponible
if ! python3 -m venv --help &>/dev/null; then
    echo "  [!] python3-venv non disponible"
    echo "    Installe-le: sudo apt install python3-venv python3-full"
    echo ""
    echo "  Fallback: installation systeme avec --break-system-packages"
    if ! pip3 install --break-system-packages --prefer-binary -r requirements.txt; then
        echo "  [!] Echec installation systeme"
        exit 1
    fi
    PIP_INSTALLED_SYSTEM=1
else
    if [ ! -d "$VENV_DIR" ]; then
        echo "  Creation du venv local: $VENV_DIR"
        python3 -m venv "$VENV_DIR"
    else
        echo "  venv existant reutilise: $VENV_DIR"
    fi

    # Activer le venv
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    # Mettre a jour pip dans le venv
    echo "  Mise a jour de pip..."
    pip install --quiet --upgrade pip 2>&1 | tail -1 || true

    # Installer les deps dans le venv
    # Sur hardware ancien (Pentium M sans SSE3), les wheels C peuvent rater
    # On force l'installation en Python pur pour MarkupSafe/charset_normalizer
    echo "  Installation des packages..."
    if [ $ANCIENT_HW -eq 1 ]; then
        echo "  [hardware ancien] Installation en mode Python pur (sans ext C)"
        # D'abord les packages purs
        pip install --quiet flask flask-cors requests 2>&1 | tail -3
        # Pour MarkupSafe: forcer la version Python pure si la C ext rate
        pip install --quiet --no-binary markupsafe markupsafe 2>&1 | tail -2 || true
        # charset_normalizer: tenter binaire, sinon source
        pip install --quiet charset-normalizer 2>&1 | tail -2 || \
            pip install --quiet --no-binary charset-normalizer charset-normalizer
    else
        if ! pip install --prefer-binary -r requirements.txt; then
            echo "  [!] Echec installation - tentative sans --prefer-binary"
            pip install -r requirements.txt
        fi
    fi
fi

echo ""

# Verifier les imports
echo "=== Verification des imports Python ==="
if [ -n "$PIP_INSTALLED_SYSTEM" ]; then
    PY_BIN="python3"
else
    PY_BIN="$VENV_DIR/bin/python"
fi

$PY_BIN -c "
import sys
print(f'  Python: {sys.version}')
print(f'  Platform: {sys.platform}')
print(f'  Executable: {sys.executable}')
import struct
print(f'  Python bits: {struct.calcsize(\"P\") * 8}')
print()

mods = ['flask', 'flask_cors', 'requests']
for m in mods:
    try:
        mod = __import__(m)
        ver = getattr(mod, '__version__', '?')
        print(f'  [OK] {m} {ver} - {mod.__file__}')
    except ImportError as e:
        print(f'  [ECHEC] {m}: {e}')
        sys.exit(1)

print()
print('  --- Deps transitives ---')
for m in ['werkzeug', 'jinja2', 'markupsafe', 'urllib3', 'charset_normalizer']:
    try:
        mod = __import__(m)
        ver = getattr(mod, '__version__', '?')
        print(f'  [OK] {m} {ver}')
    except ImportError as e:
        print(f'  [ECHEC] {m}: {e}')
"

if [ $? -ne 0 ]; then
    echo ""
    echo "[!] Echec verification imports"
    exit 1
fi

echo ""

# ---------------------------------------------------------------------------
# Creer les wrappers (run.sh, run-client.sh) qui activent le venv automatiquement
# ---------------------------------------------------------------------------
if [ -z "$PIP_INSTALLED_SYSTEM" ]; then
    echo "=== Creation des wrappers de lancement ==="

    # Wrapper serveur
    cat > "$SCRIPT_DIR/run-server.sh" << EOF
#!/bin/bash
# Wrapper: lance le serveur NEMESIS dans le venv
cd "\$(dirname "\$0")"
source venv/bin/activate
exec python server.py "\$@"
EOF
    chmod +x "$SCRIPT_DIR/run-server.sh"

    # Wrapper client
    cat > "$SCRIPT_DIR/run-client.sh" << EOF
#!/bin/bash
# Wrapper: lance le client NEMESIS dans le venv
cd "\$(dirname "\$0")"
source venv/bin/activate
exec python client.py "\$@"
EOF
    chmod +x "$SCRIPT_DIR/run-client.sh"

    # Wrapper auto_test
    cat > "$SCRIPT_DIR/run-test.sh" << EOF
#!/bin/bash
cd "\$(dirname "\$0")"
source venv/bin/activate
exec bash auto_test.sh "\$@"
EOF
    chmod +x "$SCRIPT_DIR/run-test.sh"

    echo "  [OK] run-server.sh, run-client.sh, run-test.sh crees"
    echo ""
fi

# ---------------------------------------------------------------------------
# Test xdotool (verification DISPLAY)
# ---------------------------------------------------------------------------
echo "=== Test xdotool ==="
if [ -z "$DISPLAY" ]; then
    echo "  [!] DISPLAY non defini - xdotool ne marchera pas"
    echo "    Tu dois lancer ce script depuis un terminal graphique"
    echo "    (pas depuis SSH/cron/systemd sans DISPLAY)"
else
    echo "  DISPLAY=$DISPLAY"
    if xdotool getactivewindow &>/dev/null; then
        echo "  [OK] xdotool fonctionnel"
    else
        echo "  [!] xdotool ne peut pas acceder a la fenetre active"
    fi
fi

echo ""
echo "======================================================="
echo "  Installation terminee!"
echo "======================================================="
echo ""
if [ -z "$PIP_INSTALLED_SYSTEM" ]; then
    echo "  Demarrage rapide (via wrappers venv):"
    echo "    ./run-server.sh &"
    echo "    ./run-client.sh --health"
    echo "    ./run-client.sh deepseek \"Salut\""
    echo ""
    echo "  OU manuellement (active le venv d'abord):"
    echo "    source venv/bin/activate"
    echo "    python server.py"
    echo "    python client.py --health"
else
    echo "  Demarrage rapide:"
    echo "    python3 server.py &"
    echo "    python3 client.py --health"
    echo "    python3 client.py deepseek \"Salut\""
fi
echo ""
echo "  Test complet:"
echo "    ./run-test.sh   (ou: bash auto_test.sh apres 'source venv/bin/activate')"
echo ""
echo "  Architecture cible: $ARCH_LABEL"
echo "======================================================="
