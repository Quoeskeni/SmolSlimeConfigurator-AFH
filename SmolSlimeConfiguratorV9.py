# Import all needed stuff
import customtkinter as ctk
import serial
import serial.tools.list_ports
import threading
import time
import sys
import os
import argparse
import shutil
import requests
import subprocess
import platform
import tempfile
import json
import webbrowser
import re
from tkinter import filedialog
import tkinter as tk
import queue
import zipfile
from tkinter import messagebox
# For safety...
ui_queue = queue.Queue()
serial_queue = queue.Queue()
ser_lock = threading.Lock()
main_thread = threading.current_thread()

AFH_DEBUG_FIELDS = [
    "Tracker ID",
    "Receiver address",
    "Device address",
    "AFH channel",
    "AFH epoch",
    "AFH consecutive TX errors",
    "pairing state",
]
afh_debug_state = {field: "Unknown" for field in AFH_DEBUG_FIELDS}
pairing_request_spam_count = 0
pairing_hint_shown = False
raw_console_enabled = False
receiver_pairing_request_seen = False
last_device_type = "unknown"
last_mode_summary = "Waiting for device"
last_human_lines = []

DEVICE_STATE_FIELDS = [
    "Device type",
    "Mode",
    "Pairing",
    "Paired with",
    "Battery",
    "AFH channel",
    "AFH errors",
    "Address",
]
device_state = {
    "Device type": "Unknown",
    "Mode": "Disconnected",
    "Pairing": "Unknown",
    "Paired with": "Unknown",
    "Battery": "Unknown",
    "AFH channel": "Unknown",
    "AFH errors": "Unknown",
    "Address": "Unknown",
}

# Set theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Set variables and start serial
ser = None
connected = False
read_thread = None
stop_read = threading.Event()
custom_fw_path = None

# OS temp dir
def get_settings_path():
    if sys.platform.startswith("linux"):
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        path = os.path.join(base, "smolslime")
    elif sys.platform.startswith("win"):
        path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SmolSlime")
    else:
        path = os.path.expanduser("~/Library/Application Support/SmolSlime")

    os.makedirs(path, exist_ok=True)
    return os.path.join(path, "config.json")

SETTINGS_PATH = get_settings_path()


default_settings = {
    "theme": "dark",
    "accent": "dark-blue",
    "tooltips": True,
    "favorites": ["Custom (User provided .uf2 / .hex)"],
    "seen_favorite_hint": False,
    "firmware_source": "main",
    "custom_firmware_repo": "",
    "raw_console_enabled": False,
    "auto_select_device_tab": True
}

settings = default_settings.copy()

# Scaling for linux based on DPI
def set_linux_scaling():
    try:
        import subprocess
        dpi = subprocess.check_output(
            ["xrdb", "-query"], stderr=subprocess.DEVNULL
        ).decode()
        for line in dpi.splitlines():
            if "Xft.dpi" in line:
                dpi_value = float(line.split()[-1])
                scale = dpi_value / 96
                ctk.set_widget_scaling(scale)
                ctk.set_window_scaling(scale)
                return
    except Exception:
        pass

    ctk.set_widget_scaling(1.25)
    ctk.set_window_scaling(1.25)

if sys.platform.startswith("linux"):
    set_linux_scaling()


def load_settings():
    global settings
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                settings.update(json.load(f))
        except Exception:
            pass

def save_settings():
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)

load_settings()
ctk.set_appearance_mode(settings["theme"])
ctk.set_default_color_theme(settings["accent"])

if sys.platform.startswith("linux"):
    set_linux_scaling()

FIRMWARE_REPOS = {
    "main": "https://api.github.com/repos/Quoeskeni/SlimeNRF-Firmware-CI/releases/latest",
    "kounocom": "https://api.github.com/repos/kounocom/SlimeNRF-Firmware-CI/releases/latest"
}

ARTIFACT_NAME_RE = re.compile(r"(stackedsmol|stacked[-_ ]?smol|receiver|dongle)", re.IGNORECASE)

def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def repo_api_root(api_url):
    match = re.search(r"https://api\.github\.com/repos/([^/]+/[^/]+)", api_url)
    if not match:
        return None
    return f"https://api.github.com/repos/{match.group(1)}"

def fetch_artifact_firmware_assets(api_url):
    api_root = repo_api_root(api_url)
    if not api_root:
        return {}

    artifacts_url = f"{api_root}/actions/artifacts?per_page=100"
    append_text("No GitHub release assets found; checking workflow artifacts...\n")
    response = requests.get(artifacts_url, headers=github_headers(), timeout=10)
    response.raise_for_status()
    artifacts = response.json().get("artifacts", [])
    fw_dict = {}

    for artifact in artifacts:
        name = artifact.get("name", "")
        if artifact.get("expired") or not ARTIFACT_NAME_RE.search(name):
            continue
        archive_url = artifact.get("archive_download_url")
        if archive_url:
            fw_dict[f"{name} (artifact zip)"] = f"artifact::{archive_url}"

    if fw_dict:
        append_text(f"Found {len(fw_dict)} matching firmware artifact(s).\n", "success")
    return fw_dict

# Pull data from latest releases + file browser
def fetch_latest_firmware_assets():
    source = settings.get("firmware_source", "main")

    if source == "custom":
        api_url = settings.get("custom_firmware_repo", "").strip()
        if not api_url:
            append_text("Custom firmware repo is empty.\n", "error")
            return {}
    else:
        api_url = FIRMWARE_REPOS.get(source, FIRMWARE_REPOS["main"])

    try:
        response = requests.get(api_url, headers=github_headers(), timeout=10)
        if response.status_code == 404:
            return fetch_artifact_firmware_assets(api_url)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            if len(data) > 0:
                data = data[0]
            else:
                return fetch_artifact_firmware_assets(api_url)

        assets = data.get("assets", [])
        fw_dict = {}

        for asset in assets:
            name = asset.get("name", "")
            url = asset.get("browser_download_url", "")
            if name.endswith((".uf2", ".hex")):
                fw_dict[name] = url

        if not fw_dict:
            fw_dict = fetch_artifact_firmware_assets(api_url)

        if not fw_dict:
            append_text("No UF2/HEX release assets or matching firmware artifacts found.\n", "error")

        return fw_dict

    except Exception as e:
        append_text(f"[Error fetching firmware list] {e}\n", "error")
        return {}



def early_strip_log_prefix(line):
    line = re.sub(r"\x1b\[[0-9;]*m", "", str(line))
    line = re.sub(r"^\[[^\]]+\]\s*<[^>]+>\s*[^:]+:\s*", "", line)
    return line.strip()




def early_parse_battery_line(line):
    lower = line.lower()
    ignored_contexts = (
        "calibration",
        "cycle",
        "runtime",
        "coverage",
        "updated",
        "waiting",
        "not available",
        "none",
    )
    if any(context in lower for context in ignored_contexts):
        return None

    soc = re.search(r"(?:battery\s+soc|state\s+of\s+charge|soc)[:=]?\s*(?:\d+(?:\.\d+)?\s*%\s*->\s*)?(\d+(?:\.\d+)?\s*%)", line, re.IGNORECASE)
    if soc:
        return normalize_value(soc.group(1))

    battery = re.search(r"^\s*bat(?:tery)?(?:\s+percent|\s+level)?[:=]\s*(\d+(?:\.\d+)?\s*%)", line, re.IGNORECASE)
    if battery:
        return normalize_value(battery.group(1))

    voltage = re.search(r"^\s*(?:battery\s+voltage|bat|adc|vbat|voltage)[:=]\s*(\d+(?:\.\d+)?\s*(?:v|mv))", line, re.IGNORECASE)
    if voltage:
        return normalize_value(voltage.group(1))

    return None

