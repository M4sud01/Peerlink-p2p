# PeerLink - P2P Communication and File Sharing

## 1. Project Description
A lightweight peer-to-peer application in Python. Each running instance is one peer that is
both a **TCP server** (accepts connections) and a **TCP client** (connects to others).
Peers exchange text messages and files directly - there is **no central server**.

Features: peer startup (name + port), direct connection by IP:port, HELLO handshake,
connected-peer list, text messaging, binary file transfer (images, audio, video, PDF, ZIP...)
in 64 KB chunks, multiple simultaneous peers (one thread per connection), error handling.

## 2. Requirements
- Python 3.9+ (Windows / Linux / macOS)
- Standard library only (`socket`, `threading`, `json`, `struct`, `tkinter`). No `pip install` needed.
- On some Linux systems Tkinter needs: `sudo apt install python3-tk`

## 3. Project Structure
| File | Responsibility |
|---|---|
| `main.py` | Tkinter user interface |
| `p2p_node.py` | Server/client roles, connections, threads, text + file transfer |
| `protocol.py` | Message building, length-prefix framing, chunked file bytes |
| `downloads/` | Received files are saved here |

## 4. How to Run
```
python main.py
```
1. Enter a **Name** and a **Port** and press **Start Peer**.
2. Run `python main.py` again (another terminal or computer) with a different name and port.

## 5. How to Connect Two Peers
- Same computer: Bob enters IP `127.0.0.1`, Port `5000` (Alice's port) and presses **Connect**.
- Two computers (same Wi-Fi/LAN): find the other machine's IP (`ipconfig` / `ip a`), e.g. `192.168.1.10`,
  and connect to `192.168.1.10:5000`. Allow Python through the firewall if asked.
- Both peers will show each other in **Connected Peers**. For 3+ peers, connect each new peer to the others.

## 6. How to Send Text / Transfer Files
- **Text:** select a peer in the list, type in *Send Text*, press **Send** (or Enter).
- **File:** select a peer, press **Choose File & Send**, pick any file. The receiver saves it into `downloads/`
  (existing names are never overwritten; `photo_1.jpg` is used instead).

## 7. Protocol
Framing: `[4-byte big-endian length][JSON payload]`.
Messages: `hello`, `hello_ack`, `text`, `file`.
File transfer: a `file` JSON message (`filename`, `filesize`) followed by exactly `filesize` raw bytes.
The receiver reads exactly `filesize` bytes, so it knows when the file is complete.

## 8. Error Handling
Invalid IP/port, connection refused/timeout, peer disconnecting (also mid-transfer; partial file deleted),
missing file, invalid file size, empty/duplicate/self connections, and sending without selecting a peer
are all handled without crashing; messages appear in the event log, e.g. `[ERROR] Connection failed: ... Connection refused`.

## 9. Example Screenshots
Add your own screenshots here before submission (Peer 1, Peer 2, Peer 3 windows), e.g.
`![Peer 1](screenshots/peer1.png)`.
