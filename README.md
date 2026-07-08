# 🔌 WisprDongle

**Voice-type on any computer, from your phone, with nothing installed on the computer.**

WisprDongle is a tiny USB stick (a $7 Raspberry Pi Pico 2 W) that plugs into any
computer and shows up as an ordinary USB keyboard. You dictate on your phone — with
[Wispr Flow](https://wisprflow.ai) or any keyboard — and the words are typed on the
computer over Bluetooth. Works on locked-down work machines, a friend's PC, a lab
computer: no drivers, no admin, no software on the target at all.

- ⌨️ **Types on any computer** — it *is* a USB keyboard
- 🗣️ **Dictate from your phone** — Wispr Flow or any Android keyboard
- 🇮🇹🇺🇸 **English and Italian** with correct accents (à è é ì ò ù)
- 🔒 **Password-protected** — the dongle types nothing until your phone sends the password
- 📱 **One-tap phone app** — a web page you add to your home screen, no app store
- 💸 **Free and open source** — build your own for the cost of the board

## 📱 The phone app

**→ [seni4it.github.io/wispr-dongle](https://seni4it.github.io/wispr-dongle/) ←**

Open that on your Android phone in **Chrome**, then **⋮ → Add to Home Screen**. It
launches like an app: password field, a big box you dictate into that clears when you
send, and 🇮🇹/🇺🇸 language buttons. (Web Bluetooth needs Chrome on Android; iPhone
isn't supported by Apple's browser yet.)

## 🛒 What you need

| Item | Notes |
|------|-------|
| **Raspberry Pi Pico 2 W** (or **Pico W**) | ~$7. Must be the **"W"** version — the W is the Bluetooth radio. Plain Pico / Pico 2 won't work. |
| **USB cable** | A **data** cable (not charge-only). USB-C for Pico 2 W. |
| **Android phone** | With Chrome. Wispr Flow optional but great. |

## 🔧 Build it (about 10 minutes)

### 1. Flash MicroPython
1. Hold the **BOOTSEL** button on the Pico while plugging it into your computer.
2. A drive appears (`RP2350` for Pico 2 W, `RPI-RP2` for Pico W).
3. Download the MicroPython firmware and drag it onto that drive:
   - Pico 2 W: [MicroPython for RPI_PICO2_W](https://micropython.org/download/RPI_PICO2_W/)
   - Pico W: [MicroPython for RPI_PICO_W](https://micropython.org/download/RPI_PICO_W/)
4. The drive disappears and the board reboots into MicroPython.

### 2. Copy the WisprDongle files
Install [mpremote](https://pypi.org/project/mpremote/) once (`pip install mpremote`), then:

```bash
cd firmware
./install.sh            # copies main.py, layouts.py and the USB driver, then reboots
```

No `install.sh`? Do it by hand:
```bash
PORT=$(ls /dev/tty.usbmodem* | head -1)     # macOS/Linux; on Windows use the COM port
mpremote connect $PORT exec "import os
try: os.mkdir('usb')
except: pass
try: os.mkdir('usb/device')
except: pass"
for f in usb/device/__init__.py usb/device/core.py usb/device/hid.py usb/device/keyboard.py layouts.py main.py; do
  mpremote connect $PORT fs cp "$f" ":$f"
done
mpremote connect $PORT exec "import machine; machine.reset()"
```

### 3. Set your password
The dongle ships with the password **`changeme`**. Change it on first use:
1. Plug the dongle into a computer. Its LED blinks slowly (advertising).
2. Open the [phone app](https://seni4it.github.io/wispr-dongle/), type `changeme`, tap **Connect & unlock**.
3. Tap **Change password**, pick your own. It's saved on the dongle.

## 📖 Daily use

1. Plug the dongle into the computer.
2. Open the app on your phone, tap **Connect & unlock** (password is remembered).
3. Click into wherever you want to type on the computer, dictate on the phone, tap **Send**. Done.
4. Unplug at the end of the day.

**Language & accents:** the dongle sends *key positions*, so the computer must be set to
the matching keyboard layout. For Italian accents, set the computer's input source to
**Italian** and leave the app on 🇮🇹. On a US-layout machine, tap 🇺🇸 and type English.

## 🔒 Security model (read this)

WisprDongle is a keyboard — anything that can talk to it can type on your computer. So:

- **The dongle is LOCKED until it receives your password.** A stranger who connects over
  Bluetooth can't type a single key without it. This is enforced by the dongle itself,
  not just the app.
- **No cryptographic pairing.** The stock MicroPython build for the Pico W / Pico 2 W
  can't do BLE bonding, so the password is the guard, not link encryption. A determined
  attacker in Bluetooth range could sniff the link; the password stops casual injection,
  which is the realistic threat.
- **Keep your phone locked** when unattended — the app remembers your password.
- **Unplug the dongle** when you're not using it. A keyboard that isn't plugged in can't type.

Use good judgement on shared/sensitive machines. This is a hobbyist tool, not a certified
security product.

## 🧩 How it works

```
  Phone (Wispr Flow / keyboard)
        │  types into the web app's text box
        ▼
  Web app (Chrome, Web Bluetooth)
        │  sends TEXT over BLE Nordic UART  (+ your password to unlock)
        ▼
  Pico 2 W  →  password check → sanitize → map each char to a USB key (US/IT)
        │
        ▼
  USB HID keyboard  →  types on the computer
```

Sending *text* (not keystrokes) over the air is what lets one dongle type multiple
languages: the firmware owns the character-to-key mapping per layout.

## 🙏 Credits & license

Built with [MicroPython](https://micropython.org), the
[micropython-lib USB HID driver](https://github.com/micropython/micropython-lib), and
keyboard-layout data derived from
[Adafruit CircuitPython](https://github.com/adafruit/Adafruit_CircuitPython_HID) and
[Neradoc's layouts](https://github.com/Neradoc/Circuitpython_Keyboard_Layouts).

MIT licensed — see [LICENSE](LICENSE). Build one, share it, improve it.
