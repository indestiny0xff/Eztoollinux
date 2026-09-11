# EZ Tools on Linux - .NET runtime image with all command-line tools installed
FROM mcr.microsoft.com/dotnet/runtime:9.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends wget unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY install-eztools.sh allez /tmp/
RUN chmod +x /tmp/install-eztools.sh \
    && SKIP_DOTNET=1 /tmp/install-eztools.sh \
    && rm -f /tmp/install-eztools.sh /tmp/allez

WORKDIR /data
CMD ["bash"]
