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
