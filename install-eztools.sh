#!/usr/bin/env bash
#
# install-eztools.sh
# Installs the .NET runtime and Eric Zimmerman's EZ Tools (command-line suite)
# natively on Linux, with a wrapper command for each tool in /usr/local/bin.
#
# Usage: sudo ./install-eztools.sh
#
# Environment overrides:
#   DOTNET_CHANNEL  .NET channel to install            (default: 9.0)
#   NET_VERSION     EZ Tools build to download          (default: 9)
#   INSTALL_DIR     where tools are extracted           (default: /opt/eztools)
#   DOTNET_DIR      where .NET is installed             (default: /opt/dotnet)
#   BIN_DIR         where wrappers are created          (default: /usr/local/bin)
#   SKIP_DOTNET=1   skip the .NET install (already present on PATH)

set -euo pipefail

DOTNET_CHANNEL="${DOTNET_CHANNEL:-9.0}"
NET_VERSION="${NET_VERSION:-9}"
INSTALL_DIR="${INSTALL_DIR:-/opt/eztools}"
DOTNET_DIR="${DOTNET_DIR:-/opt/dotnet}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
BASE_URL="https://download.ericzimmermanstools.com/net${NET_VERSION}"

# Command-line tools from https://ericzimmerman.github.io (GUI tools excluded)
TOOLS=(
  AmcacheParser
  AppCompatCacheParser
  bstrings
  EvtxECmd
  JLECmd
  LECmd
  MFTECmd
  PECmd
  RBCmd
  RecentFileCacheParser
  RECmd
  rla
  SBECmd
  SQLECmd
  SrumECmd
  SumECmd
  WxTCmd
)

log()  { printf '[+] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }
die()  { printf '[x] %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (sudo ./install-eztools.sh)."

# --- dependencies -----------------------------------------------------------
install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q "$@"
  else
    die "Unsupported package manager. Install manually: $*"
  fi
}

missing=()
command -v wget  >/dev/null 2>&1 || missing+=(wget)
command -v unzip >/dev/null 2>&1 || missing+=(unzip)
if [[ ${#missing[@]} -gt 0 ]]; then
  log "Installing dependencies: ${missing[*]}"
  install_packages ca-certificates "${missing[@]}"
fi

# --- .NET runtime -----------------------------------------------------------
if [[ "${SKIP_DOTNET:-0}" != "1" ]]; then
  log "Installing .NET ${DOTNET_CHANNEL} to ${DOTNET_DIR}"
  if command -v apt-get >/dev/null 2>&1; then
    install_packages libicu-dev
  elif command -v dnf >/dev/null 2>&1; then
    install_packages libicu
  fi
  wget -q https://builds.dotnet.microsoft.com/dotnet/scripts/v1/dotnet-install.sh \
    -O /tmp/dotnet-install.sh
  chmod +x /tmp/dotnet-install.sh
  /tmp/dotnet-install.sh --channel "$DOTNET_CHANNEL" --runtime dotnet \
    --install-dir "$DOTNET_DIR"
  rm -f /tmp/dotnet-install.sh
  ln -sf "$DOTNET_DIR/dotnet" "$BIN_DIR/dotnet"
fi

DOTNET_BIN="$(command -v dotnet || true)"
[[ -n "$DOTNET_BIN" ]] || die "dotnet not found on PATH."
log ".NET runtime: $("$DOTNET_BIN" --list-runtimes | head -n1)"

# --- EZ Tools ---------------------------------------------------------------
mkdir -p "$INSTALL_DIR"
installed=() failed=()

for tool in "${TOOLS[@]}"; do
  log "Downloading ${tool}"
  if ! wget -q "${BASE_URL}/${tool}.zip" -O "/tmp/${tool}.zip"; then
    warn "Download failed for ${tool}, skipping."
    failed+=("$tool")
    continue
  fi
  rm -rf "${INSTALL_DIR:?}/${tool}"
  unzip -qo "/tmp/${tool}.zip" -d "${INSTALL_DIR}/${tool}"
  rm -f "/tmp/${tool}.zip"

  # Archive layouts vary (flat vs nested, casing differs) - locate the dll
  dll="$(find "${INSTALL_DIR}/${tool}" -iname "${tool}.dll" | head -n1)"
  if [[ -z "$dll" ]]; then
    warn "Could not locate ${tool}.dll, skipping wrapper."
    failed+=("$tool")
    continue
  fi

  name="$(printf '%s' "$tool" | tr '[:upper:]' '[:lower:]')"
  cat > "${BIN_DIR}/${name}" <<EOF
#!/usr/bin/env bash
exec "${DOTNET_BIN}" "${dll}" "\$@"
EOF
  chmod +x "${BIN_DIR}/${name}"
  installed+=("$name")
done

# --- summary ----------------------------------------------------------------
echo
log "Installed ${#installed[@]}/${#TOOLS[@]} tools to ${INSTALL_DIR}"
log "Commands available: ${installed[*]}"
[[ ${#failed[@]} -eq 0 ]] || warn "Failed: ${failed[*]}"
log "Example: mftecmd -f '\$MFT' --csv /tmp/out"