def early_list_serial_ports():
    ports = serial.tools.list_ports.comports()
    if sys.platform.startswith("linux"):
        return [p.device for p in ports if "ttyACM" in p.device or "ttyUSB" in p.device]
    return [p.device for p in ports]


def early_detect_state(line, state):
    cleaned = early_strip_log_prefix(line)
    lower = cleaned.lower()

    def labeled(label):
        match = re.search(rf"{label}\s*[:=]\s*([^\r\n,;]+)", cleaned, re.IGNORECASE)
        return match.group(1).strip().strip("[]") if match else None

    if labeled(r"tracker\s*id"):
        state["Device type"] = "Tracker"
        state["Address"] = labeled(r"tracker\s*id")
    if labeled(r"receiver\s*address"):
        state["Device type"] = "Tracker"
        state["Paired with"] = labeled(r"receiver\s*address")
        state["Pairing"] = "Paired"
        state["Mode"] = "Paired"
    if labeled(r"device\s*address"):
        state["Device type"] = "Receiver"
        if state.get("Mode") == "Pairing":
            state["Paired with"] = labeled(r"device\s*address")
            state["Pairing"] = "Paired"
            state["Mode"] = "Paired"
        else:
            state["Address"] = labeled(r"device\s*address")
    if "rx pairing request" in lower or "pairing request received" in lower or "pairing mode" in lower:
        state["Device type"] = "Receiver"
        state["Mode"] = "Pairing"
        state["Pairing"] = "Tracker request received"
    battery = early_parse_battery_line(cleaned)
    if battery:
        state["Device type"] = "Tracker"
        state["Battery"] = battery
    pairing = labeled(r"pairing\s*state")
    if pairing:
        state["Pairing"] = pairing
        low = pairing.lower()
        state["Mode"] = "Pairing" if "start" in low else "Normal" if "stop" in low or "idle" in low else "Paired" if "paired" in low else state.get("Mode", "Unknown")
    channel = re.search(r"afh(?: default)? channel[:=]\s*(-?\d+)", cleaned, re.IGNORECASE)
    if channel:
        state["AFH channel"] = channel.group(1)
    errors = re.search(r"(?:afh )?consecutive tx errors[:=]\s*(\d+)", cleaned, re.IGNORECASE)
    if errors:
        state["AFH errors"] = errors.group(1)


def early_format_state(state):
    return "\n".join(["Smart SmolSlime status", "======================="] + [f"{field}: {state.get(field, 'Unknown')}" for field in DEVICE_STATE_FIELDS])


def early_run_console_mode(port=None, baudrate=115200, raw=False, commands=None):
    ports = early_list_serial_ports()
    if not port:
        if not ports:
            print("No serial ports found. Connect receiver/tracker and retry.", file=sys.stderr)
            return 2
        port = ports[0]
    state = device_state.copy()
    previous = None
    command_list = commands or ["info", "afh_info", "list", "battery"]
    print(f"Opening {port} at {baudrate} baud. Press Ctrl+C to stop.")
    try:
        with serial.Serial(port, baudrate, timeout=0.25) as serial_port:
            time.sleep(0.4)
            for command in command_list:
                serial_port.write((command + "\n").encode())
                print(f"> {command}")
                time.sleep(0.08)
            while True:
                raw_line = serial_port.readline()
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                early_detect_state(line, state)
                current = tuple(state.get(field, "Unknown") for field in DEVICE_STATE_FIELDS)
                if raw:
                    print(line)
                if current != previous:
                    print("\n" + early_format_state(state) + "\n", flush=True)
                    previous = current
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 0
    except (OSError, serial.SerialException) as exc:
        print(f"Device disconnected or serial error: {exc}", file=sys.stderr)
        return 1


def early_parse_cli_args():
    parser = argparse.ArgumentParser(description="SmolSlime AFH configurator")
    parser.add_argument("--console", action="store_true", help="Run smart terminal console instead of GUI")
    parser.add_argument("--port", help="Serial port for --console mode")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate for --console mode")
    parser.add_argument("--raw", action="store_true", help="Show raw firmware log lines in --console mode")
    parser.add_argument("--cmd", action="append", dest="commands", help="Command to send on connect; can be used multiple times")
    return parser.parse_args()


EARLY_CLI_ARGS = early_parse_cli_args()
if EARLY_CLI_ARGS.console:
    raise SystemExit(early_run_console_mode(EARLY_CLI_ARGS.port, EARLY_CLI_ARGS.baudrate, EARLY_CLI_ARGS.raw, EARLY_CLI_ARGS.commands))

# Start base window, size & name
app = ctk.CTk()
app.title("SmolSlime Configurator")
app.geometry("1080x560")
app.minsize(1010, 520)

# Overdone tooltip overlay
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)
        global TOOLTIPS_ENABLED
        TOOLTIPS_ENABLED = settings.get("tooltips", True)

    def show_tip(self, event=None):
        if not TOOLTIPS_ENABLED or self.tipwindow or not self.text:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        bg_color = "#333333" if settings["theme"] == "dark" else "#FFFFFF"
        fg_color = "#FFFFFF" if settings["theme"] == "dark" else "#000000"

        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.configure(bg=bg_color)

        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background=bg_color,
            foreground=fg_color,
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=5, ipady=2)

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


# Sniff them sweet sweet Smol Slimes (Looks for the COM port)
def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    filtered = []
# Filter out all ports except USB
    for port in ports:
        if sys.platform.startswith("linux"):
            if "ttyACM" in port.device or "ttyUSB" in port.device:
                filtered.append(port.device)
        else:
            filtered.append(port.device)

    return filtered

# Refresh the dropdown menu 
def refresh_ports():
    ports = list_serial_ports()
    if ports:
        port_option.configure(values=ports)
        port_option.set(ports[0])
    else:
        port_option.configure(values=["No ports found"])
        port_option.set("No ports found")

def run_on_ui_thread(func, *args, **kwargs):
    if threading.current_thread() is main_thread:
        func(*args, **kwargs)
    else:
        ui_queue.put((func, args, kwargs))

def call_on_ui_thread_sync(func, *args, **kwargs):
    if threading.current_thread() is main_thread:
        return func(*args, **kwargs)

    result_queue = queue.Queue(maxsize=1)

    def wrapper():
        try:
            result_queue.put((True, func(*args, **kwargs)))
        except Exception as exc:
            result_queue.put((False, exc))

    ui_queue.put((wrapper, (), {}))
    ok, result = result_queue.get()
    if ok:
        return result
    raise result

def set_status(text, color):
    run_on_ui_thread(status_label.configure, text=text, text_color=color)

def show_progress():
    run_on_ui_thread(progress_bar.pack, pady=(5, 5))

def hide_progress():
    run_on_ui_thread(progress_bar.pack_forget)

def set_progress(value):
    run_on_ui_thread(progress_bar.set, value)

