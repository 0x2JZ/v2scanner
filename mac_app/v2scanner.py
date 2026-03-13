"""
V2 Scanner — Portable macOS App
Tests V2Ray/Xray proxy configs and lists working ones.
"""

import os
import sys
import json
import subprocess
import tempfile
import time
import socket
import threading
import queue
import logging
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing, contextmanager

import requests

import config_parser as parser
import transport_builder

# ── Logging ───────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────
IS_WINDOWS = sys.platform == "win32"
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
DEFAULT_TEST_URLS = ["https://www.youtube.com/generate_204", "https://www.google.com/generate_204"]
DEFAULT_TIMEOUT = 10
DEFAULT_WORKERS = 6
UNSUPPORTED_PROTOCOLS = ["tuic://", "wireguard://"]


# ── Xray Path Resolution ─────────────────────────────
def get_xray_path() -> str:
    """Find xray binary: bundled (PyInstaller) → same dir → PATH."""
    # PyInstaller bundle
    if getattr(sys, "_MEIPASS", None):
        bundled = os.path.join(sys._MEIPASS, "xray.exe" if IS_WINDOWS else "xray")
        if os.path.isfile(bundled):
            return bundled

    # Same directory as script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local = os.path.join(script_dir, "xray.exe" if IS_WINDOWS else "xray")
    if os.path.isfile(local):
        return local

    # Fallback to PATH
    return "xray.exe" if IS_WINDOWS else "xray"


# ── Port Finder ──────────────────────────────────────
def find_free_port() -> int:
    for attempt in range(10):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("127.0.0.1", 0))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                port = s.getsockname()[1]
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as t:
                    t.settimeout(0.1)
                    try:
                        t.connect(("127.0.0.1", port))
                        continue
                    except (socket.error, socket.timeout):
                        return port
            except OSError:
                if attempt == 9:
                    raise
                time.sleep(0.1)
    raise RuntimeError("Could not find a free port")


# ── Process Manager ──────────────────────────────────
@contextmanager
def managed_process(command: List[str], config_file: str):
    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=SUBPROCESS_FLAGS,
        )
        yield process
    finally:
        if process:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
            except (ProcessLookupError, OSError):
                pass


