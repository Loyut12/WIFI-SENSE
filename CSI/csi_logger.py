"""
ESP32-S3 CSI Logger — no thresholds, just records everything
INSTALL:  pip install pyserial
RUN:      python csi_logger.py
"""

import serial
import csv
import re
from datetime import datetime

PORT   = "COM3"
BAUD   = 921600
OUTPUT = r"C:\Users\ahmed\Desktop\CSCI\csi_data.csv"

print(f"Opening {PORT} at {BAUD} baud...")
print(f"Saving to: {OUTPUT}")
print("Press Ctrl+C to stop.\n")

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
except Exception as e:
    print(f"ERROR: {e}"); exit()

with open(OUTPUT, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "packet", "rssi", "mean_amplitude",
                     "variance", "smoothed", "subcarriers", "csi_amplitudes"])

    count = 0
    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line.startswith("CSI_DATA"):
                continue

            # Format A — two-device receiver
            # CSI_DATA,pkt,rssi,mean,variance,smoothed,motion,[amps]
            m = re.match(
                r"CSI_DATA,(\d+),(-?\d+),([\d.]+),([\d.]+),([\d.]+),\d,\[([^\]]+)\]",
                line
            )
            if m:
                pkt      = int(m.group(1))
                rssi     = int(m.group(2))
                mean_amp = float(m.group(3))
                variance = float(m.group(4))
                smoothed = float(m.group(5))
                amps     = m.group(6).strip()
                n_sub    = len(amps.split())
                ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                writer.writerow([ts, pkt, rssi, mean_amp, variance, smoothed, n_sub, amps])
                f.flush()
                count += 1
                print(f"  #{pkt:>6} | RSSI:{rssi:>4}dBm | "
                      f"Var:{variance:>8.2f} | Smooth:{smoothed:>8.2f}")
                continue

            # Format B — single device / router format
            # CSI_DATA,seq,mac,rssi,...,[IQ comma-separated]
            m2 = re.match(
                r"CSI_DATA,(\d+),([\da-fA-F:]+),(-?\d+),[\d,\s-]+,\[([^\]]+)\]",
                line
            )
            if m2:
                seq    = int(m2.group(1))
                rssi   = int(m2.group(3))
                iq_raw = m2.group(4)
                vals   = list(map(int, re.findall(r'-?\d+', iq_raw)))
                amps   = [round((vals[i]**2 + vals[i+1]**2)**0.5, 1)
                          for i in range(0, len(vals)-1, 2)]
                if not amps: continue
                mean_amp = round(sum(amps)/len(amps), 2)
                variance = round(sum((a-mean_amp)**2 for a in amps)/len(amps), 2)
                amps_str = " ".join(map(str, amps))
                ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                writer.writerow([ts, seq, rssi, mean_amp, variance, "", len(amps), amps_str])
                f.flush()
                count += 1
                print(f"  #{seq:>6} | RSSI:{rssi:>4}dBm | Var:{variance:>8.2f}")

    except KeyboardInterrupt:
        print(f"\nStopped. Saved {count} packets to '{OUTPUT}'")
        ser.close()
