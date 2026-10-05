"""p2p_node.py - A peer: TCP server (accepts) + TCP client (connects), one thread per connection."""
import os
import socket
import threading
import uuid

import protocol

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")


class PeerConnection:
    """One live connection to a remote peer."""
    def __init__(self, sock, addr, peer_id, name, listen_port):
        self.sock, self.addr = sock, addr
        self.peer_id, self.name, self.listen_port = peer_id, name, listen_port
        self.send_lock = threading.Lock()   # prevents text/file bytes interleaving


class P2PNode:
    def __init__(self, name, port, on_event=print, on_peers_changed=lambda: None,
                 on_message=None, on_file=None):
        self.name, self.port = name, port
        self.peer_id = uuid.uuid4().hex[:8]
        self.on_event = on_event
        self.on_peers_changed = on_peers_changed
        self.on_message = on_message or (lambda n, m: None)
        self.on_file = on_file or (lambda n, p: None)
        self.peers = {}                      # peer_id -> PeerConnection
        self.lock = threading.Lock()
        self.server_socket = None
        self.running = False

    # ---------- server role ----------
    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", self.port))
            s.listen()
        except OSError as e:
            s.close()
            raise OSError(f"Cannot listen on port {self.port}: {e}")
        self.server_socket, self.running = s, True
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.on_event(f"[SYSTEM] Peer started: {self.name} [{self.peer_id}] on port {self.port}")

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
            except OSError:
                break                          # server socket closed
            threading.Thread(target=self._handle_incoming, args=(conn, addr), daemon=True).start()

    def _handle_incoming(self, conn, addr):
        try:
            conn.settimeout(5)
            hello = protocol.recv_json(conn)
            if hello.get("type") != protocol.HELLO:
                raise ValueError("expected hello")
            protocol.send_json(conn, protocol.make_hello_ack(self.peer_id, self.name, self.port))
            conn.settimeout(None)
            if not self._register(conn, addr, hello):
                conn.close()                  # duplicate / self connection
        except Exception as e:
            self.on_event(f"[ERROR] Incoming connection from {addr[0]}:{addr[1]} failed: {e}")
            conn.close()

    # ---------- client role ----------
    def connect(self, ip, port):
        """Connect to another peer. Raises ValueError/OSError with a friendly message."""
        try:
            socket.inet_aton(ip)
        except OSError:
            raise ValueError(f"Invalid IP address: {ip}")
        if not (1 <= port <= 65535):
            raise ValueError(f"Invalid port: {port}")
        if port == self.port and ip in ("127.0.0.1", "localhost"):
            raise ValueError("Cannot connect to yourself")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((ip, port))
            protocol.send_json(sock, protocol.make_hello(self.peer_id, self.name, self.port))
            ack = protocol.recv_json(sock)
            if ack.get("type") != protocol.HELLO_ACK:
                raise ValueError("expected hello_ack")
            sock.settimeout(None)
        except Exception as e:
            sock.close()
            raise OSError(f"Connection failed: {e}")
        if not self._register(sock, (ip, port), ack):
            sock.close()
            raise ValueError("Already connected to this peer")
        return ack["peer_name"]

    # ---------- shared ----------
    def _register(self, sock, addr, info):
        pid = info["peer_id"]
        with self.lock:
            if pid == self.peer_id or pid in self.peers:
                return False
            pc = PeerConnection(sock, addr, pid, info["peer_name"], info.get("port"))
            self.peers[pid] = pc
        self.on_event(f"[SYSTEM] Connected to {pc.name} ({addr[0]}:{addr[1]})")
        self.on_peers_changed()
        threading.Thread(target=self._receive_loop, args=(pc,), daemon=True).start()
        return True

    def _receive_loop(self, pc):
        try:
            while self.running:
                msg = protocol.recv_json(pc.sock)
                t = msg.get("type")
                if t == protocol.TEXT:
                    self.on_message(pc.name, msg.get("message", ""))
                elif t == protocol.FILE:
                    self._receive_file(pc, msg)
        except Exception as e:
            if self.running:
                self.on_event(f"[SYSTEM] {pc.name} disconnected ({e})")
        finally:
            self._remove(pc)

    def _receive_file(self, pc, msg):
        filename = os.path.basename(str(msg.get("filename", ""))) or "received_file"
        size = msg.get("filesize")
        if not isinstance(size, int) or size < 0:
            raise ValueError("invalid file size in metadata")
        dest = self._unique_path(filename)
        self.on_event(f"[SYSTEM] Receiving {filename} ({size} bytes) from {pc.name}...")
        try:
            protocol.recv_file_bytes(pc.sock, dest, size)
        except Exception:
            if os.path.exists(dest):
                os.remove(dest)               # discard partial file
            raise
        self.on_file(pc.name, dest)

    @staticmethod
    def _unique_path(filename):
        path = os.path.join(DOWNLOAD_DIR, filename)
        base, ext = os.path.splitext(filename)
        i = 1
        while os.path.exists(path):
            path = os.path.join(DOWNLOAD_DIR, f"{base}_{i}{ext}")
            i += 1
        return path

    def _remove(self, pc):
        with self.lock:
            removed = self.peers.pop(pc.peer_id, None)
        try:
            pc.sock.shutdown(socket.SHUT_RDWR)   # wakes blocked recv() and notifies remote peer
        except OSError:
            pass
        try:
            pc.sock.close()
        except OSError:
            pass
        if removed:
            self.on_peers_changed()

    def get_peers(self):
        with self.lock:
            return list(self.peers.values())

    # ---------- sending ----------
    def _get(self, peer_id):
        with self.lock:
            pc = self.peers.get(peer_id)
        if not pc:
            raise ConnectionError("Peer is not connected")
        return pc

    def send_text(self, peer_id, text):
        pc = self._get(peer_id)
        try:
            with pc.send_lock:
                protocol.send_json(pc.sock, protocol.make_text(self.peer_id, self.name, text))
        except OSError as e:
            self._remove(pc)
            raise ConnectionError(f"Send failed: {e}")
        return pc.name

    def send_file(self, peer_id, path, progress=None):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File does not exist: {path}")
        size = os.path.getsize(path)
        pc = self._get(peer_id)
        try:
            with pc.send_lock:                # metadata + raw bytes must stay together
                protocol.send_json(pc.sock, protocol.make_file(
                    self.peer_id, self.name, os.path.basename(path), size))
                protocol.send_file_bytes(pc.sock, path, progress)
        except OSError as e:
            self._remove(pc)
            raise ConnectionError(f"Send failed: {e}")
        return pc.name

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        for pc in self.get_peers():
            self._remove(pc)
        self.on_event("[SYSTEM] Peer stopped")
