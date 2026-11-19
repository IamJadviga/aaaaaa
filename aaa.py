import argparse
import json
import logging
import logging.handlers
import math
import os
import signal
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

APP_NAME = "convert-service"
LOG = logging.getLogger("convert")


def setup_logging(log_dir: str, max_bytes: int, backup_count: int) -> None:
    """Два потока журнала: файл с ротацией (том журналов) и stdout (журнал контейнера)."""
    os.makedirs(log_dir, exist_ok=True)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    for h in list(LOG.handlers):         
        LOG.removeHandler(h)
        h.close()

    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s",
                            datefmt="%Y-%m-%dT%H:%M:%S")
    fmt.converter = time.gmtime           

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=max_bytes,               
        backupCount=backup_count,        
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    LOG.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    LOG.addHandler(stream_handler)


def log_stress(lines: int) -> int:
    LOG.info("log_stress_begin lines=%d", lines)
    pad = "x" * 96
    for i in range(lines):
        LOG.info("stress_test seq=%d pad=%s", i, pad)
    LOG.info("log_stress_end lines=%d", lines)
    logging.shutdown()
    return 0

class StateStore:
    """Счётчик обработанных запросов в JSON-файле. Запись атомарная."""

    def __init__(self, path: str):
        self.path = path
        self.dir = os.path.dirname(path) or "."
        self._lock = threading.Lock()
        self._count = 0

    def load(self) -> int:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._count = int(data.get("request_count", 0))
            LOG.info("state_loaded path=%s request_count=%d", self.path, self._count)
        except FileNotFoundError:
            self._count = 0
            LOG.info("state_absent path=%s start_count=0", self.path)
        except (OSError, ValueError, TypeError) as exc:
            quarantine = f"{self.path}.corrupt.{int(time.time())}"
            try:
                os.replace(self.path, quarantine)
            except OSError:
                quarantine = "<не сохранён>"
            self._count = 0
            LOG.error("state_corrupt path=%s error=%s quarantine=%s start_count=0",
                      self.path, exc, quarantine)
        return self._count

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def increment(self) -> int:
        with self._lock:
            self._count += 1
            self._write_locked({"request_count": self._count})
            return self._count

    def flush(self) -> None:
        with self._lock:
            self._write_locked({"request_count": self._count})

    def _write_locked(self, data: dict) -> None:
        os.makedirs(self.dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())    
            os.replace(tmp, self.path)  
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        try:                              
            dfd = os.open(self.dir, os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass


class ConvertHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = APP_NAME
    sys_version = ""
    timeout = 15

    def do_GET(self):
        started = time.perf_counter()
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            status, body = 200, {"status": "ok", "version": self.server.app_version}
        elif path == "/stats":
            status, body = 200, {"request_count": self.server.store.count}
        elif path == "/convert":
            status, body = self._convert(parse_qs(parsed.query))
        else:
            status, body = 404, {"error": "Not found"}

        self._send(status, body)
        LOG.info('%s "%s" %d %.2fms', self.client_address[0], self.path,
                 status, (time.perf_counter() - started) * 1000)

    def _convert(self, params):
        if not params.get("value"):
            return 400, {"error": "Missing 'value' parameter"}
        try:
            value = float(params["value"][0])
        except (TypeError, ValueError):
            return 400, {"error": "Invalid value"}
        if not math.isfinite(value):
            return 400, {"error": "Value must be finite"}
        meters = value * 1000
        if not math.isfinite(meters):
            return 400, {"error": "Value out of range"}

        count = self.server.store.increment()
        return 200, {
            "kilometers": value,
            "meters": meters,
            "message": self.server.message,
            "version": self.server.app_version,
            "requests_handled": count,
        }

    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    def log_error(self, fmt, *args):
        LOG.warning("%s - %s", self.address_string(), fmt % args)


class ConvertServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, store, app_version, message):
        super().__init__(addr, ConvertHandler)
        self.store = store
        self.app_version = app_version
        self.message = message

    def handle_error(self, request, client_address):
        LOG.warning("connection_error client=%s", client_address[0])


_stop = False


def _request_stop(signum, frame):
    global _stop
    _stop = True       


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--log-stress", type=int, default=0, metavar="N",
                        help="служебный режим: записать N тестовых записей в журнал и выйти")
    args = parser.parse_args(argv)

    log_dir = os.environ.get("LOG_DIR", "/logs")
    data_dir = os.environ.get("DATA_DIR", "/data")
    max_bytes = int(os.environ.get("LOG_MAX_BYTES", "20000000"))
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", "2"))
    version = os.environ.get("APP_VERSION", "unknown")
    port = int(os.environ.get("PORT", "8004"))

    try:
        setup_logging(log_dir, max_bytes, backup_count)
    except OSError as exc:
        print(f"[fatal] каталог журналов недоступен {log_dir}: {exc}", file=sys.stderr)
        return 1

    LOG.info("start app=%s version=%s log_dir=%s max_bytes=%d backup_count=%d",
             APP_NAME, version, log_dir, max_bytes, backup_count)

    if args.log_stress > 0:
        return log_stress(args.log_stress)

    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError as exc:
        LOG.error("data_dir_unavailable path=%s error=%s", data_dir, exc)
        return 1

    store = StateStore(os.path.join(data_dir, "state.json"))
    store.load()

    server = ConvertServer(("0.0.0.0", port), store, version,
                           os.environ.get("MESSAGE", ""))
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    threading.Thread(target=server.serve_forever,
                     kwargs={"poll_interval": 0.2}, daemon=True).start()
    LOG.info("listening port=%d data_dir=%s request_count=%d", port, data_dir, store.count)

    while not _stop:
        time.sleep(0.2)

    LOG.info("shutdown_begin")
    server.shutdown()
    server.server_close()
    store.flush()
    LOG.info("shutdown_done request_count=%d", store.count)
    logging.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())