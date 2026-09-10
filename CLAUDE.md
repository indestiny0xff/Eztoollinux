# Eztoollinux

Installers for running Eric Zimmerman's EZ Tools (forensic CLI suite) natively on Linux.

## Layout
- `install-eztools.sh` - bash installer: installs the .NET runtime, downloads the net9 builds of all CLI tools to `/opt/eztools`, and creates lowercase wrapper commands in `/usr/local/bin` (e.g. `mftecmd`). Configurable via env vars (`DOTNET_CHANNEL`, `NET_VERSION`, `INSTALL_DIR`, `SKIP_DOTNET`).
- `Dockerfile` - builds on `mcr.microsoft.com/dotnet/runtime:9.0` and reuses `install-eztools.sh` with `SKIP_DOTNET=1`.

## Conventions
- Tool zips come from `https://download.ericzimmermanstools.com/net<version>/<Tool>.zip`; archive layouts and dll casing vary, so the script locates dlls with `find -iname`.
- Keep the script POSIX-bash, `set -euo pipefail`, root-required.
- Verify changes by building the Docker image and running a tool with `--version`.
- README: no emoji, concise. Commits: no AI attribution lines.
