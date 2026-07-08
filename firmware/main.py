# Wispr Flow BLE -> USB keyboard dongle for Raspberry Pi Pico 2 W (MicroPython).
#
# Phone sends TEXT over BLE (Nordic UART Service). We map each character to a
# USB HID keycode locally, per keyboard layout, so English AND Italian both
# type correctly on the host. See runbook.md.
#
# SECURITY: the dongle types NOTHING until the connected client sends the
# correct unlock password. Stock MicroPython on the Pico 2 W cannot do BLE
# pairing/bonding, so this application-layer password is the real guard against
# a stranger connecting over Bluetooth and injecting keystrokes. Password is
# stored in wispr_pass.txt on the board (change it with %%SETPASS when unlocked,
# or from the web app's settings).
#
# Wire protocol (each on its own line, \n-terminated):
#   %%PASS <password>   unlock this connection (required first)
#   %%SETPASS <new>     change the password (only when already unlocked)
#   %%IT / %%US         set the dongle's layout table
#   %%SWITCH            flip IT<->US AND press Ctrl+Space on the host
#   %%CYCLE             host: Ctrl+Option+Space (next input source)
#   %%ENTER / %%NOENTER press Enter after each message / don't (default)
#   anything else       typed on the host (only while unlocked)

import bluetooth
import struct
import time
from micropython import const
from machine import Pin

import usb.device
from usb.device.keyboard import KeyboardInterface, KeyCode

import layouts

# ---------------------------------------------------------------- USB HID ----
kbd = KeyboardInterface()
usb.device.get().init(kbd, builtin_driver=True)  # builtin_driver keeps REPL

SHIFT = KeyCode.LEFT_SHIFT
ALTGR = KeyCode.RIGHT_ALT

_t = time.ticks_ms()
while not kbd.is_open() and time.ticks_diff(time.ticks_ms(), _t) < 5000:
    time.sleep_ms(50)
time.sleep_ms(300)
kbd.send_keys(())          # warm up endpoint so first keystroke isn't dropped
time.sleep_ms(50)

# ------------------------------------------------------------- LED status ----
led = Pin("LED", Pin.OUT)

# --------------------------------------------------------------- password ----
_PASS_FILE = "wispr_pass.txt"
_DEFAULT_PASS = "changeme"


def load_password():
    try:
        with open(_PASS_FILE) as f:
            p = f.read().strip()
            return p if p else _DEFAULT_PASS
    except OSError:
        save_password(_DEFAULT_PASS)
        return _DEFAULT_PASS


def save_password(p):
    with open(_PASS_FILE, "w") as f:
        f.write(p)


password = load_password()

# ------------------------------------------------------------------- name ----
_NAME_FILE = "wispr_name.txt"


def default_name():
    import machine, ubinascii
    uid = ubinascii.hexlify(machine.unique_id()).decode().upper()
    return "WisprDongle-" + uid[-4:]   # unique per board, so two are distinct


def load_name():
    try:
        with open(_NAME_FILE) as f:
            n = f.read().strip()
            if n:
                return n[:24]           # keep adv packet <= 31 bytes
    except OSError:
        pass
    return default_name()


def save_name(n):
    with open(_NAME_FILE, "w") as f:
        f.write(n[:24])

# ------------------------------------------------- smart-punctuation clean ----
SUBS = {
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "–": "-", "—": "-",
    "…": "...",
    " ": " ",
    "​": "",
    "•": "-",
}


def sanitize(text):
    for bad, good in SUBS.items():
        text = text.replace(bad, good)
    return text


active = "IT"
type_enter = False


def type_char(ch):
    if ch == "\n":
        kbd.send_keys([KeyCode.ENTER]); kbd.send_keys(())
        return
    if ch == "\t":
        kbd.send_keys([KeyCode.TAB]); kbd.send_keys(())
        return
    packed = layouts.LAYOUTS[active].get(ch)
    if packed is None:
        return
    keycode = packed & 0x7F
    keys = [keycode]
    if packed & 0x100:
        keys.append(SHIFT)
    if packed & 0x200:
        keys.append(ALTGR)
    kbd.send_keys(keys)
    kbd.send_keys(())


def type_text(text):
    for ch in text:
        type_char(ch)
        led.toggle()
        time.sleep_ms(4)
    led.on()


def _press(*keys):
    kbd.send_keys(list(keys))
    time.sleep_ms(30)
    kbd.send_keys(())
    time.sleep_ms(30)


# ------------------------------------------------------------- BLE / NUS ------
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_RX = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_WRITE)
_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_NOTIFY)
_UART_SERVICE = (_UART_UUID, (_RX, _TX))

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID128 = const(0x07)