def schedule_after(delay_ms, func, *args):
    run_on_ui_thread(app.after, delay_ms, lambda: func(*args))


def set_raw_console_enabled(value):
    global raw_console_enabled
    raw_console_enabled = bool(value)
    settings["raw_console_enabled"] = raw_console_enabled
    save_settings()
    if raw_console_enabled:
        append_text("Raw console enabled: firmware logs will be shown verbatim.\n", "success")
    else:
        append_text("Smart view enabled: noisy firmware logs are summarized above.\n", "success")


def strip_log_prefix(line):
    line = re.sub(r"\x1b\[[0-9;]*m", "", str(line))
    line = re.sub(r"^\[[^\]]+\]\s*<[^>]+>\s*[^:]+:\s*", "", line)
    return line.strip()


def normalize_value(value):
    value = strip_log_prefix(value).strip().strip("[]")
    return value.strip()


def extract_labeled_value(line, label):
    cleaned = strip_log_prefix(line)
    match = re.search(rf"{label}\s*[:=]\s*([^\r\n,;]+)", cleaned, re.IGNORECASE)
    return normalize_value(match.group(1)) if match else None


def set_device_field(field, value):
    value = normalize_value(str(value))
    if value:
        device_state[field] = value


def set_device_type(device_type):
    global last_device_type
    if device_type not in ("tracker", "receiver"):
        return
    last_device_type = device_type
    set_device_field("Device type", "Tracker" if device_type == "tracker" else "Receiver")
    if settings.get("auto_select_device_tab", True):
        tab_name = "Tracker" if device_type == "tracker" else "Receiver"
        schedule_after(0, tab_view.set, tab_name)


def add_human_line(text):
    global last_human_lines
    text = text.strip()
    if not text:
        return
    if text in last_human_lines[-4:]:
        return
    last_human_lines.append(text)
    last_human_lines = last_human_lines[-6:]
    append_text(f"• {text}\n", "success")


def format_device_summary():
    lines = [
        "Smart SmolSlime status",
        "=======================",
    ]
    for field in DEVICE_STATE_FIELDS:
        lines.append(f"{field}: {device_state.get(field, 'Unknown')}")
    if last_human_lines:
        lines.append("")
        lines.append("Important events:")
        lines.extend(f"- {line}" for line in last_human_lines[-6:])
    return "\n".join(lines)


def refresh_device_summary():
    if "device_cards" not in globals():
        return
    for field, label in device_cards.items():
        label.configure(text=device_state.get(field, "Unknown"))
    if "human_summary_label" in globals():
        human_summary_label.configure(text="\n".join(last_human_lines[-4:]) or "No important events yet.")


def parse_battery_line(line):
    lower = line.lower()
    ignored_contexts = (
        "calibration",
        "cycle",
        "runtime",
        "coverage",
        "updated",
        "waiting",
        "not available",
        "none",
    )
    if any(context in lower for context in ignored_contexts):
        return None

    soc = re.search(r"(?:battery\s+soc|state\s+of\s+charge|soc)[:=]?\s*(?:\d+(?:\.\d+)?\s*%\s*->\s*)?(\d+(?:\.\d+)?\s*%)", line, re.IGNORECASE)
    if soc:
        return normalize_value(soc.group(1))

    battery = re.search(r"^\s*bat(?:tery)?(?:\s+percent|\s+level)?[:=]\s*(\d+(?:\.\d+)?\s*%)", line, re.IGNORECASE)
    if battery:
        return normalize_value(battery.group(1))

    voltage = re.search(r"^\s*(?:battery\s+voltage|bat|adc|vbat|voltage)[:=]\s*(\d+(?:\.\d+)?\s*(?:v|mv))", line, re.IGNORECASE)
    if voltage:
        return normalize_value(voltage.group(1))

    return None


def process_device_line(line):
    global receiver_pairing_request_seen
    cleaned = strip_log_prefix(line)
    lower = cleaned.lower()
    important = False

    tracker_id = extract_labeled_value(cleaned, r"tracker\s*id")
    receiver_address = extract_labeled_value(cleaned, r"receiver\s*address")
    device_address = extract_labeled_value(cleaned, r"device\s*address")

    if tracker_id:
        set_device_type("tracker")
        set_device_field("Address", tracker_id)
        add_human_line(f"Tracker detected, id {tracker_id}.")
        important = True

    if receiver_address:
        set_device_type("tracker")
        set_device_field("Paired with", receiver_address)
        set_device_field("Pairing", "Paired")
        set_device_field("Mode", "Paired")
        add_human_line(f"Tracker paired with receiver {receiver_address}.")
        important = True

    receiver_markers = (
        "rx pairing request",
        "pairing mode",
        "saved devices",
        "hid",
        "usb receiver",
        "dongle",
    )
    tracker_markers = (
        "tracker id",
        "receiver address",
        "battery",
        "imu",
    )

    if "rx pairing request" in lower:
        set_device_type("receiver")
        set_device_field("Pairing", "Tracker request received")
        set_device_field("Mode", "Pairing")
        receiver_pairing_request_seen = True
        add_human_line("Receiver sees a tracker pairing request.")
        important = False
    elif "pairing request received" in lower:
        set_device_type("tracker")
        set_device_field("Pairing", "Pair ACK received")
        set_device_field("Mode", "Pairing")
        important = False

    stored_device = re.fullmatch(r"[0-9A-Fa-f]{12}", cleaned)
    if stored_device and last_device_type == "receiver":
        tracker_addr = cleaned.upper()
        set_device_field("Paired with", tracker_addr)
        set_device_field("Pairing", "Paired")
        set_device_field("Mode", "Paired")
        receiver_pairing_request_seen = False
        add_human_line(f"Receiver stored tracker {tracker_addr}.")
        important = True

    if device_address:
        if last_device_type == "tracker":
            set_device_type("tracker")
            set_device_field("Address", device_address)
            add_human_line(f"Tracker detected, address {device_address}.")
        else:
            set_device_type("receiver")
            set_device_field("Address", device_address)
            add_human_line(f"Receiver detected, address {device_address}.")
        important = True

    if (
        any(marker in lower for marker in receiver_markers)
        and not any(marker in lower for marker in tracker_markers)
        and "rx pairing request" not in lower
    ):
        set_device_type("receiver")
        important = True

    battery = parse_battery_line(cleaned)
    if battery:
        set_device_type("tracker")
        set_device_field("Battery", battery)
        add_human_line(f"Battery: {battery}.")
        important = True

    pairing_state = extract_labeled_value(cleaned, r"pairing\s*state")
    if pairing_state:
        set_device_field("Pairing", pairing_state)
        state_lower = pairing_state.lower()
        if "start" in state_lower:
            set_device_field("Mode", "Pairing")
        elif "stop" in state_lower or "idle" in state_lower:
            set_device_field("Mode", "Normal")
        elif "paired" in state_lower:
            set_device_field("Mode", "Paired")
        add_human_line(f"Pairing: {pairing_state}.")
        important = True
    elif re.search(r"\bpaired\b", lower):
        set_device_field("Pairing", "Paired")
        set_device_field("Mode", "Paired")
        add_human_line("Pairing completed.")
        important = True

    channel_match = re.search(r"afh(?: default)? channel[:=]\s*(-?\d+)", cleaned, re.IGNORECASE)
    if channel_match:
        channel = channel_match.group(1)
        set_device_field("AFH channel", channel)
        if channel != "100":
            add_human_line(f"AFH channel is {channel}; use Force Channel 100 if pairing fails.")
        else:
            add_human_line("AFH channel is 100, discovery channel is correct.")
        important = True

    epoch_match = re.search(r"afh epoch[:=]\s*(\d+)", cleaned, re.IGNORECASE)
    if epoch_match:
        afh_debug_state["AFH epoch"] = epoch_match.group(1)

    errors_match = re.search(r"(?:afh )?consecutive tx errors[:=]\s*(\d+)", cleaned, re.IGNORECASE)
    if errors_match:
        errors = errors_match.group(1)
        set_device_field("AFH errors", errors)
        if errors != "0":
            add_human_line(f"Radio retries/errors: {errors}.")
        important = True

    if "failed to set afh channel" in lower:
        add_human_line("Firmware rejected manual AFH channel command; pairing can still use firmware default channel 100.")
        important = True

    refresh_device_summary()
    return important

