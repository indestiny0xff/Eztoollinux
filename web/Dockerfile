# EZ Tools web UI - build from the repo root:
#   docker build -f web/Dockerfile -t eztools-web .
FROM mcr.microsoft.com/dotnet/runtime:9.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       wget unzip ca-certificates python3 python3-flask gunicorn \
    && rm -rf /var/lib/apt/lists/*

COPY install-eztools.sh allez /tmp/
RUN chmod +x /tmp/install-eztools.sh \
    && SKIP_DOTNET=1 /tmp/install-eztools.sh \
    && rm -f /tmp/install-eztools.sh /tmp/allez

COPY web/app.py /app/app.py
COPY web/static /app/static

WORKDIR /app
EXPOSE 8080
CMD ["gunicorn", "-w", "1", "--threads", "8", "--timeout", "0", "-b", "0.0.0.0:8080", "app:app"]
