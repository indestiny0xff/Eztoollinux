# Eztoollinux

Installers for running Eric Zimmerman's EZ Tools (forensic CLI suite) natively on Linux.

## Layout
- `allez` - bash orchestrator (no extension, LF-pinned in .gitattributes): discovers artifacts by known Windows paths (case-insensitive `find -ipath`, per-user loops) under a mounted drive root, runs each tool with `--csv`, imports all CSVs into `allez.db` via the sqlite3 CLI (`.import`, `--skip 1` for appends). Installed by install-eztools.sh (copied from alongside, or fetched from GitHub raw); needs sqlite3 (added to installer deps).
- `install-eztools.sh` - bash installer: installs the .NET runtime, downloads the net9 builds of all CLI tools to `/opt/eztools`, and creates lowercase wrapper commands in `/usr/local/bin` (e.g. `mftecmd`). Configurable via env vars (`DOTNET_CHANNEL`, `NET_VERSION`, `INSTALL_DIR`, `SKIP_DOTNET`).
- `Dockerfile` - CLI image on `mcr.microsoft.com/dotnet/runtime:9.0`, reuses `install-eztools.sh` with `SKIP_DOTNET=1`.
- `web/` - web UI image (separate feature, keep the CLI image intact): Flask backend (`app.py`) with a job runner and server-side table API (search/sort/pagination for CSV/JSONL outputs), vanilla JS frontend in `static/`, `web/Dockerfile` built from repo root context. `docker-compose.yml` binds 80:8080 so http://eztoollinux.localhost works; `./data` mounts to `/data` for the in-page evidence browser. Also: per-tool `--help` viewer, KNOWN_PATHS per tool shown in the UI, ALLEZ exposed as a tool (`runner: "allez"`, dir input only), and a SQL console per job - `/api/jobs/<id>/db` builds/loads a SQLite db (reuses allez.db when present, table names match allez's `table_name_for`), `/db/query` executes read-only SQL (mode=ro + query_only), frontend has a schema explorer and autocomplete (keywords + table + column names).

## Conventions
- SQLECmd's zip ships only the Windows SQLite.Interop.dll; the installer downloads the matching Linux native build (version grepped from the bundle) from the Stub.System.Data.SQLite.Core.NetStandard NuGet package and symlinks libSQLite.Interop.dll.so next to SQLECmd.dll. Without it SQLECmd throws EntryPointNotFoundException on every database.
- Table naming in allez and web (keep in sync: allez sed pipeline == app.py table_name_for): strip timestamp prefix, lowercase, [a-z0-9_], strip SQLECmd's trailing run UUID so tables merge across users/runs.
- Tool zips come from `https://download.ericzimmermanstools.com/net<version>/<Tool>.zip`; archive layouts and dll casing vary, so the script locates dlls with `find -iname`.
- Keep the script POSIX-bash, `set -euo pipefail`, root-required.
- Verify changes by building the Docker image and running a tool with `--version`.
- README: no emoji, concise. Commits: no AI attribution lines.