def _adv_payload(name):
    p = bytearray()
    p += struct.pack("BB", 2, _ADV_TYPE_FLAGS) + struct.pack("B", 0x06)
    n = name.encode()
    p += struct.pack("BB", len(n) + 1, _ADV_TYPE_NAME) + n
    return p


def _resp_payload(service_uuid):
    b = bytes(service_uuid)
    return struct.pack("BB", len(b) + 1, _ADV_TYPE_UUID128) + b


class NUSDongle:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._rx_h, self._tx_h),) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._ble.gatts_set_buffer(self._rx_h, 512, True)
        self._conn = None
        self._buf = bytearray()      # raw bytes; decoded per-line (UTF-8 safe)
        self._unlocked = False       # LOCKED until correct %%PASS this session
        self._name = load_name()
        self._payload = _adv_payload(self._name)
        self._resp = _resp_payload(_UART_UUID)
        self._advertise()
        print("advertising as", self._name, "- LOCKED until password")

    def _advertise(self):
        self._ble.gap_advertise(100000, adv_data=self._payload, resp_data=self._resp)

    def _notify(self, msg):
        # Tell the phone our lock state (best-effort).
        if self._conn is not None:
            try:
                self._ble.gatts_notify(self._conn, self._tx_h, msg)
            except Exception:
                pass

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn, _, _ = data
            self._unlocked = False   # every new connection starts LOCKED
            self._buf = bytearray()
            led.on()
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn = None
            self._unlocked = False
            self._buf = bytearray()
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn, attr = data
            if attr == self._rx_h:
                chunk = self._ble.gatts_read(self._rx_h)
                if chunk:
                    self._buf += chunk   # accumulate raw bytes, decode later

    def _handle_line(self, line):
        # line is a decoded str (one message, no trailing newline).
        global active, type_enter, password
        s = line.strip()
        u = s.upper()

        # --- auth commands (allowed while LOCKED) ---
        if u.startswith("%%PASS"):
            attempt = s[6:].lstrip(": ").strip()
            if attempt == password:
                self._unlocked = True
                self._notify(b"OK\n")
            else:
                self._unlocked = False
                self._notify(b"BAD\n")
            return
        if not self._unlocked:
            self._notify(b"LOCKED\n")     # ignore everything until unlocked
            return

        # --- commands allowed only while UNLOCKED ---
        if u.startswith("%%SETPASS"):
            newp = s[9:].lstrip(": ").strip()
            if newp:
                password = newp
                try:
                    save_password(newp)
                    self._notify(b"PASS-SET\n")
                except Exception:
                    self._notify(b"PASS-ERR\n")
            return
        if u.startswith("%%SETNAME"):
            newn = s[9:].lstrip(": ").strip()
            if newn:
                try:
                    save_name(newn)
                    self._name = newn[:24]
                    self._payload = _adv_payload(self._name)
                    self._notify(b"NAME-SET\n")   # applies on next reconnect
                except Exception:
                    self._notify(b"NAME-ERR\n")
            return
        if u == "%%NAME?":
            self._notify(("NAME " + self._name + "\n").encode())
            return
        if u == "%%IT":
            active = "IT"; return
        if u == "%%US":
            active = "US"; return
        if u == "%%SWITCH":
            active = "US" if active == "IT" else "IT"
            _press(KeyCode.LEFT_CTRL, KeyCode.SPACE); return
        if u == "%%CYCLE":
            _press(KeyCode.LEFT_CTRL, KeyCode.LEFT_ALT, KeyCode.SPACE); return
        if u == "%%ENTER":
            type_enter = True; return
        if u == "%%NOENTER":
            type_enter = False; return

        # --- plain text -> type it ---
        type_text(sanitize(line + ("\n" if type_enter else "")))

    def poll(self):
        if not self._buf:
            return
        # Decode complete lines only; keep trailing partial bytes for next round
        # (prevents splitting a multi-byte Italian character across BLE writes).
        if self._buf.find(b"\n") >= 0:
            idx = self._buf.rfind(b"\n")
            head = bytes(self._buf[:idx])
            self._buf = bytearray(self._buf[idx + 1:])
            for raw in head.split(b"\n"):
                self._handle_line(raw.decode("utf-8", "ignore"))
        else:
            # No newline yet: wait briefly for the rest, then flush.
            time.sleep_ms(40)
            if self._buf.find(b"\n") < 0:
                raw = bytes(self._buf)
                self._buf = bytearray()
                self._handle_line(raw.decode("utf-8", "ignore"))


dongle = NUSDongle()
_blink = time.ticks_ms()
while True:
    if dongle._conn is None:
        if time.ticks_diff(time.ticks_ms(), _blink) > 400:
            led.toggle(); _blink = time.ticks_ms()
    dongle.poll()
    time.sleep_ms(10)
