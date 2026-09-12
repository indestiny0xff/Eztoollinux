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
command -v wget    >/dev/null 2>&1 || missing+=(wget)
command -v unzip   >/dev/null 2>&1 || missing+=(unzip)
command -v sqlite3 >/dev/null 2>&1 || missing+=(sqlite3)
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
  # Pin to the runtime we just installed, not whatever is first on PATH
  DOTNET_BIN="$DOTNET_DIR/dotnet"
else
  DOTNET_BIN="$(command -v dotnet || true)"
  [[ -n "$DOTNET_BIN" ]] || die "SKIP_DOTNET=1 but dotnet not found on PATH."
fi

DOTNET_ROOT_DIR="$(dirname "$(readlink -f "$DOTNET_BIN")")"

# The net${NET_VERSION} tool builds require that major runtime version
if ! "$DOTNET_BIN" --list-runtimes 2>/dev/null \
    | grep -q "Microsoft.NETCore.App ${NET_VERSION}\."; then
  die "dotnet at ${DOTNET_BIN} does not have the .NET ${NET_VERSION} runtime. \
Re-run without SKIP_DOTNET, or install .NET ${NET_VERSION} first."
fi
log ".NET runtime: $("$DOTNET_BIN" --list-runtimes | grep "Microsoft.NETCore.App ${NET_VERSION}\." | head -n1)"

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
export DOTNET_ROOT="${DOTNET_ROOT_DIR}"
exec "${DOTNET_BIN}" "${dll}" "\$@"
EOF
  chmod +x "${BIN_DIR}/${name}"
  installed+=("$name")
done

# --- SQLECmd Linux native library --------------------------------------------
# The zip ships only the Windows SQLite.Interop.dll; fetch the matching Linux
# build from the official System.Data.SQLite NuGet package.
sqle_dll="$(find "$INSTALL_DIR/SQLECmd" -iname 'SQLECmd.dll' 2>/dev/null | head -n1)"
if [[ -n "$sqle_dll" ]]; then
  sqle_dir="$(dirname "$sqle_dll")"
  sds_ver="$(grep -aoE '1\.0\.1[0-9]{2}' "$sqle_dll" | sort -u | head -n1)"
  sds_ver="${sds_ver:-1.0.119}"
  case "$(uname -m)" in
    aarch64|arm64) sds_rid="linux-arm64" ;;
    *)             sds_rid="linux-x64" ;;
  esac
  if wget -q "https://www.nuget.org/api/v2/package/Stub.System.Data.SQLite.Core.NetStandard/${sds_ver}" \
       -O /tmp/sds.nupkg \
     && unzip -o -q /tmp/sds.nupkg -d /tmp/sds "runtimes/${sds_rid}/native/*" \
     && cp "/tmp/sds/runtimes/${sds_rid}/native/SQLite.Interop.dll" "$sqle_dir/"; then
    ln -sf "$sqle_dir/SQLite.Interop.dll" "$sqle_dir/libSQLite.Interop.dll.so"
    log "SQLECmd: installed Linux SQLite interop ${sds_ver} (${sds_rid})"
  else
    warn "SQLECmd: could not install the Linux SQLite interop; SQLECmd will fail to parse databases."
  fi
  rm -rf /tmp/sds.nupkg /tmp/sds
fi

# --- allez orchestrator ------------------------------------------------------
# Runs every tool against a mounted Windows root and builds a SQLite database.
allez_src="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/allez"
if [[ -f "$allez_src" ]]; then
  install -m 0755 "$allez_src" "$BIN_DIR/allez"
  installed+=(allez)
elif wget -q https://raw.githubusercontent.com/indestiny0xff/Eztoollinux/main/allez \
    -O "$BIN_DIR/allez"; then
  chmod +x "$BIN_DIR/allez"
  installed+=(allez)
else
  rm -f "$BIN_DIR/allez"
  warn "Could not install allez (not found next to this script, download failed)."
fi

# --- summary ----------------------------------------------------------------
echo
log "Installed ${#installed[@]}/${#TOOLS[@]} tools to ${INSTALL_DIR}"
log "Commands available: ${installed[*]}"
[[ ${#failed[@]} -eq 0 ]] || warn "Failed: ${failed[*]}"
log "Example: mftecmd -f '\$MFT' --csv /tmp/out"
