#!/usr/bin/env bash
# WisprDongle firmware installer. Run AFTER flashing MicroPython to the board.
# Requires: pip install mpremote
set -e

PORT="${1:-$(ls /dev/tty.usbmodem* 2>/dev/null | head -1)}"
if [ -z "$PORT" ]; then
  echo "No board found. Plug in the Pico (already running MicroPython) and retry,"
  echo "or pass the port:  ./install.sh /dev/tty.usbmodemXXXX   (Windows: COM3)"
  exit 1
fi
echo "Using board at: $PORT"

python3 -m mpremote connect "$PORT" exec "import os
try: os.mkdir('usb')
except: pass
try: os.mkdir('usb/device')
except: pass
print('dirs ready')"

for f in usb/device/__init__.py usb/device/core.py usb/device/hid.py usb/device/keyboard.py layouts.py main.py; do
  echo "  copying $f"
  python3 -m mpremote connect "$PORT" fs cp "$f" ":$f"
done

echo "Resetting board..."
python3 -m mpremote connect "$PORT" exec "import machine; machine.reset()" 2>/dev/null || true
echo
echo "Done. The LED should blink slowly (advertising)."
echo "Default password is 'changeme' — change it in the phone app:"
echo "  https://seni4it.github.io/wispr-dongle/"
