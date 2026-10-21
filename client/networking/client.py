"""Client side of the wire protocol: a socket with a background reader thread.
request() is a blocking call matched to its reply by id (LAN latency is tiny);
unsolicited server pushes (queue updates, match snapshots) are collected by poll()."""
import itertools
import queue
import socket
import threading
import time

from shared.protocol import MAX_SERVER_MSG, PROTOCOL_VERSION, ProtocolError, decode, encode


class NetError(Exception):
    pass


class NetClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.close_reason = ""
        self.pushes = queue.Queue()
        self._ids = itertools.count(1)
        self._waiters = {}
        self._wlock = threading.Lock()
        self._slock = threading.Lock()
        self._last_sent = time.monotonic()
        self.address = ("", 0)

    def connect(self, host: str, port: int, timeout: float = 3.0):
        self.close()
        try:
            sock = socket.create_connection((host, port), timeout)
        except OSError as e:
            raise NetError(f"Could not connect to {host}:{port} ({e.strerror or e})") from e
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock, self.connected, self.close_reason = sock, True, ""
        self.address = (host, port)
        self.pushes = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        r = self.request("hello", v=PROTOCOL_VERSION)
        if not r.get("ok"):
            self.close()
            raise NetError(r.get("error", "Server refused the connection."))
        return r

    # ----- sending -----
    def _send(self, msg):
        if not self.connected:
            raise NetError("Not connected to the server.")
        try:
            with self._slock:
                self.sock.sendall(encode(msg))
            self._last_sent = time.monotonic()
        except OSError as e:
            self._drop(f"connection lost ({e})")
            raise NetError("Connection to the server was lost.") from e

    def send(self, t: str, **fields):
        """Fire-and-forget (used for real-time input)."""
        self._send(dict(fields, t=t))

    def request(self, t: str, timeout: float = 5.0, **fields) -> dict:
        rid = next(self._ids)
        ev, box = threading.Event(), []
        with self._wlock:
            self._waiters[rid] = (ev, box)
        try:
            self._send(dict(fields, t=t, id=rid))
            if not ev.wait(timeout):
                raise NetError("The server didn't answer in time.")
        finally:
            with self._wlock:
                self._waiters.pop(rid, None)
        if not box:
            raise NetError(self.close_reason or "Connection to the server was lost.")
        return box[0]

    def poll(self) -> list:
        out = []
        while True:
            try:
                out.append(self.pushes.get_nowait())
            except queue.Empty:
                return out

    def keepalive(self):
        if self.connected and time.monotonic() - self._last_sent > 20:
            try:
                self.send("ping")
            except NetError:
                pass

    # ----- receiving -----
    def _reader(self):
        buf = b""
        sock = self.sock
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    self._drop("The server closed the connection.")
                    return
                buf += chunk
                if len(buf) > MAX_SERVER_MSG * 2:
                    self._drop("Server sent too much data.")
                    return
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = decode(line)
                    except ProtocolError:
                        continue
                    if msg["t"] == "reply":
                        with self._wlock:
                            waiter = self._waiters.get(msg.get("re"))
                        if waiter:
                            waiter[1].append(msg)
                            waiter[0].set()
                    else:
                        self.pushes.put(msg)
        except OSError as e:
            self._drop(f"connection lost ({e})")

    def _drop(self, reason):
        if not self.connected:
            return
        self.connected = False
        self.close_reason = reason
        self.pushes.put({"t": "_disconnected", "reason": reason})
        with self._wlock:
            for ev, _ in self._waiters.values():
                ev.set()

    def close(self):
        was = self.connected
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        if was:
            self.close_reason = "closed"