def console_print_summary(previous_snapshot):
    snapshot = tuple(device_state.get(field, "Unknown") for field in DEVICE_STATE_FIELDS)
    if snapshot != previous_snapshot:
        print("\n" + format_device_summary() + "\n", flush=True)
        return snapshot
    return previous_snapshot


def run_console_mode(port=None, baudrate=115200, raw=False, commands=None):
    ports = list_serial_ports()
    if not port:
        if not ports:
            print("No serial ports found. Connect receiver/tracker and retry.", file=sys.stderr)
            return 2
        port = ports[0]

    print(f"Opening {port} at {baudrate} baud. Press Ctrl+C to stop.")
    command_list = commands or ["info", "afh_info", "list", "battery"]
    snapshot = tuple(device_state.get(field, "Unknown") for field in DEVICE_STATE_FIELDS)
    try:
        with serial.Serial(port, baudrate, timeout=0.25) as serial_port:
            time.sleep(0.4)
            for command in command_list:
                serial_port.write((command + "\n").encode())
                print(f"> {command}")
                time.sleep(0.08)
            while True:
                raw_line = serial_port.readline()
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                important = process_device_line(line)
                update_afh_debug_state(line)
                if raw or important:
                    print(line)
                snapshot = console_print_summary(snapshot)
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 0
    except (OSError, serial.SerialException) as exc:
        print(f"Device disconnected or serial error: {exc}", file=sys.stderr)
        return 1


def parse_cli_args():
    parser = argparse.ArgumentParser(description="SmolSlime AFH configurator")
    parser.add_argument("--console", action="store_true", help="Run smart terminal console instead of GUI")
    parser.add_argument("--port", help="Serial port for --console mode")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate for --console mode")
    parser.add_argument("--raw", action="store_true", help="Show raw firmware log lines in --console mode")
    parser.add_argument("--cmd", action="append", dest="commands", help="Command to send on connect; can be used multiple times")
    return parser.parse_args()

def send_commands(commands):
    for command in commands:
        send_command(command)
        time.sleep(0.05)

def pair_afh():
    send_commands(["afh_set_channel 100", "afh_info", "pair"])

def clear_pair_afh():
    if messagebox.askyesno("Clear and Pair AFH", "This will clear saved pairing data on the connected device before AFH pairing. Continue?"):
        send_commands(["clear", "afh_set_channel 100", "afh_info", "pair"])

def run_afh_debug():
    send_commands(["info", "afh_info", "list", "battery"])

# El button to connect your Smol Slimes to El program
def connect_to_port():
    global ser, connected, read_thread, stop_read

    port = port_option.get()
    if not port or "No ports" in port:
        append_text("No valid port selected.\n", "error")
        return

    if ser and ser.is_open:
        stop_read.set()
        try:
            ser.close()
        except Exception:
            pass
        ser = None
        connected = False

    stop_read = threading.Event()

    try:
        ser = serial.Serial(port, 115200, timeout=1)
        connected = True
        set_status(f"Connected to {port}", "green")
        append_text(f"Connected to {port}\n", "success")
        set_device_field("Mode", "Detecting")
        set_device_field("Device type", "Detecting")
        refresh_device_summary()

        read_thread = threading.Thread(target=read_serial, daemon=True)
        read_thread.start()
        schedule_after(250, run_afh_debug)

    except serial.SerialException as e:
        append_text(f"Failed to connect: {e}\n")
        set_status("Connection failed", "red")

# If smolslime escapes (disconnects) de program tries to catch it and put it back in the dungeon (reconnects)
def attempt_reconnect():
    global ser, connected, stop_read, read_thread

    port = port_option.get()
    if not port or "No ports" in port:
        append_text("No valid port to reconnect.\n")
        return

    def reconnect_loop():
        global ser, connected, stop_read, read_thread
        retries = 0
        max_retries = 15 // 2

        while not connected and retries < max_retries:
            try:
                if ser and ser.is_open:
                    with ser_lock:
                        ser.close()
                    ser = None

                ser = serial.Serial(port, 115200, timeout=1)
                connected = True
                stop_read.clear()
                read_thread = threading.Thread(target=read_serial, daemon=True)
                read_thread.start()
                set_status(f"Connected to {port}", "green")
                append_text("\nSuccessfully reconnected!\n", "success")
                break

            except serial.SerialException:
                retries += 1
                append_text(".", None)
                time.sleep(2)

        if not connected:
            append_text("\nFailed to reconnect.\n", "error")
            set_status("Not connected", "red")

    threading.Thread(target=reconnect_loop, daemon=True).start()

# Send commands via serial,
def send_command(cmd):
    global ser, connected
    if ser and ser.is_open:
        try:
            with ser_lock:
                ser.write((cmd + "\n").encode())
            append_text(f">>> {cmd}\n")
        except (serial.SerialException, OSError) as e:
            append_text(f"[Error] Serial write failed: {e}\n", "error")
            disconnect_serial()
    else:
        append_text("Not connected.\n", "error")

def read_serial():
    global ser, stop_read, connected
    while not stop_read.is_set():
        try:
            if ser and ser.in_waiting:
                with ser_lock:
                    line = ser.readline().decode(errors="ignore").rstrip('\r\n \t')
                if line:
                    serial_queue.put(line)
            else:
                time.sleep(0.01)
        except (OSError, serial.SerialException) as e:
            append_text("Device disconnected; waiting for it to reappear...\n", "error")
            disconnect_serial()
            attempt_reconnect()
            break


def disconnect_serial():
    global ser, connected
    try:
        if ser:
            with ser_lock:
                ser.close()
    except Exception:
        pass
    ser = None
    connected = False
    set_device_field("Mode", "Disconnected")
    refresh_device_summary()
    set_status("Not connected", "red")

# Let the code add MORE!! (more lines of serial that is)
def append_text(text, color=None):
    if threading.current_thread() is not main_thread:
        ui_queue.put((append_text, (text, color), {}))
        return

    console.configure(state="normal")
    tag = None
    if color == "error":
        tag = "red"
    elif color == "success":
        tag = "green"

    at_bottom = console.yview()[1] == 1.0

    if tag:
        console.insert("end", text, tag)
    else:
        console.insert("end", text)

    if at_bottom:
        console.see("end")

    console.configure(state="disabled")

