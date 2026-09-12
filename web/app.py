#!/usr/bin/env python3
"""EZ Tools web UI - Flask backend.

Wraps the EZ Tools CLI wrappers installed by install-eztools.sh with a small
job runner and a server-side table API so large CSV/JSON outputs can be
searched, sorted, and paginated in the browser without shipping the whole
file to the client.
"""

import csv as csvmod
import glob
import json
import os
import re
import shlex
import sqlite3
import subprocess
import threading
import uuid

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

APP_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.environ.get("JOBS_DIR", "/tmp/eztools-jobs")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
EZTOOLS_DIR = os.environ.get("EZTOOLS_DIR", "/opt/eztools")
MAX_TABLE_ROWS = 200_000
STDOUT_CAP = 100_000

app = Flask(__name__, static_folder=os.path.join(APP_DIR, "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024 * 1024  # 8 GB uploads

# input: "file" (single file, -f), "dir" (-d), "either" (single file -f, several -d)
# outputs: csv/json rendered as tables, stdout captured, files = raw downloads
TOOLS = [
    {"id": "mftecmd", "cmd": "mftecmd", "name": "MFTECmd",
     "desc": "NTFS metadata parser: $MFT, $J, $Boot, $SDS, $LogFile",
     "input": "file", "hint": "$MFT, $J, $Boot, $SDS", "outputs": ["csv", "json"]},
    {"id": "evtxecmd", "cmd": "evtxecmd", "name": "EvtxECmd",
     "desc": "Windows event log parser with crowd-sourced maps",
     "input": "either", "hint": ".evtx files", "outputs": ["csv", "json"]},
    {"id": "pecmd", "cmd": "pecmd", "name": "PECmd",
     "desc": "Prefetch parser - evidence of execution",
     "input": "either", "hint": ".pf files", "outputs": ["csv", "json"]},
    {"id": "recmd", "cmd": "recmd", "name": "RECmd",
     "desc": "Registry hive parser (Kroll batch export by default)",
     "input": "either", "hint": "SYSTEM, SOFTWARE, NTUSER.DAT, ...",
     "outputs": ["csv"], "preargs": "recmd_batch"},
    {"id": "lecmd", "cmd": "lecmd", "name": "LECmd",
     "desc": "Shortcut (.lnk) file parser",
     "input": "either", "hint": ".lnk files", "outputs": ["csv", "json"]},
    {"id": "jlecmd", "cmd": "jlecmd", "name": "JLECmd",
     "desc": "Jump list parser (automatic and custom destinations)",
     "input": "either", "hint": "*.automaticDestinations-ms", "outputs": ["csv", "json"]},
    {"id": "amcacheparser", "cmd": "amcacheparser", "name": "AmcacheParser",
     "desc": "Amcache.hve parser - evidence of execution",
     "input": "file", "hint": "Amcache.hve", "outputs": ["csv"]},
    {"id": "appcompatcacheparser", "cmd": "appcompatcacheparser", "name": "AppCompatCacheParser",
     "desc": "ShimCache parser from a SYSTEM hive",
     "input": "file", "hint": "SYSTEM hive", "outputs": ["csv"]},
    {"id": "bstrings", "cmd": "bstrings", "name": "bstrings",
     "desc": "String extraction and regex search in any file",
     "input": "file", "hint": "any binary file", "outputs": ["stdout"]},
    {"id": "rbcmd", "cmd": "rbcmd", "name": "RBCmd",
     "desc": "Recycle Bin artifact parser ($I files, INFO2)",
     "input": "either", "hint": "$I****** files", "outputs": ["csv"]},
    {"id": "recentfilecacheparser", "cmd": "recentfilecacheparser", "name": "RecentFileCacheParser",
     "desc": "RecentFileCache.bcf parser",
     "input": "file", "hint": "RecentFileCache.bcf", "outputs": ["csv", "json"]},
    {"id": "sbecmd", "cmd": "sbecmd", "name": "SBECmd",
     "desc": "ShellBags parser from user registry hives",
     "input": "dir", "hint": "folder with NTUSER.DAT / UsrClass.dat", "outputs": ["csv"]},
    {"id": "sqlecmd", "cmd": "sqlecmd", "name": "SQLECmd",
     "desc": "SQLite database parser with bundled maps",
     "input": "either", "hint": ".db / .sqlite files", "outputs": ["csv"]},
    {"id": "srumecmd", "cmd": "srumecmd", "name": "SrumECmd",
     "desc": "SRUM parser - app/network usage history",
     "input": "either", "hint": "SRUDB.dat (+ SOFTWARE hive)", "outputs": ["csv"]},
    {"id": "sumecmd", "cmd": "sumecmd", "name": "SumECmd",
     "desc": "User Access Logging (SUM) parser",
     "input": "dir", "hint": "folder with Current.mdb / SystemIdentity.mdb", "outputs": ["csv"]},
    {"id": "wxtcmd", "cmd": "wxtcmd", "name": "WxTCmd",
     "desc": "Windows Timeline parser (ActivitiesCache.db)",
     "input": "file", "hint": "ActivitiesCache.db", "outputs": ["csv"]},
    {"id": "rla", "cmd": "rla", "name": "rla",
     "desc": "Replay registry transaction logs into a clean hive",
     "input": "either", "hint": "hive + .LOG1/.LOG2", "outputs": ["files"], "outflag": "--out"},
    {"id": "allez", "cmd": "allez", "name": "ALLEZ",
     "desc": "Run every tool against a mounted Windows root, auto-discover all artifacts, build one SQLite database",
     "input": "dir", "hint": "root of a mounted image or copied C:\\ drive (contains Windows\\, Users\\)",
     "outputs": ["db"], "runner": "allez"},
]
TOOLS_BY_ID = {t["id"]: t for t in TOOLS}

# Known Windows locations for each tool's input, shown in the UI.
# <user> means the artifact exists per user profile (allez checks every user).
KNOWN_PATHS = {
    "mftecmd": [r"C:\$MFT", r"C:\$Extend\$J", r"C:\$Boot", r"C:\$Secure ($SDS)"],
    "evtxecmd": [r"C:\Windows\System32\winevt\Logs"],
    "pecmd": [r"C:\Windows\Prefetch"],
    "recmd": [r"C:\Windows\System32\config (SYSTEM, SOFTWARE, SAM, SECURITY)",
              r"C:\Users\<user>\NTUSER.DAT",
              r"C:\Users\<user>\AppData\Local\Microsoft\Windows\UsrClass.dat",
              r"C:\Windows\ServiceProfiles\<account>\NTUSER.DAT (+ UsrClass.dat)"],
    "lecmd": [r"C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Recent",
              r"C:\Users\<user>\Desktop",
              r"C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu",
              r"C:\ProgramData\Microsoft\Windows\Start Menu"],
    "jlecmd": [r"C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Recent\AutomaticDestinations",
               r"C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Recent\CustomDestinations"],
    "amcacheparser": [r"C:\Windows\appcompat\Programs\Amcache.hve"],
    "appcompatcacheparser": [r"C:\Windows\System32\config\SYSTEM"],
    "bstrings": [r"any file (memory dumps, unknown binaries, pagefile.sys, ...)"],
    "rbcmd": [r"C:\$Recycle.Bin\<SID>\$I******"],
    "recentfilecacheparser": [r"C:\Windows\AppCompat\Programs\RecentFileCache.bcf"],
    "sbecmd": [r"C:\Users\<user>\NTUSER.DAT",
               r"C:\Users\<user>\AppData\Local\Microsoft\Windows\UsrClass.dat",
               r"C:\Windows\ServiceProfiles\<account>\ (same hives, service accounts)"],
    "sqlecmd": [r"C:\Users\<user>\AppData\Local\Google\Chrome\User Data\Default\History (also Edge, Brave, Vivaldi, Opera)",
                r"C:\Users\<user>\AppData\Roaming\Mozilla\Firefox\Profiles\<profile>\places.sqlite",
                r"C:\Users\<user>\AppData\Local\Microsoft\Windows\Notifications\wpndatabase.db",
                r"C:\Users\<user>\AppData\Local\Packages\<app>\... (store app databases)"],
    "srumecmd": [r"C:\Windows\System32\sru\SRUDB.dat",
                 r"C:\Windows\System32\config\SOFTWARE (optional, -r)"],
    "sumecmd": [r"C:\Windows\System32\LogFiles\Sum"],
    "wxtcmd": [r"C:\Users\<user>\AppData\Local\ConnectedDevicesPlatform\<id>\ActivitiesCache.db"],
    "rla": [r"C:\Windows\System32\config (hive + .LOG1/.LOG2 pairs)"],
    "allez": [r"point it at the ROOT of the mounted image / copied drive - it checks every known path above, for every user profile",
              r"default: fast targeted scan; add -e in extra arguments for the exhaustive sweep (Packages, browser profile dirs, whole Users) - much slower"],
}

JOBS = {}        # id -> job dict
JOBS_LOCK = threading.Lock()
TABLE_CACHE = {} # path -> (mtime, headers, rows, truncated)
HELP_CACHE = {}  # tool id -> --help output


def sanitize_name(name):
    """Keep forensic filenames like $MFT intact, drop path tricks."""
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r"[^A-Za-z0-9$._\- ]", "_", name).strip()
    return name or "file"


def recmd_batch():
    rebs = sorted(glob.glob(os.path.join(EZTOOLS_DIR, "RECmd", "**", "*.reb"), recursive=True))
    kroll = [r for r in rebs if "kroll" in r.lower()]
    return (kroll or rebs or [None])[0]


def build_command(tool, input_path, input_is_dir, fmt, extra_args, out_dir):
    if tool.get("runner") == "allez":
        cmd = ["allez", "-s", input_path, "-o", out_dir]
        if extra_args:
            cmd += shlex.split(extra_args)
        return cmd
    cmd = [tool["cmd"]]
    if tool.get("preargs") == "recmd_batch":
        batch = recmd_batch()
        if batch and "--bn" not in extra_args:
            cmd += ["--bn", batch]
    cmd += (["-d", input_path] if input_is_dir else ["-f", input_path])
    if fmt == "csv":
        cmd += ["--csv", out_dir]
    elif fmt == "json":
        cmd += ["--json", out_dir]
    elif fmt == "files":
        cmd += [tool.get("outflag", "--out"), out_dir]
    if extra_args:
        cmd += shlex.split(extra_args)
    return cmd


def run_job(job_id):
    job = JOBS[job_id]
    try:
        proc = subprocess.run(
            job["cmd"], cwd=job["out_dir"], timeout=3600,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        job["returncode"] = proc.returncode
        job["stdout"] = proc.stdout[-STDOUT_CAP:]
        job["status"] = "done" if proc.returncode == 0 else "error"
    except subprocess.TimeoutExpired:
        job["status"] = "error"
        job["stdout"] = "Timed out after 1 hour."
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        job["stdout"] = str(exc)
    files = []
    for root, _dirs, names in os.walk(job["out_dir"]):
        for name in names:
            full = os.path.join(root, name)
            files.append({
                "name": os.path.relpath(full, job["out_dir"]).replace("\\", "/"),
                "size": os.path.getsize(full),
            })
    job["files"] = sorted(files, key=lambda f: f["name"])


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/tools")
def api_tools():
    return jsonify([dict(
        {k: t[k] for k in ("id", "name", "desc", "input", "hint", "outputs")},
        runner=t.get("runner", ""), paths=KNOWN_PATHS.get(t["id"], []))
        for t in TOOLS])


@app.get("/api/tools/<tool_id>/help")
def api_tool_help(tool_id):
    tool = TOOLS_BY_ID.get(tool_id) or abort(404)
    if tool_id not in HELP_CACHE:
        try:
            proc = subprocess.run(
                [tool["cmd"], "--help"], timeout=60,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
            HELP_CACHE[tool_id] = proc.stdout[:STDOUT_CAP]
        except Exception as exc:  # noqa: BLE001
            return jsonify({"help": "Could not load help: " + str(exc)})
    return jsonify({"help": HELP_CACHE[tool_id]})


@app.get("/api/browse")
def api_browse():
    """List a directory under DATA_DIR so mounted evidence can be picked."""
    rel = request.args.get("path", "").strip().lstrip("/")
    base = os.path.realpath(DATA_DIR)
    path = os.path.realpath(os.path.join(base, rel))
    if not (path == base or path.startswith(base + os.sep)):
        abort(400, "Path must stay under /data")
    if not os.path.isdir(path):
        return jsonify({"error": "No /data volume mounted or path not found",
                        "path": rel, "entries": []})
    entries = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            entries.append({"name": name, "dir": os.path.isdir(full),
                            "size": 0 if os.path.isdir(full) else os.path.getsize(full)})
    except PermissionError:
        abort(403, "Permission denied")
    return jsonify({"path": rel, "entries": entries[:2000]})


@app.post("/api/run")
def api_run():
    tool = TOOLS_BY_ID.get(request.form.get("tool", ""))
    if not tool:
        abort(400, "Unknown tool")
    fmt = request.form.get("format") or tool["outputs"][0]
    if fmt not in tool["outputs"]:
        abort(400, "Format not supported by this tool")
    extra_args = request.form.get("args", "").strip()

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(JOBS_DIR, job_id)
    in_dir = os.path.join(job_dir, "input")
    out_dir = os.path.join(job_dir, "output")
    os.makedirs(in_dir)
    os.makedirs(out_dir)

    uploads = [f for f in request.files.getlist("files") if f.filename]
    server_path = request.form.get("path", "").strip()

    if uploads:
        for f in uploads:
            f.save(os.path.join(in_dir, sanitize_name(f.filename)))
        if len(uploads) == 1 and tool["input"] != "dir":
            input_path = os.path.join(in_dir, sanitize_name(uploads[0].filename))
            input_is_dir = False
        else:
            if tool["input"] == "file":
                abort(400, f"{tool['name']} takes a single file")
            input_path, input_is_dir = in_dir, True
    elif server_path:
        base = os.path.realpath(DATA_DIR)
        input_path = os.path.realpath(os.path.join(base, server_path.lstrip("/")))
        if not (input_path == base or input_path.startswith(base + os.sep)):
            abort(400, "Server path must stay under /data")
        if not os.path.exists(input_path):
            abort(400, "Server path not found")
        input_is_dir = os.path.isdir(input_path)
        if input_is_dir and tool["input"] == "file":
            abort(400, f"{tool['name']} takes a single file, not a folder")
        if not input_is_dir and tool["input"] == "dir":
            abort(400, f"{tool['name']} takes a folder, not a file")
    else:
        abort(400, "Provide an upload or a /data path")

    cmd = build_command(tool, input_path, input_is_dir, fmt, extra_args, out_dir)
    job = {"id": job_id, "tool": tool["id"], "cmd": cmd, "cmdline": shlex.join(cmd),
           "format": fmt, "status": "running", "stdout": "", "returncode": None,
           "files": [], "out_dir": out_dir}
    with JOBS_LOCK:
        JOBS[job_id] = job
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return jsonify({"id": job_id, "cmdline": job["cmdline"]})


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    job = JOBS.get(job_id) or abort(404)
    return jsonify({k: job[k] for k in
                    ("id", "tool", "cmdline", "format", "status", "stdout", "returncode", "files")})


def job_file(job_id, name):
    job = JOBS.get(job_id) or abort(404)
    full = os.path.realpath(os.path.join(job["out_dir"], name))
    base = os.path.realpath(job["out_dir"])
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        abort(404)
    return full


@app.get("/api/jobs/<job_id>/download")
def api_download(job_id):
    full = job_file(job_id, request.args.get("file", ""))
    return send_file(full, as_attachment=True, download_name=os.path.basename(full))


def load_table(path):
    """Parse CSV/TSV/JSONL into (headers, rows); cached by mtime."""
    mtime = os.path.getmtime(path)
    cached = TABLE_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1], cached[2], cached[3]

    headers, rows, truncated = [], [], False
    lower = path.lower()
    if lower.endswith((".json", ".jsonl")):
        seen = {}
        objs = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                objs.append(obj)
                for key in obj:
                    seen.setdefault(key, None)
                if len(objs) >= MAX_TABLE_ROWS:
                    truncated = True
                    break
        headers = list(seen)
        for obj in objs:
            rows.append([obj.get(h, "") if isinstance(obj.get(h, ""), str)
                         else json.dumps(obj.get(h, ""), ensure_ascii=False)
                         for h in headers])
    else:
        delim = "\t" if lower.endswith(".tsv") else ","
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csvmod.reader(fh, delimiter=delim)
            for i, rec in enumerate(reader):
                if i == 0:
                    headers = rec
                else:
                    rows.append(rec)
                    if len(rows) >= MAX_TABLE_ROWS:
                        truncated = True
                        break

    if len(TABLE_CACHE) >= 2:
        TABLE_CACHE.pop(next(iter(TABLE_CACHE)))
    TABLE_CACHE[path] = (mtime, headers, rows, truncated)
    return headers, rows, truncated


@app.get("/api/jobs/<job_id>/table")
def api_table(job_id):
    full = job_file(job_id, request.args.get("file", ""))
    if not full.lower().endswith((".csv", ".tsv", ".json", ".jsonl")):
        abort(400, "Not a tabular file")
    headers, rows, truncated = load_table(full)

    q = request.args.get("q", "").strip().lower()
    if q:
        rows = [r for r in rows if any(q in c.lower() for c in r)]

    sort = request.args.get("sort", "")
    if sort.isdigit() and headers and int(sort) < len(headers):
        col = int(sort)
        rev = request.args.get("dir", "asc") == "desc"

        def key(row):
            val = row[col] if col < len(row) else ""
            try:
                return (0, float(val), "")
            except ValueError:
                return (1, 0.0, val.lower())
        rows = sorted(rows, key=key, reverse=rev)

    offset = max(0, int(request.args.get("offset", 0)))
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    return jsonify({"headers": headers, "rows": rows[offset:offset + limit],
                    "filtered": len(rows), "truncated": truncated})


def table_name_for(filename):
    """Match allez's naming: strip timestamp prefix, lowercase, [a-z0-9_]."""
    base = os.path.splitext(os.path.basename(filename))[0]
    base = re.sub(r"^[0-9]{8,}_", "", base)
    name = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]", "_", base.lower())).strip("_")
    # SQLECmd appends a random UUID per run; drop it so tables merge
    name = re.sub(r"_[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}$", "", name)
    if not name:
        name = "results"
    if name[0].isdigit():
        name = "t_" + name
    return name


def build_job_db(job):
    """Return the path of the job's SQLite db, building it from outputs if needed."""
    out_dir = job["out_dir"]
    for f in job["files"]:  # a run (like allez) may already ship a database
        if f["name"].lower().endswith(".db"):
            return os.path.join(out_dir, f["name"])
    db_path = os.path.join(out_dir, "results.db")
    if os.path.exists(db_path):
        return db_path
    conn = sqlite3.connect(db_path)
    try:
        for f in job["files"]:
            if not f["name"].lower().endswith((".csv", ".tsv", ".json", ".jsonl")):
                continue
            headers, rows, _trunc = load_table(os.path.join(out_dir, f["name"]))
            if not headers:
                continue
            tbl = table_name_for(f["name"])
            cols = ", ".join('"%s" TEXT' % h.replace('"', '""') for h in headers)
            existing = conn.execute(
                "SELECT COUNT(*) FROM pragma_table_info(?)", (tbl,)).fetchone()[0]
            if existing == 0:
                conn.execute('CREATE TABLE "%s" (%s)' % (tbl, cols))
            elif existing != len(headers):
                tbl = tbl + "_2"
                conn.execute('CREATE TABLE IF NOT EXISTS "%s" (%s)' % (tbl, cols))
            ph = ",".join("?" * len(headers))
            conn.executemany(
                'INSERT INTO "%s" VALUES (%s)' % (tbl, ph),
                ((r + [""] * len(headers))[:len(headers)] for r in rows))
        conn.commit()
    finally:
        conn.close()
    return db_path


@app.post("/api/jobs/<job_id>/db")
def api_db_build(job_id):
    job = JOBS.get(job_id) or abort(404)
    if job["status"] != "done" and not job["files"]:
        abort(400, "Job has no output yet")
    db_path = build_job_db(job)
    conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    try:
        tables = []
        for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            cols = [{"name": c[1], "type": c[2] or "TEXT"}
                    for c in conn.execute('PRAGMA table_info("%s")' % name)]
            count = conn.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()[0]
            tables.append({"name": name, "rows": count, "columns": cols})
    finally:
        conn.close()
    return jsonify({"db": os.path.basename(db_path), "tables": tables})


@app.post("/api/jobs/<job_id>/db/query")
def api_db_query(job_id):
    job = JOBS.get(job_id) or abort(404)
    sql = (request.get_json(silent=True) or {}).get("sql", "").strip()
    if not sql:
        abort(400, "Empty query")
    db_path = build_job_db(job)
    conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    conn.execute("PRAGMA query_only = ON")
    try:
        cur = conn.execute(sql)
        headers = [d[0] for d in cur.description] if cur.description else []
        rows = [["" if v is None else str(v) for v in r] for r in cur.fetchmany(1000)]
        truncated = bool(cur.fetchone())
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
    return jsonify({"headers": headers, "rows": rows, "truncated": truncated})


@app.get("/api/jobs/<job_id>/text")
def api_text(job_id):
    full = job_file(job_id, request.args.get("file", ""))
    with open(full, encoding="utf-8", errors="replace") as fh:
        return jsonify({"text": fh.read(512 * 1024), "size": os.path.getsize(full)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
