# EZ Tools on Linux

Run Eric Zimmerman's EZ Tools (forensic command-line suite) natively on Linux, either installed directly on the host or inside a Docker container. Both methods install the .NET 9 runtime and the net9 builds of all 17 CLI tools: AmcacheParser, AppCompatCacheParser, bstrings, EvtxECmd, JLECmd, LECmd, MFTECmd, PECmd, RBCmd, RecentFileCacheParser, RECmd, rla, SBECmd, SQLECmd, SrumECmd, SumECmd, WxTCmd.

Each tool gets a lowercase wrapper command (e.g. `mftecmd`, `evtxecmd`), so no aliases or `dotnet` invocations are needed.

Also included: `allez`, an orchestrator that runs the whole suite against a mounted Windows drive and builds one queryable SQLite database (see below).

## Option 1: Native install

Tested on Ubuntu 24.04. Supports apt and dnf based distributions.

```bash
sudo ./install-eztools.sh
mftecmd --version
```

This installs:
- .NET runtime to `/opt/dotnet` (symlinked as `/usr/local/bin/dotnet`)
- Tools to `/opt/eztools/<Tool>`
- Wrappers to `/usr/local/bin/<tool>`

Configuration via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DOTNET_CHANNEL` | `9.0` | .NET channel to install |
| `NET_VERSION` | `9` | EZ Tools build to download |
| `INSTALL_DIR` | `/opt/eztools` | Tool extraction directory |
| `DOTNET_DIR` | `/opt/dotnet` | .NET install directory |
| `BIN_DIR` | `/usr/local/bin` | Wrapper location |
| `SKIP_DOTNET` | `0` | Set to `1` if dotnet is already on PATH |

## Option 2: Docker

```bash
docker build -t eztools .
```

Run a tool against evidence on the host by mounting it into `/data` (the working directory):

```bash
docker run --rm -v "$(pwd):/data" eztools mftecmd -f '$MFT' --csv /data/out
```

Or start an interactive shell:

```bash
docker run --rm -it -v "$(pwd):/data" eztools
```

## Option 3: Web UI

A browser front end for the whole suite: pick a tool, upload evidence or browse a mounted folder, keep the default arguments or add your own, and the CSV/JSON output is rendered as a searchable, sortable table directly in the page.

```bash
docker compose up -d --build
```

Then open http://eztoollinux.localhost - browsers resolve any `*.localhost` name to 127.0.0.1, and compose binds port 80, so the short address works with no DNS or hosts-file setup. (If port 80 is taken, change the mapping in `docker-compose.yml` and use http://eztoollinux.localhost:8080.)

Evidence placed in the `./data` folder next to `docker-compose.yml` appears under "Browse /data" in the page, which avoids uploading large files like an $MFT. Uploads work too (up to 8 GB).

Features:
- All 17 CLI tools, each with its expected input and supported output formats
- Live preview of the exact command that will run
- CSV and JSON results as a paginated table with full-text search, match highlighting, and column sorting (handled server side, so large outputs stay fast)
- Raw file downloads and the full tool log for every run
- Built-in command-line help viewer per tool, for checking every available option
- Known Windows artifact locations shown for every tool, so you know where inputs live
- ALLEZ as a tool in the page: point it at a mounted drive under /data and it runs the whole suite
- SQL console on every run: outputs become a SQLite database with a schema explorer (tables, columns, row counts) and a query editor with autocompletion for SQL keywords, table names, and column names (Ctrl+Enter to run; queries are read-only)

To reach it from another machine on your network, add a line like `192.168.1.x eztoollinux.lan` to that machine's hosts file, or just use the server's IP.

Without compose: `docker build -f web/Dockerfile -t eztools-web .` then `docker run -d -p 80:8080 -v /path/to/evidence:/data eztools-web`.

## allez: run everything, query everything

`allez` (installed by both the script and the Docker images) takes the root of a mounted image or copied `C:\` drive, finds every artifact in its known location automatically - `$MFT`, event logs, Prefetch, Amcache, ShimCache, registry hives, SRUM, SUM, Recycle Bin, and the per-user artifacts (shortcuts, jump lists, timeline, shellbags) for every user profile - runs the matching tool on each, and loads all resulting CSVs into a single SQLite database:

```bash
allez -s /mnt/image -o /cases/output
sqlite3 /cases/output/allez.db "SELECT name FROM sqlite_master WHERE type='table'"
```

Service account profiles (`Windows\ServiceProfiles\*`) are parsed like user profiles, and every table gets a `username` column derived from the row's source path, so per-account filtering is `WHERE username = 'someuser'`.

Artifacts that are not present are skipped and reported. `--no-db` skips the database step; the full tool output lands in `allez.log`.

By default the scan is fast: it targets known database files and parses staged copies of the user hives (seconds to minutes). Add `-e` for the exhaustive mode, which sweeps whole directories (`AppData\Local\Packages`, full browser profiles, all of `Users`) and can take 10+ minutes per user on a real system because every cache file gets probed.

## Usage examples

```bash
# Parse an MFT to CSV (quote $MFT so the shell does not expand it)
mftecmd -f '$MFT' --csv /tmp/out

# Parse Windows event logs
evtxecmd -f Security.evtx --csv /tmp/out

# Parse prefetch files
pecmd -d C:/Windows/Prefetch --csv /tmp/out
```

Run any tool with `-h` for its full options.

## References

- Tool documentation and downloads: https://ericzimmerman.github.io
- Based on: https://www.sans.org/blog/running-ez-tools-natively-on-linux