# The thing that asks for the custom .U2F
def on_tracker_change(choice):
    global custom_fw_path
    if choice == "Custom…":
        path = filedialog.askopenfilename(title="Select firmware (.uf2 or .hex)", filetypes=[("Firmware files", "*.uf2 *.hex"), ("UF2 files", "*.uf2"), ("HEX files", "*.hex")])
        if path:
            custom_fw_path = path
            send_button.configure(text=f"Flash: {os.path.basename(path)}")
        else:
            tracker_select.set(tracker_names[0])
    else:
        custom_fw_path = None
        send_button.configure(text="Flash Firmware")


# Top UI | Yk the serial buttons
top_frame = ctk.CTkFrame(app)
top_frame.pack(pady=5, padx=10, fill="x")

initial_ports = list_serial_ports()
if not initial_ports:
    initial_ports = ["No ports found"]

port_option = ctk.CTkOptionMenu(top_frame, values=initial_ports)
port_option.set(initial_ports[0])
port_option.pack(side="left", padx=5)
ToolTip(port_option, "Select the port for your device")

btn_refresh = ctk.CTkButton(top_frame, text="↻", width=10, command=refresh_ports)
btn_refresh.pack(side="left", padx=5)
ToolTip(btn_refresh, "Refresh serial port")

btn_connect = ctk.CTkButton(top_frame, text="Connect", command=connect_to_port)
btn_connect.pack(side="left", padx=5)
ToolTip(btn_connect, "Connect to the selected serial port")

progress_bar = ctk.CTkProgressBar(app, width=1000)
progress_bar.set(0)
hide_progress()

firmware_urls = {"Custom (User provided .uf2 / .hex)": None}

# Fill the dropdown menu with latest releases
selected_firmware = tk.StringVar(value="Select Firmware")

current_os = platform.system()
if current_os == "Darwin":
    mac_or_other = "Middle"
else:
    mac_or_other = "Right"
    
def open_firmware_popup():
    fw_buttons = {}
    global firmware_urls
    popup = ctk.CTkToplevel(app)
    popup.title("Select Firmware")
    popup.geometry("300x400")
    popup.transient(app)
    
    # R-Click Hint (Middle-Click on mac)
    if not settings.get("seen_favorite_hint", False):
        hint_popup = ctk.CTkToplevel(popup)
        hint_popup.title("Tip")
        hint_popup.geometry("260x100")
        hint_popup.transient(popup)

        hint_label = ctk.CTkLabel(
            hint_popup,
            text=f"{mac_or_other} click firmware to star it!\nFavorites appear first and in gold",
            justify="center",
            wraplength=220
        )
        hint_label.pack(expand=True, fill="both", padx=10, pady=10)

        ok_button = ctk.CTkButton(hint_popup, text="Got it!", command=hint_popup.destroy)
        ok_button.pack(pady=(0, 10))

        settings["seen_favorite_hint"] = True
        save_settings()

        hint_popup.wait_visibility()
        hint_popup.grab_set()


    def open_docs():
        webbrowser.open("https://docs.slimevr.dev/smol-slimes/firmware/smol-pre-compiled-firmware.html#-tracker")

    help_button = ctk.CTkButton(
        popup, text="Which Firmware to pick?", command=open_docs,
        fg_color="red", hover_color="#cc0000", text_color="white"
    )
    help_button.pack(padx=10, pady=(10, 5), fill="x")

    # Search bar
    search_var = tk.StringVar()

    search_entry = ctk.CTkEntry(popup, placeholder_text="Search firmware or paste URL...", textvariable=search_var)
    search_entry.pack(padx=10, pady=(0, 5), fill="x")

    scroll_frame = ctk.CTkScrollableFrame(popup, width=280, height=320)
    scroll_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)
    canvas = scroll_frame._parent_canvas

    def scrollf(event):
        if sys.platform.startswith("linux"):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
        else:
            canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    if sys.platform.startswith("linux"):
        canvas.bind("<Button-4>", scrollf)
        canvas.bind("<Button-5>", scrollf)
    else:
        canvas.bind("<MouseWheel>", scrollf)
# fave ting ting
    def toggle_favorite(fw):
        favs = settings.setdefault("favorites", [])
        is_fav = fw in favs

        if is_fav:
            favs.remove(fw)
        else:
            favs.append(fw)

        save_settings()

        btn = fw_buttons.get(fw)
        if not btn:
            return

        btn.configure(
            text=("☆ " if not is_fav else "") + fw,
            text_color="gold" if not is_fav else ctk.ThemeManager.theme["CTkButton"]["text_color"]
        )

        if not is_fav:
            children = scroll_frame.winfo_children()
            if children and children[0] is not btn:
                btn.pack_forget()
                btn.pack(fill="x", pady=2, before=children[0])

            scroll_frame._parent_canvas.yview_moveto(0)


    def select_fw(fw):
        selected_firmware.set(fw)
        popup.destroy()

    def update_list(*args):
        fw_buttons.clear()

        search_term = search_var.get().lower()
        for widget in scroll_frame.winfo_children():
            widget.destroy()

        favs = settings.get("favorites", [])
        items = list(firmware_urls.keys())
        sorted_items = sorted(items, key=lambda x: (x not in favs, x.lower()))

        for fw in sorted_items:
            if search_term in fw.lower():
                is_fav = fw in favs
                btn = ctk.CTkButton(
                    scroll_frame,
                    text=("☆ " if is_fav else "") + fw,
                    command=lambda f=fw: select_fw(f),
                    text_color="gold" if is_fav else None
                )
                btn.pack(fill="x", pady=2)

                # Right click (or middle click on mac)
                btn.bind("<Button-3>", lambda e, f=fw: toggle_favorite(f))

                fw_buttons[fw] = btn


    def on_paste_url(*args):
        text = search_var.get().strip()
        match = re.search(r'([^/\\]+\.uf2)$', text)
        if match:
            filename = match.group(1)
            search_var.set(filename)
        update_list()

    search_var.trace_add("write", on_paste_url)
    
    def _on_mousewheel(event):
        scroll_frame._parent_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    scroll_frame.bind_all("<MouseWheel>", _on_mousewheel)
    scroll_frame.bind_all("<Button-4>", lambda e: scroll_frame._parent_canvas.yview_scroll(-1, "units"))
    scroll_frame.bind_all("<Button-5>", lambda e: scroll_frame._parent_canvas.yview_scroll(1, "units"))

    update_list()
    popup.after(10, lambda: popup.grab_set())

# Button to open firmware popup
firmware_button = ctk.CTkButton(
    top_frame, textvariable=selected_firmware, command=open_firmware_popup, width=200
)
firmware_button.pack(side="left", padx=5)
ToolTip(firmware_button, "Select the Firmware version for your smolslime")

# Populate firmware menu
def populate_firmware_menu():
    global firmware_urls
    auto_fw = fetch_latest_firmware_assets()
    if auto_fw:
        firmware_urls = {**auto_fw, "Custom (User provided .uf2 / .hex)": None}
    else:
        firmware_urls = {"Custom (User provided .uf2 / .hex)": None}


app.after(100, populate_firmware_menu)

