"""Bike -> Bike Buddy telemetry bridge. Run it on a device physically connected to the bike (laptop, Raspberry Pi, Android with Termux).
  python bridge.py --source serial --port /dev/ttyUSB0      ESP32/Arduino that prints one JSON object per line, e.g. {"battery":12.6,"tyre_front":31.2}
  python bridge.py --source obd --port /dev/rfcomm0          ELM327 adapter (pip install obd). Most motorcycles are NOT OBD-II: check yours first.
Sends only what the bike really reports; fields it cannot read are simply not sent (the app then shows 'n/a', never a made-up number).
Reconnects automatically and never replays old data: stale readings are worse than none."""
import argparse, json, os, time
import requests

def serial_reader(port, baud):
    import serial
    ser = serial.Serial(port, baud, timeout=2)
    def read():
        line = ser.readline().decode(errors="ignore").strip()
        return json.loads(line) if line.startswith("{") else {}
    return read

def obd_reader(port):
    import obd
    c = obd.OBD(port) if port else obd.OBD()
    if not c.is_connected(): raise RuntimeError("OBD adapter not connected")
    pids = {"battery": obd.commands.CONTROL_MODULE_VOLTAGE, "engine_temp": obd.commands.COOLANT_TEMP, "fuel": obd.commands.FUEL_LEVEL, "rpm": obd.commands.RPM}
    def read():
        out = {}
        for k, cmd in pids.items():
            r = c.query(cmd)
            if not r.is_null(): out[k] = float(r.value.magnitude)
        if "rpm" in out: out["ignition"] = out["rpm"] > 0
        return out
    return read

def main():
    a = argparse.ArgumentParser(); a.add_argument("--source", choices=["serial", "obd"], required=True); a.add_argument("--port"); a.add_argument("--baud", type=int, default=115200)
    a.add_argument("--url", default="http://localhost:5000"); a.add_argument("--every", type=float, default=2.0); a = a.parse_args()
    headers = {"X-Token": os.environ["TELEMETRY_TOKEN"]} if os.environ.get("TELEMETRY_TOKEN") else {}; wait = 1
    while True:
        try:
            read = serial_reader(a.port, a.baud) if a.source == "serial" else obd_reader(a.port); print("bike connected"); wait = 1
            while True:
                d = read()
                if d: print(requests.post(a.url + "/api/telemetry", json=d, headers=headers, timeout=5).json())
                time.sleep(a.every)
        except Exception as ex:
            print(f"link lost ({ex}); retrying in {wait}s"); time.sleep(wait); wait = min(wait * 2, 15)

if __name__ == "__main__": main()