# ── Config Tester ────────────────────────────────────
class XrayTester:
    def __init__(self, xray_path: str = None, timeout: int = DEFAULT_TIMEOUT,
                 test_urls: List[str] = None):
        self.xray_path = xray_path or get_xray_path()
        self.timeout = timeout
        self.test_urls = test_urls or DEFAULT_TEST_URLS
        self._verify_xray()

    @staticmethod
    def _wait_for_port(port: int, timeout: float = 5.0) -> bool:
        """Poll until a local port accepts connections, or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                    s.settimeout(0.1)
                    s.connect(("127.0.0.1", port))
                    return True
            except (socket.error, socket.timeout, OSError):
                time.sleep(0.05)
        return False

    def _verify_xray(self):
        try:
            result = subprocess.run(
                [self.xray_path, "version"],
                capture_output=True, timeout=5,
                creationflags=SUBPROCESS_FLAGS,
            )
            if result.returncode != 0:
                raise RuntimeError(f"xray verification failed: {result.stderr.decode()}")
        except FileNotFoundError:
            raise RuntimeError(
                f"xray not found at: {self.xray_path}\n\n"
                "Place xray.exe in the same folder as this app."
            )

    def is_supported(self, config_str: str) -> bool:
        lower = config_str.lower()
        return not any(lower.startswith(p) for p in UNSUPPORTED_PROTOCOLS)

    def parse_config(self, config_str: str) -> Optional[Dict]:
        try:
            lower = config_str.lower()
            if lower.startswith("vmess://"):
                data = parser.decode_vmess(config_str)
                if not data:
                    return None
                return {
                    "protocol": "vmess",
                    "settings": {"vnext": [{"address": data.get("add"),
                                            "port": int(data.get("port")),
                                            "users": [{"id": data.get("id"),
                                                        "alterId": int(data.get("aid", 0)),
                                                        "security": data.get("scy", "auto")}]}]},
                    "streamSettings": transport_builder.build_xray_settings(data),
                }
            elif lower.startswith("vless://"):
                data = parser.parse_vless(config_str)
                if not data:
                    return None
                return {
                    "protocol": "vless",
                    "settings": {"vnext": [{"address": data["address"],
                                            "port": data["port"],
                                            "users": [{"id": data["uuid"],
                                                        "encryption": "none",
                                                        "flow": data.get("flow", "")}]}]},
                    "streamSettings": transport_builder.build_xray_settings(data),
                }
            elif lower.startswith("trojan://"):
                data = parser.parse_trojan(config_str)
                if not data:
                    return None
                return {
                    "protocol": "trojan",
                    "settings": {"servers": [{"address": data["address"],
                                              "port": data["port"],
                                              "password": data["password"]}]},
                    "streamSettings": transport_builder.build_xray_settings(data),
                }
            elif lower.startswith("ss://"):
                data = parser.parse_shadowsocks(config_str)
                if not data:
                    return None
                return {
                    "protocol": "shadowsocks",
                    "settings": {"servers": [{"address": data["address"],
                                              "port": data["port"],
                                              "method": data["method"],
                                              "password": data["password"]}]},
                }
            return None
        except Exception:
            return None

    def test_config(self, config_str: str) -> Tuple[bool, Optional[int], str]:
        if not self.is_supported(config_str):
            return True, 0, config_str  # Skip unsupported, count as pass

        config_file = None
        try:
            outbound = self.parse_config(config_str)
            if not outbound:
                return False, None, config_str

            socks_port = find_free_port()

            xray_config = {
                "log": {"loglevel": "error"},
                "inbounds": [
                    {"port": socks_port, "protocol": "socks",
                     "settings": {"auth": "noauth", "udp": False}},
                ],
                "outbounds": [outbound],
            }

            fd, config_file = tempfile.mkstemp(suffix=".json", text=True, prefix="xray_")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(xray_config, f, indent=2)
            except Exception:
                os.close(fd)
                raise

            with managed_process(
                [self.xray_path, "run", "-c", config_file], config_file
            ) as process:
                # Poll for port readiness instead of sleeping 3s
                if not self._wait_for_port(socks_port, timeout=5.0):
                    return False, None, config_str
                if process.poll() is not None:
                    return False, None, config_str

                proxies = {
                    "http": f"socks5h://127.0.0.1:{socks_port}",
                    "https": f"socks5h://127.0.0.1:{socks_port}",
                }
                session = requests.Session()
                session.proxies.update(proxies)

                url = self.test_urls[0]
                start_time = time.time()
                try:
                    response = session.get(url, timeout=self.timeout)
                    delay = int((time.time() - start_time) * 1000)
                    if response.status_code in [200, 204]:
                        return True, delay, config_str
                except requests.exceptions.ProxyError:
                    return False, None, config_str
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                    pass
                except Exception:
                    pass

                return False, None, config_str

        except Exception:
            return False, None, config_str
        finally:
            if config_file and os.path.exists(config_file):
                try:
                    os.unlink(config_file)
                except Exception:
                    pass


# ── Shutdown Coordination ────────────────────────────
_shutdown_event = threading.Event()


def run_tests(configs: List[str], max_workers: int, xray_path: str,
              timeout: int, test_urls: List[str],
              progress_queue: queue.Queue) -> List[Tuple[str, int]]:
    """Run tests in background thread. Posts progress to queue."""
    _shutdown_event.clear()
    working = []
    tested = 0
    skipped = 0

    try:
        tester = XrayTester(xray_path=xray_path, timeout=timeout, test_urls=test_urls)
    except RuntimeError as e:
        progress_queue.put(("error", str(e)))
        return []

    total = len(configs)
    progress_queue.put(("started", total))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(tester.test_config, cfg): cfg for cfg in configs}

        for future in as_completed(futures):
            if _shutdown_event.is_set():
                for f in futures:
                    f.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                progress_queue.put(("stopped", None))
                return working

            tested += 1
            try:
                success, delay, config_str = future.result(timeout=tester.timeout + 10)
                if success:
                    if delay == 0:
                        skipped += 1
                    else:
                        working.append((config_str, delay))
                        progress_queue.put(("working", config_str, delay))
            except Exception:
                pass

            progress_queue.put(("progress", tested, total, len(working), skipped))

    progress_queue.put(("done", len(working), tested, skipped))
    return working


def stop_tests():
    _shutdown_event.set()


# ═══════════════════════════════════════════════════════
#  GUI — Dark-themed tkinter
# ═══════════════════════════════════════════════════════
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── Theme Colors ─────────────────────────────────────
C = {
    "bg_deep":      "#0c0c12",
    "bg_panel":     "#10101a",
    "bg_elevated":  "#1c1c2a",
    "bg_input":     "#14141f",
    "border":       "#2a2a3e",
    "border_focus": "#00b4ff",
    "accent":       "#00b4ff",
    "accent2":      "#a064ff",
    "success":      "#00ffaa",
    "danger":       "#ff3c5a",
    "warning":      "#ffc832",
    "text":         "#dce1f0",
    "text_sec":     "#828aa5",
    "text_muted":   "#464b5f",
}


class V2ScannerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("V2 Scanner")
        self.root.geometry("850x680")
        self.root.minsize(700, 550)
        self.root.configure(bg=C["bg_deep"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to set icon if available
        try:
            icon_path = os.path.join(
                getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
                "icon.ico",
            )
            if os.path.isfile(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self._setup_styles()
        self._build_ui()

        self.testing = False
        self.test_thread = None
        self.progress_queue = queue.Queue()
        self.working_configs = []

        self._poll_queue()

    # ── Styles ───────────────────────────────────────
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=C["bg_deep"], foreground=C["text"],
                        fieldbackground=C["bg_input"], bordercolor=C["border"],
                        troughcolor=C["bg_panel"], focuscolor=C["accent"])

        style.configure("TFrame", background=C["bg_deep"])
        style.configure("Panel.TFrame", background=C["bg_panel"])

        style.configure("TLabel", background=C["bg_deep"], foreground=C["text"],
                        font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"),
                        foreground="#f5f5ff")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9),
                        foreground=C["text_sec"])
        style.configure("Status.TLabel", font=("Segoe UI", 10),
                        foreground=C["text_sec"])
        style.configure("Success.TLabel", foreground=C["success"])

        style.configure("Accent.TButton", background=C["accent"],
                        foreground="#ffffff", font=("Segoe UI", 10, "bold"),
                        padding=(16, 8))
        style.map("Accent.TButton",
                  background=[("active", "#0090cc"), ("disabled", C["bg_elevated"])])

        style.configure("Danger.TButton", background=C["danger"],
                        foreground="#ffffff", font=("Segoe UI", 10, "bold"),
                        padding=(16, 8))
        style.map("Danger.TButton",
                  background=[("active", "#cc2040"), ("disabled", C["bg_elevated"])])

        style.configure("Secondary.TButton", background=C["bg_elevated"],
                        foreground=C["text"], font=("Segoe UI", 9),
                        padding=(12, 6))
        style.map("Secondary.TButton",
                  background=[("active", C["border"])])

        style.configure("TProgressbar", troughcolor=C["bg_panel"],
                        background=C["accent"], thickness=8)

        style.configure("TSpinbox", fieldbackground=C["bg_input"],
                        foreground=C["text"], arrowcolor=C["text_sec"])

    # ── UI Layout ────────────────────────────────────
    def _build_ui(self):
        # Main container with padding
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        # ─ Header
        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 16))

        ttk.Label(header, text="V2 SCANNER", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="  Proxy Config Tester",
                  style="Subtitle.TLabel").pack(side=tk.LEFT, padx=(4, 0), pady=(6, 0))

        # ─ Input section
        input_frame = ttk.Frame(main)
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        input_header = ttk.Frame(input_frame)
        input_header.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(input_header, text="CONFIGS",
                  font=("Segoe UI", 9, "bold"),
                  foreground=C["text_sec"]).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(input_header)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Load File", style="Secondary.TButton",
                   command=self._load_file).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Clear", style="Secondary.TButton",
                   command=self._clear_input).pack(side=tk.LEFT)

        # Text input
        text_frame = tk.Frame(input_frame, bg=C["border"], bd=0, highlightthickness=0)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.input_text = tk.Text(
            text_frame, wrap=tk.NONE, font=("Consolas", 9),
            bg=C["bg_input"], fg=C["text"], insertbackground=C["accent"],
            selectbackground=C["accent"], selectforeground="#fff",
            relief=tk.FLAT, padx=10, pady=8, height=8,
            borderwidth=0, highlightthickness=0,
        )
        input_scroll = tk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                     command=self.input_text.yview,
                                     bg=C["bg_panel"], troughcolor=C["bg_panel"],
                                     activebackground=C["accent"])
        self.input_text.configure(yscrollcommand=input_scroll.set)
        input_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=1, pady=1)
        self.input_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # ─ Controls row
        controls = ttk.Frame(main)
        controls.pack(fill=tk.X, pady=(0, 12))

        self.btn_start = ttk.Button(controls, text="START TEST",
                                     style="Accent.TButton", command=self._start)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_stop = ttk.Button(controls, text="STOP",
                                    style="Danger.TButton", command=self._stop,
                                    state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 16))

        # Workers spinner
        ttk.Label(controls, text="Workers:", foreground=C["text_sec"],
                  font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        self.workers_var = tk.StringVar(value="6")
        self.workers_spin = ttk.Spinbox(
            controls, from_=1, to=32, textvariable=self.workers_var,
            width=4, font=("Segoe UI", 9),
        )
        self.workers_spin.pack(side=tk.LEFT)

        # Config count label
        self.count_label = ttk.Label(controls, text="",
                                      style="Subtitle.TLabel")
        self.count_label.pack(side=tk.RIGHT)

        # ─ Progress
        progress_frame = ttk.Frame(main)
        progress_frame.pack(fill=tk.X, pady=(0, 12))

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate",
                                             style="TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))

        self.status_label = ttk.Label(progress_frame, text="Ready",
                                       style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        # ─ Results section
        results_header = ttk.Frame(main)
        results_header.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(results_header, text="WORKING CONFIGS",
                  font=("Segoe UI", 9, "bold"),
                  foreground=C["success"]).pack(side=tk.LEFT)

        self.results_count = ttk.Label(results_header, text="",
                                        style="Subtitle.TLabel")
        self.results_count.pack(side=tk.LEFT, padx=(8, 0))

        result_btns = ttk.Frame(results_header)
        result_btns.pack(side=tk.RIGHT)

        ttk.Button(result_btns, text="Copy All", style="Secondary.TButton",
                   command=self._copy_results).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(result_btns, text="Export", style="Secondary.TButton",
                   command=self._export_results).pack(side=tk.LEFT)

        # Results listbox
        result_frame = tk.Frame(main, bg=C["border"], bd=0, highlightthickness=0)
        result_frame.pack(fill=tk.BOTH, expand=True)

        self.results_list = tk.Text(
            result_frame, wrap=tk.NONE, font=("Consolas", 9),
            bg=C["bg_input"], fg=C["success"], insertbackground=C["accent"],
            relief=tk.FLAT, padx=10, pady=8, height=8,
            state=tk.DISABLED, borderwidth=0, highlightthickness=0,
        )
        result_scroll = tk.Scrollbar(result_frame, orient=tk.VERTICAL,
                                      command=self.results_list.yview,
                                      bg=C["bg_panel"], troughcolor=C["bg_panel"],
                                      activebackground=C["accent"])
        self.results_list.configure(yscrollcommand=result_scroll.set)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=1, pady=1)
        self.results_list.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Configure text tags for results
        self.results_list.tag_configure("config", foreground=C["text"])
        self.results_list.tag_configure("latency", foreground=C["success"])
        self.results_list.tag_configure("header", foreground=C["accent"],
                                         font=("Consolas", 9, "bold"))

    # ── Actions ──────────────────────────────────────
    def _load_file(self):
        path = filedialog.askopenfilename(
            title="Load Configs",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.input_text.delete("1.0", tk.END)
                self.input_text.insert("1.0", content)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file:\n{e}")

    def _clear_input(self):
        self.input_text.delete("1.0", tk.END)

    def _get_configs(self) -> List[str]:
        text = self.input_text.get("1.0", tk.END)
        configs = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("//") and "://" in line:
                configs.append(line)
        return configs

    def _start(self):
        configs = self._get_configs()
        if not configs:
            messagebox.showwarning("No Configs", "Paste or load some proxy configs first.")
            return

        self.testing = True
        self.working_configs = []
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.progress_bar["value"] = 0

        # Clear results
        self.results_list.configure(state=tk.NORMAL)
        self.results_list.delete("1.0", tk.END)
        self.results_list.configure(state=tk.DISABLED)
        self.results_count.configure(text="")

        workers = int(self.workers_var.get())
        self.count_label.configure(text=f"{len(configs)} configs")
        self.status_label.configure(text="Starting...")

        self.progress_queue = queue.Queue()
        self.test_thread = threading.Thread(
            target=run_tests,
            args=(configs, workers, get_xray_path(), DEFAULT_TIMEOUT,
                  DEFAULT_TEST_URLS, self.progress_queue),
            daemon=True,
        )
        self.test_thread.start()

    def _stop(self):
        stop_tests()
        self.btn_stop.configure(state=tk.DISABLED)
        self.status_label.configure(text="Stopping...")

    def _finish(self):
        self.testing = False
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)

    def _add_result(self, config_str: str, delay: int):
        self.working_configs.append((config_str, delay))
        self.results_list.configure(state=tk.NORMAL)

        # Protocol label
        proto = config_str.split("://")[0].upper() if "://" in config_str else "?"
        self.results_list.insert(tk.END, f"[{proto}] ", "header")
        self.results_list.insert(tk.END, f"{delay}ms ", "latency")
        self.results_list.insert(tk.END, f"  {config_str}\n", "config")

        self.results_list.configure(state=tk.DISABLED)
        self.results_list.see(tk.END)
        self.results_count.configure(text=f"({len(self.working_configs)} found)")

    def _copy_results(self):
        if not self.working_configs:
            return
        text = "\n".join(cfg for cfg, _ in self.working_configs)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text=f"Copied {len(self.working_configs)} configs to clipboard")

    def _export_results(self):
        if not self.working_configs:
            return
        path = filedialog.asksaveasfilename(
            title="Export Working Configs",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="working_configs.txt",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for cfg, delay in self.working_configs:
                        f.write(f"{cfg}\n")
                self.status_label.configure(text=f"Exported {len(self.working_configs)} configs to {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export:\n{e}")

    # ── Queue Polling ────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                msg = self.progress_queue.get_nowait()
                kind = msg[0]

                if kind == "started":
                    total = msg[1]
                    self.progress_bar["maximum"] = total
                    self.status_label.configure(text=f"Testing 0/{total}...")

                elif kind == "progress":
                    tested, total, working, skipped = msg[1], msg[2], msg[3], msg[4]
                    self.progress_bar["value"] = tested
                    pct = round(tested / max(1, total) * 100, 1)
                    self.status_label.configure(
                        text=f"Testing {tested}/{total} ({pct}%) — {working} working"
                    )

                elif kind == "working":
                    config_str, delay = msg[1], msg[2]
                    self._add_result(config_str, delay)

                elif kind == "done":
                    working, tested, skipped = msg[1], msg[2], msg[3]
                    self.progress_bar["value"] = self.progress_bar["maximum"]
                    self.status_label.configure(
                        text=f"Done: {working} working out of {tested} tested"
                    )
                    self._finish()

                elif kind == "stopped":
                    self.status_label.configure(
                        text=f"Stopped — {len(self.working_configs)} working found"
                    )
                    self._finish()

                elif kind == "error":
                    messagebox.showerror("Xray Error", msg[1])
                    self._finish()

        except queue.Empty:
            pass

        self.root.after(100, self._poll_queue)

    # ── Cleanup ──────────────────────────────────────
    def _on_close(self):
        if self.testing:
            stop_tests()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    app = V2ScannerApp()
    app.run()