# Loading bar
def animate_progress(target, step=0.02, interval=50):
    if threading.current_thread() is not main_thread:
        run_on_ui_thread(animate_progress, target, step, interval)
        return

    current = progress_bar.get()
    if current < target:
        progress_bar.set(min(current + step, target))
        app.after(interval, lambda: animate_progress(target, step, interval))
    elif target == 1.0:
        app.after(2000, progress_bar.pack_forget)

def get_nrfutil_path():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        return os.path.join(base_path, "nrfutil")
    else:
        return "nrfutil"

# HEX flashing usin command thingy, Shud work gud
def flash_hex_firmware(file_path):
    global ser, connected
    if not ser or not ser.is_open:
        append_text("Device not connected.\n", "error")
        return
    
    append_text("Entering bootloader...\n")
    send_command("dfu")
    time.sleep(2)

    port = ser.port
    append_text(f"Starting Flash on port: {port}...\n")
    ser.close()
    ser = None
    connected = False
    nrfutil_cmd = get_nrfutil_path()

    try:
        dfu_package = os.path.splitext(file_path)[0] + "_dfu_package.zip"

        append_text("Generating DFU package...\n")
        subprocess.run([
            nrfutil_cmd, "pkg", "generate",
            "--hw-version", "52",
            "--application-version", "1",
            "--sd-req", "0x00",
            "--application", file_path,
            dfu_package
        ], check=True, shell=False)

        append_text("Flashing DFU package via serial...\n")
        subprocess.run([
            nrfutil_cmd, "dfu", "serial",
            "--package", dfu_package,
            "--port", port,
            "--baud-rate", "115200"
        ], check=True, shell=False)

        append_text("YAY! FW Flashed!!!\n", "success")
        set_progress(1.0)

    except FileNotFoundError:
        append_text("Error 420: run 'pip install nrfutil'.\n", "error")
    except subprocess.CalledProcessError as e:
        append_text(f"Error code: {e}\n", "error")
    finally:
        try:
            if os.path.exists(dfu_package):
                os.remove(dfu_package)
        except Exception:
            pass



def download_artifact_firmware(artifact_url):
    temp_dir = tempfile.mkdtemp(prefix="smolslime_artifact_")
    zip_path = os.path.join(temp_dir, "artifact.zip")
    append_text(f"Downloading firmware artifact from {artifact_url}...\n", "success")
    response = requests.get(artifact_url, headers=github_headers(), stream=True, timeout=30)
    response.raise_for_status()
    with open(zip_path, "wb") as f:
        shutil.copyfileobj(response.raw, f)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(temp_dir)

    for root, _, files in os.walk(temp_dir):
        for filename in files:
            if filename.lower().endswith((".uf2", ".hex")):
                firmware_path = os.path.join(root, filename)
                append_text(f"Using extracted firmware: {firmware_path}\n", "success")
                return firmware_path

    raise FileNotFoundError("Artifact zip did not contain a .uf2 or .hex firmware file")

# Download the firmware once user selected and pressed the Firmware button,
# and also the actual logic for flashing (Resets, puts into DFU, waits for drive to appear, moves the .U2F to the drive)
def download_firmware():
    selection = selected_firmware.get()


    if selection == "Select Firmware":
        append_text("Please select a firmware option.\n", "error")
        return

    

    if selection == "Custom (User provided .uf2 / .hex)":
        file_path = call_on_ui_thread_sync(filedialog.askopenfilename, filetypes=[("Firmware files", "*.uf2 *.hex"), ("UF2 files", "*.uf2"), ("HEX files", "*.hex")])
        if not file_path:
            append_text("No custom firmware selected.\n")
            return
        append_text(f"Selected custom firmware: {file_path}\n")
        local_path = file_path
        if local_path.endswith(".hex"):
            append_text("Starting flashing... [HEX]\n", "success")
            flash_hex_firmware(local_path)
            return
    else:
        firmware_url = firmware_urls.get(selection)
        if not firmware_url:
            append_text("No firmware URL for selected firmware.\n")
            return

        try:
            if firmware_url.startswith("artifact::"):
                local_path = download_artifact_firmware(firmware_url.removeprefix("artifact::"))
            else:
                local_path = os.path.join(tempfile.gettempdir(), os.path.basename(firmware_url))
                append_text(f"Downloading firmware from {firmware_url}...\n", "success")
                response = requests.get(firmware_url, stream=True, timeout=20)
                response.raise_for_status()
                with open(local_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f)

                append_text(f"Firmware downloaded to: {local_path}\n", "success")
            if local_path.endswith(".hex"):
                append_text("yoo HEX file! Loading...\n", "success")
                flash_hex_firmware(local_path)
                return

        except Exception as e:
            append_text(f"[Error] Firmware download failed: {e}\n", "error")
            return
    show_progress()
    animate_progress(0.2)

    append_text("Clearing Connection data and entering bootloader mode...\n")
    send_command("clear")
    time.sleep(0.5)
    send_command("dfu")
    animate_progress(0.4)

    append_text("Waiting up to 5 seconds for UF2 device to appear. If you have issues, please post an issue https://github.com/ICantMakeThings/SmolSlimeConfigurator \n")
    time.sleep(5)

    mount_point = None
    system = platform.system()
    candidate_paths = []

    try:
        if system == "Windows":
            import win32api
            candidate_paths = win32api.GetLogicalDriveStrings().split('\000')[:-1]

        elif system == "Darwin":
            candidate_paths = [
                os.path.join("/Volumes", d)
                for d in os.listdir("/Volumes")
            ]

        elif system == "Linux":
            mount_roots = [
                "/run/media",
                "/media",
                "/mnt"
            ]

            for media_root in mount_roots:
                if not os.path.isdir(media_root):
                    continue

                for root, dirs, _ in os.walk(media_root):
                    for d in dirs:
                        candidate_paths.append(os.path.join(root, d))

        for path in candidate_paths:
            try:
                if os.path.isfile(os.path.join(path, "INFO_UF2.TXT")):
                    mount_point = path
                    break
            except Exception:
                continue


        if mount_point and os.path.isdir(mount_point):
            dest = os.path.join(mount_point, os.path.basename(local_path))
            append_text(f"Copying firmware to {dest}...\n")
            shutil.copy(local_path, dest)
            append_text(f"DONE: Firmware successfully flashed to {mount_point}\n", "success")
            animate_progress(1.0)
            schedule_after(2000, progress_bar.pack_forget)

        else:
            append_text("ERROR: Could not find NICENANO or UF2 boot device. Is the device in DFU/bootloader mode?\n", "error")
        hide_progress()

    except Exception as e:
        append_text(f"[Error flashing] {e}\n", "error")
        append_text("NOTE! On windows [WinError 433] doesn't mean it failed!\n", "success")
        hide_progress()


