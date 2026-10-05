"""main.py - Tkinter user interface for PeerLink (P2P messaging and file sharing). Run: python main.py"""
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from p2p_node import P2PNode


class App:
    def __init__(self, root):
        self.root, self.node = root, None
        self.ui_queue = queue.Queue()          # worker threads -> UI thread
        self.peer_ids = []
        root.title("PeerLink - P2P File Sharing")
        root.geometry("900x600")
        self._build()
        self._set_running(False)
        self._poll()
        root.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- layout ----------
    def _build(self):
        r = self.root
        f = ttk.LabelFrame(r, text="My Peer"); f.pack(fill="x", padx=8, pady=4)
        self.name_var, self.port_var = tk.StringVar(value="Alice"), tk.StringVar(value="5000")
        ttk.Label(f, text="Name:").grid(row=0, column=0, padx=4, pady=4)
        self.name_e = ttk.Entry(f, textvariable=self.name_var, width=16); self.name_e.grid(row=0, column=1)
        ttk.Label(f, text="Port:").grid(row=0, column=2, padx=4)
        self.port_e = ttk.Entry(f, textvariable=self.port_var, width=8); self.port_e.grid(row=0, column=3)
        self.start_b = ttk.Button(f, text="Start Peer", command=self.start_peer); self.start_b.grid(row=0, column=4, padx=6)
        self.stop_b = ttk.Button(f, text="Stop", command=self.stop_peer); self.stop_b.grid(row=0, column=5)
        self.info_var = tk.StringVar(value="Not running")
        ttk.Label(f, textvariable=self.info_var).grid(row=1, column=0, columnspan=6, sticky="w", padx=4)

        c = ttk.LabelFrame(r, text="Connect to Another Peer"); c.pack(fill="x", padx=8, pady=4)
        self.ip_var, self.rport_var = tk.StringVar(value="127.0.0.1"), tk.StringVar(value="5001")
        ttk.Label(c, text="IP:").grid(row=0, column=0, padx=4, pady=4)
        self.ip_e = ttk.Entry(c, textvariable=self.ip_var, width=18); self.ip_e.grid(row=0, column=1)
        ttk.Label(c, text="Port:").grid(row=0, column=2, padx=4)
        self.rport_e = ttk.Entry(c, textvariable=self.rport_var, width=8); self.rport_e.grid(row=0, column=3)
        self.conn_b = ttk.Button(c, text="Connect", command=self.connect_peer); self.conn_b.grid(row=0, column=4, padx=6)

        mid = ttk.Frame(r); mid.pack(fill="both", expand=True, padx=8, pady=4)
        pf = ttk.LabelFrame(mid, text="Connected Peers"); pf.pack(side="left", fill="y")
        self.peer_list = tk.Listbox(pf, width=32, exportselection=False); self.peer_list.pack(fill="both", expand=True, padx=4, pady=4)
        lf = ttk.LabelFrame(mid, text="Messages / Events"); lf.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.log = tk.Text(lf, state="disabled", wrap="word", font=("Courier", 10)); self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lf, command=self.log.yview); sb.pack(side="right", fill="y"); self.log["yscrollcommand"] = sb.set

        t = ttk.LabelFrame(r, text="Send Text"); t.pack(fill="x", padx=8, pady=4)
        self.text_var = tk.StringVar()
        self.text_e = ttk.Entry(t, textvariable=self.text_var); self.text_e.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        self.text_e.bind("<Return>", lambda e: self.send_text())
        self.send_b = ttk.Button(t, text="Send", command=self.send_text); self.send_b.pack(side="right", padx=4)

        fl = ttk.LabelFrame(r, text="Send File"); fl.pack(fill="x", padx=8, pady=4)
        ttk.Label(fl, text="Text, image, audio, video, PDF, ZIP, etc.").pack(side="left", padx=4, pady=4)
        self.file_b = ttk.Button(fl, text="Choose File & Send", command=self.send_file); self.file_b.pack(side="right", padx=4)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(r, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def _set_running(self, running):
        for w in (self.name_e, self.port_e, self.start_b):
            w.config(state="disabled" if running else "normal")
        for w in (self.stop_b, self.ip_e, self.rport_e, self.conn_b, self.text_e, self.send_b, self.file_b):
            w.config(state="normal" if running else "disabled")

    # ---------- thread-safe UI updates ----------
    def _ui(self, fn, *a):
        self.ui_queue.put((fn, a))

    def _poll(self):
        while not self.ui_queue.empty():
            fn, a = self.ui_queue.get()
            fn(*a)
        self.root.after(100, self._poll)

    def _log(self, line):
        self.log.config(state="normal"); self.log.insert("end", line + "\n")
        self.log.see("end"); self.log.config(state="disabled")

    def _set_status(self, s):
        self.status.set(s)

    def _refresh_peers(self):
        peers = self.node.get_peers() if self.node else []
        self.peer_ids = [p.peer_id for p in peers]
        self.peer_list.delete(0, "end")
        for p in peers:
            self.peer_list.insert("end", f"{p.name} [{p.peer_id}] {p.addr[0]}:{p.listen_port or p.addr[1]}")

    # ---------- node callbacks (called from worker threads) ----------
    def _on_event(self, line): self._ui(self._log, line)
    def _on_peers(self): self._ui(self._refresh_peers)
    def _on_message(self, name, msg): self._ui(self._log, f"{name} -> You: {msg}")

    def _on_file(self, name, path):
        self._ui(self._log, f"{name} -> You: File received: {os.path.basename(path)}")
        self._ui(self._set_status, f"Received: {os.path.relpath(path)}")

    # ---------- actions ----------
    def start_peer(self):
        name = self.name_var.get().strip()
        if not name:
            return messagebox.showerror("Error", "Peer name cannot be empty")
        try:
            port = int(self.port_var.get())
            if not 1 <= port <= 65535: raise ValueError
        except ValueError:
            return messagebox.showerror("Error", "Port must be an integer between 1 and 65535")
        node = P2PNode(name, port, self._on_event, self._on_peers, self._on_message, self._on_file)
        try:
            node.start()
        except OSError as e:
            return messagebox.showerror("Error", str(e))
        self.node = node
        self.info_var.set(f"{name} | ID: {node.peer_id} | Port: {port}")
        self._set_status(f"Peer started: {name} [{node.peer_id}] on port {port}")
        self._set_running(True)

    def stop_peer(self):
        if self.node:
            self.node.stop(); self.node = None
        self._refresh_peers(); self.info_var.set("Not running")
        self._set_status("Peer stopped"); self._set_running(False)

    def connect_peer(self):
        ip = self.ip_var.get().strip()
        try:
            port = int(self.rport_var.get())
        except ValueError:
            return messagebox.showerror("Error", "Invalid port")
        def work():
            try:
                name = self.node.connect(ip, port)
                self._ui(self._set_status, f"Connected to {name} ({ip}:{port})")
            except Exception as e:
                self._ui(self._log, f"[ERROR] {e}")
                self._ui(self._set_status, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _selected(self):
        sel = self.peer_list.curselection()
        if not sel or sel[0] >= len(self.peer_ids):
            messagebox.showwarning("No peer selected", "Please select a connected peer first.")
            return None
        return self.peer_ids[sel[0]]

    def send_text(self):
        text = self.text_var.get().strip()
        if not text: return
        pid = self._selected()
        if not pid: return
        self.text_var.set("")
        def work():                           # off the UI thread: a running file upload holds the send lock
            try:
                name = self.node.send_text(pid, text)
                self._ui(self._log, f"You -> {name}: {text}")
            except Exception as e:
                self._ui(self._log, f"[ERROR] {e}")
        threading.Thread(target=work, daemon=True).start()

    def send_file(self):
        pid = self._selected()
        if not pid: return
        path = filedialog.askopenfilename(title="Choose a file to send")
        if not path: return
        def work():
            try:
                self._ui(self._set_status, f"Sending {os.path.basename(path)}...")
                name = self.node.send_file(pid, path)
                self._ui(self._log, f"You -> {name}: File sent: {os.path.basename(path)}")
                self._ui(self._set_status, f"Sent {os.path.basename(path)} to {name}")
            except Exception as e:
                self._ui(self._log, f"[ERROR] {e}")
                self._ui(self._set_status, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _close(self):
        if self.node: self.node.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
