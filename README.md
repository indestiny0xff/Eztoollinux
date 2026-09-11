# EZ Tools on Linux

Run Eric Zimmerman's EZ Tools (forensic command-line suite) natively on Linux, either installed directly on the host or inside a Docker container. Both methods install the .NET 9 runtime and the net9 builds of all 17 CLI tools: AmcacheParser, AppCompatCacheParser, bstrings, EvtxECmd, JLECmd, LECmd, MFTECmd, PECmd, RBCmd, RecentFileCacheParser, RECmd, rla, SBECmd, SQLECmd, SrumECmd, SumECmd, WxTCmd.

Each tool gets a lowercase wrapper command (e.g. `mftecmd`, `evtxecmd`), so no aliases or `dotnet` invocations are needed.

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

To reach it from another machine on your network, add a line like `192.168.1.x eztoollinux.lan` to that machine's hosts file, or just use the server's IP.

Without compose: `docker build -f web/Dockerfile -t eztools-web .` then `docker run -d -p 80:8080 -v /path/to/evidence:/data eztools-web`.

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