def update_afh_debug_state(line):
    global pairing_request_spam_count, pairing_hint_shown
    cleaned = strip_log_prefix(line)
    lower = cleaned.lower()
    patterns = {
        "Tracker ID": [r"tracker\s*id[:=]\s*([^,;]+)", r"id[:=]\s*([^,;]+)"],
        "Receiver address": [r"receiver\s*address[:=]\s*([^,;]+)", r"rx\s*addr(?:ess)?[:=]\s*([^,;]+)"],
        "Device address": [r"device\s*address[:=]\s*([^,;]+)", r"dev\s*addr(?:ess)?[:=]\s*([^,;]+)"],
        "AFH channel": [r"afh(?:\s+channel| channel)?[:=]\s*(\d+)", r"channel[:=]\s*(\d+)"],
        "AFH epoch": [r"epoch[:=]\s*(\d+)"],
        "AFH consecutive TX errors": [r"consecutive\s+tx\s+errors[:=]\s*(\d+)", r"tx\s+errors[:=]\s*(\d+)"]
    }
    for field, regexes in patterns.items():
        for regex in regexes:
            match = re.search(regex, cleaned, re.IGNORECASE)
            if match:
                afh_debug_state[field] = match.group(1).strip()
                break

    if "pairing request received" in lower:
        pairing_request_spam_count += 1
        afh_debug_state["pairing state"] = "Pairing request received"
    if "paired" in lower:
        pairing_request_spam_count = 0
        afh_debug_state["pairing state"] = "Paired"
    elif "pair" in lower and "request" not in lower:
        afh_debug_state["pairing state"] = cleaned

    if pairing_request_spam_count >= 3 and not pairing_hint_shown:
        pairing_hint_shown = True
        append_text("Hint: Tracker requests are reaching a receiver, but no pair ACK was accepted yet. Keep receiver in Start AFH Pairing, and use Pair AFH on one tracker at a time.\n", "error")

def save_debug_log():
    path = filedialog.asksaveasfilename(
        title="Save AFH debug log",
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not path:
        return
    console_text = console.get("1.0", "end-1c")
    with open(path, "w", encoding="utf-8") as f:
        f.write("AFH Debug State\n")
        f.write("===============\n")
        for field in AFH_DEBUG_FIELDS:
            f.write(f"{field}: {afh_debug_state.get(field, 'Unknown')}\n")
        f.write("\nConsole Log\n")
        f.write("===========\n")
        f.write(console_text)
    append_text(f"Saved AFH debug log to {path}\n", "success")

# Buttons!
def start_firmware_download():
    threading.Thread(target=download_firmware, daemon=True).start()

btn_download_fw = ctk.CTkButton(top_frame, text="⬇ Firmware", width=80, command=start_firmware_download)
btn_download_fw.pack(side="left", padx=5)
ToolTip(btn_download_fw, "Upgrade your firmware!")

status_label = ctk.CTkLabel(top_frame, text="Not connected", text_color="red")
status_label.pack(side="left", padx=10)

tab_view = ctk.CTkTabview(app, width=1000, height=170, corner_radius=10, anchor="w")
tab_view.pack(pady=10, padx=10, fill="x")



# Make the repetitive stuff less messy
def ui_btn(parent, text, command, tooltip, width=110):
    btn = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width,
        height=30,
        anchor="center"
    )
    ToolTip(btn, tooltip)
    return btn


# Tracker tab
tracker_tab = tab_view.add("Tracker")
tracker_btn_frame = ctk.CTkFrame(tracker_tab)
tracker_btn_frame.pack(pady=10, padx=10)

ui_btn(tracker_btn_frame, "Info", lambda: send_command("info"), "Get device information").grid(row=0, column=0, padx=5, pady=5)
ui_btn(tracker_btn_frame, "Pair AFH", pair_afh, "Set channel 100, print AFH info, then pair safely").grid(row=0, column=1, padx=5, pady=5)
ui_btn(tracker_btn_frame, "Clear+Pair AFH", clear_pair_afh, "Clear pairing data, set channel 100, then pair", width=135).grid(row=0, column=2, padx=5, pady=5)
ui_btn(tracker_btn_frame, "Battery", lambda: send_command("battery"), "Get battery information").grid(row=0, column=3, padx=5, pady=5)
ui_btn(tracker_btn_frame, "AFH Info", lambda: send_command("afh_info"), "Show AFH channel, state, errors, and epoch").grid(row=0, column=4, padx=5, pady=5)
ui_btn(tracker_btn_frame, "Debug Log", save_debug_log, "Save parsed AFH state and console text", width=120).grid(row=0, column=5, padx=5, pady=5)
ui_btn(tracker_btn_frame, "DFU", lambda: send_command("dfu"), "Enter DFU bootloader (if available)").grid(row=0, column=6, padx=5, pady=5)

# Receiver tab
receiver_tab = tab_view.add("Receiver")
receiver_btn_frame = ctk.CTkFrame(receiver_tab)
receiver_btn_frame.pack(pady=10, padx=10)

ui_btn(receiver_btn_frame, "Info", lambda: send_command("info"), "Get device information").grid(row=0, column=0, padx=5, pady=5)
ui_btn(receiver_btn_frame, "List", lambda: send_command("list"), "Get paired devices").grid(row=0, column=1, padx=5, pady=5)
ui_btn(receiver_btn_frame, "Start AFH Pairing", pair_afh, "Set channel 100, print AFH info, then enter receiver pairing", width=145).grid(row=0, column=2, padx=5, pady=5)
ui_btn(receiver_btn_frame, "Exit Pairing", lambda: send_command("exit"), "Exit pairing mode", width=120).grid(row=0, column=3, padx=5, pady=5)
ui_btn(receiver_btn_frame, "AFH Info", lambda: send_command("afh_info"), "Show AFH channel, state, errors, and epoch").grid(row=0, column=4, padx=5, pady=5)
ui_btn(receiver_btn_frame, "Debug Log", save_debug_log, "Save parsed AFH state and console text", width=120).grid(row=0, column=5, padx=5, pady=5)
ui_btn(receiver_btn_frame, "DFU", lambda: send_command("dfu"), "Enter DFU bootloader (if available)").grid(row=0, column=6, padx=5, pady=5)

# Settings tab
settings_tab = tab_view.add("Settings")
settings_frame = ctk.CTkFrame(settings_tab)
settings_frame.pack(padx=10, pady=10, fill="both", expand=True)
settings_frame.grid_columnconfigure(0, weight=1)
settings_frame.grid_columnconfigure(1, weight=1)

# Platform name ting ting
platform_name = platform.system()
if platform_name == "Darwin":
    platform_name = "macOS"
elif platform_name == "Windows":
    platform_name = "Windows"
elif platform_name == "Linux":
    platform_name = "Linux"

version_label = ctk.CTkLabel(
    settings_frame,
    text=f"SmolSlimeConfigurator Version 9 ({platform_name})",
    text_color="gray"
)
version_label.pack(anchor="ne", padx=10, pady=5)

firmware_frame = ctk.CTkFrame(settings_frame)
firmware_frame.pack(pady=10, fill="x")

ctk.CTkLabel(
    firmware_frame,
    text="Firmware Source:",
    font=ctk.CTkFont(weight="bold")
).pack(anchor="w", padx=5, pady=(0, 5))

# Firmware repo select

firmware_source_var = tk.StringVar(value=settings.get("firmware_source", "main"))

def on_firmware_source_change():
    settings["firmware_source"] = firmware_source_var.get()
    save_settings()
    populate_firmware_menu()

rb_main = ctk.CTkRadioButton(
    firmware_frame,
    text="Main (Shine-Bright-Meow)",
    variable=firmware_source_var,
    value="main",
    command=on_firmware_source_change
)
rb_main.pack(anchor="w", padx=10)
ToolTip(rb_main, "Main firmware repo")

rb_kouno = ctk.CTkRadioButton(
    firmware_frame,
    text="Kounocom (Backup)",
    variable=firmware_source_var,
    value="kounocom",
    command=on_firmware_source_change
)
rb_kouno.pack(anchor="w", padx=10)
ToolTip(rb_kouno, "Backup firmware option")

rb_custom = ctk.CTkRadioButton(
    firmware_frame,
    text="Custom Repo",
    variable=firmware_source_var,
    value="custom",
    command=on_firmware_source_change
)
rb_custom.pack(anchor="w", padx=10)
ToolTip(rb_custom, "Custom firmware repo")

custom_repo_entry = ctk.CTkEntry(
    firmware_frame,
    placeholder_text="https://api.github.com/repos/user/repo/releases/latest"
)
custom_repo_entry.pack(fill="x", padx=20, pady=(5, 0))
custom_repo_entry.insert(0, settings.get("custom_firmware_repo", ""))

def save_custom_repo(*args):
    settings["custom_firmware_repo"] = custom_repo_entry.get().strip()
    save_settings()

custom_repo_entry.bind("<FocusOut>", save_custom_repo)
ToolTip(custom_repo_entry, "Custom firmware repo")

def toggle_theme(choice):
    settings["theme"] = choice
    ctk.set_appearance_mode(choice)

    if sys.platform.startswith("linux"):
        set_linux_scaling()

    save_settings()

def toggle_accent(choice):
    settings["accent"] = choice
    ctk.set_default_color_theme(choice)
    save_settings()

def toggle_tooltips():
    global TOOLTIPS_ENABLED
    settings["tooltips"] = not settings["tooltips"]
    TOOLTIPS_ENABLED = settings["tooltips"]
    save_settings()
    append_text(f"Tooltips {'enabled' if TOOLTIPS_ENABLED else 'disabled'}.\n", "success")

def open_repo():
    webbrowser.open("https://github.com/ICantMakeThings/SmolSlimeConfigurator")

appearance_frame = ctk.CTkFrame(settings_frame)
appearance_frame.pack(pady=10, fill="x")

ctk.CTkLabel(appearance_frame, text="Appearance Mode:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
theme_menu = ctk.CTkOptionMenu(appearance_frame, values=["light", "dark"], command=toggle_theme)
theme_menu.set(settings["theme"])
theme_menu.grid(row=0, column=1, padx=5, pady=5, sticky="w")

ctk.CTkLabel(appearance_frame, text="Accent Colour:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
accent_menu = ctk.CTkOptionMenu(appearance_frame, values=["blue", "green", "dark-blue"], command=toggle_accent)
accent_menu.set(settings["accent"])
accent_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")
ToolTip(accent_menu, "Requires app restart")

# Buttonssss
button_row = ctk.CTkFrame(settings_frame)
button_row.pack(pady=15)

tooltips_button = ctk.CTkButton(button_row, text="Toggle Tooltips", command=toggle_tooltips)
tooltips_button.pack(side="left", padx=10)
ToolTip(tooltips_button, "Yk what each button does? Turn off tooltips!")


repo_button = ctk.CTkButton(button_row, text="Open GitHub Repo", command=open_repo)
repo_button.pack(side="left", padx=10)

ToolTip(repo_button, "github.com/ICantMakeThings/SmolSlimeConfigurator")


# Human-readable device summary
summary_frame = ctk.CTkFrame(app)
summary_frame.pack(pady=(0, 6), padx=10, fill="x")
summary_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

device_cards = {}
for idx, field in enumerate(DEVICE_STATE_FIELDS):
    card = ctk.CTkFrame(summary_frame)
    card.grid(row=idx // 4, column=idx % 4, padx=5, pady=4, sticky="ew")
    ctk.CTkLabel(card, text=field, text_color="gray", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=(5, 0))
    value_label = ctk.CTkLabel(card, text=device_state[field], font=ctk.CTkFont(weight="bold"), wraplength=220)
    value_label.pack(anchor="w", padx=8, pady=(0, 5))
    device_cards[field] = value_label

human_summary_label = ctk.CTkLabel(summary_frame, text="No important events yet.", justify="left", anchor="w", wraplength=980)
human_summary_label.grid(row=2, column=0, columnspan=4, padx=8, pady=(2, 6), sticky="ew")

console_mode_frame = ctk.CTkFrame(app)
console_mode_frame.pack(pady=(0, 4), padx=10, fill="x")
raw_console_var = tk.BooleanVar(value=settings.get("raw_console_enabled", False))
raw_console_enabled = raw_console_var.get()
raw_switch = ctk.CTkSwitch(
    console_mode_frame,
    text="Raw console / сырые логи",
    variable=raw_console_var,
    command=lambda: set_raw_console_enabled(raw_console_var.get()),
)
raw_switch.pack(side="left", padx=8, pady=5)
ctk.CTkLabel(console_mode_frame, text="Smart GUI mode summarizes noisy firmware logs for normal users.", text_color="gray").pack(side="left", padx=8)

# CLI
console = ctk.CTkTextbox(app, width=1000, height=165, corner_radius=10)
console.tag_config("red", foreground="red")
console.tag_config("green", foreground="lime")

console.pack(pady=(0, 5), padx=10)
console.configure(state="disabled")

def send_custom_command():
    cmd = command_entry.get().strip()
    if cmd:
        send_command(cmd)
        command_entry.delete(0, "end")

entry_frame = ctk.CTkFrame(app)
entry_frame.pack(pady=5, padx=10, fill="x")

command_entry = ctk.CTkEntry(entry_frame, placeholder_text="Enter custom command...")
command_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=5)

btn_send = ctk.CTkButton(entry_frame, text="Send", width=80, command=send_custom_command)
btn_send.pack(side="left", pady=5)

btn_clear = ctk.CTkButton(entry_frame, text="X", width=30, command=lambda: console.configure(state="normal") or console.delete("1.0", "end") or console.configure(state="disabled"))
btn_clear.pack(side="left", padx=(5,0), pady=5)
ToolTip(btn_clear, "Clear")

command_entry.bind("<Return>", lambda event: send_custom_command())

# App icons are nice, but missing/bad icon files must never prevent the
# Windows PyInstaller build from opening. Fall back to the default Tk icon.
def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def set_app_icon():
    icon_ico = resource_path("icon.ico")
    icon_png = resource_path("icon.png")

    if sys.platform.startswith("win") and os.path.exists(icon_ico):
        try:
            app.iconbitmap(icon_ico)
            return
        except tk.TclError as e:
            print(f"[Warning] Could not load icon.ico: {e}")

    if os.path.exists(icon_png):
        try:
            img = tk.PhotoImage(file=icon_png)
            app.iconphoto(True, img)
        except tk.TclError as e:
            print(f"[Warning] Could not load icon.png: {e}")

set_app_icon()



def flush_ui_queue():
    while not ui_queue.empty():
        func, args, kwargs = ui_queue.get()
        func(*args, **kwargs)

    while not serial_queue.empty():
        line = serial_queue.get()
        important = process_device_line(line)
        update_afh_debug_state(line)
        if raw_console_enabled or important:
            append_text(line + "\n")

    app.after(50, flush_ui_queue)

app.after(50, flush_ui_queue)
# The MOST PORTAN' PART!!!
app.mainloop()
