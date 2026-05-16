# Wi-Fi Sense

A device-free motion detection prototype using Wi-Fi Channel State Information (CSI) collected between two ESP32-S3 microcontrollers communicating over ESP-NOW. No router required. No training data required. No cameras.

---

## How It Works

```
[TX ESP32-S3] ──── ESP-NOW 100 Hz ────► [RX ESP32-S3] ──── Serial 921600 ────► [Laptop]
  transmitter                              receiver                               Python pipeline
  fixed MAC                                CSI callback                           CSV → MOTION/IDLE
```

The TX board broadcasts at 100 Hz on a fixed channel (channel 11, 40 MHz HT40). The RX board captures CSI from every received frame and logs it over serial at 921,600 baud. A Python pipeline then processes the data through six stages to produce a binary MOTION / IDLE output per frame.

---

## Pipeline

| Stage | What it does | Where it runs |
|---|---|---|
| S1 — CSI Acquisition | TX broadcasts, RX captures CSI frames | On-device |
| S2 — Amplitude Extraction | IQ pairs → amplitude per subcarrier | On-device |
| S3 — Hampel Filter + Baseline Norm | Outlier suppression, first-15-packet baseline | Offline Python |
| S4 — NBVI Subcarrier Selection | 12 highest-variance non-adjacent subcarriers | Offline Python |
| S5 — Threshold Derivation | T = max(still-room smoothed variance) | Offline Python |
| S6 — MVS Classification | Rolling variance vs threshold → MOTION / IDLE | Offline Python |

---

## Hardware

- 2× ESP32-S3-DevKitC-1
- 2× External stub antennas
- USB-C cable (RX board to laptop for serial logging)
- Portable power bank (TX board, optional for cable-free placement)

---

## Results

Tested across five occupancy conditions in a 4.60 × 3.40 m room with TX and RX placed 5.84 m apart. Threshold T = 60 derived from still-room pipeline maximum.

| Condition | Accuracy | Packets |
|---|---|---|
| Still room (IDLE) | 100% | 4,741 |
| 1 person | 63.7% | 10,483 |
| 2 persons | 70.3% | 9,752 |
| 3 persons | 75.5% | 8,992 |
| 4 persons | 100% | 8,048 |
| **Overall** | **78.8%** | **42,016** |

RSSI remained consistent across all conditions (-59 to -64 dBm), confirming RSSI alone is not a reliable motion indicator.

---

## Repository Structure

```
wi-fi-sense/
├── firmware/
│   ├── transmitter/
│   │   └── transmitter.ino       # Flash to ESP32-S3 #1 (TX)
│   └── receiver/
│       └── receiver.ino          # Flash to ESP32-S3 #2 (RX)
├── python/
│   ├── csi_logger.py             # Serial capture → CSV
│   └── csi_pipeline.py           # Full processing pipeline + plots
└── README.md
```

---

## Quickstart

### 1. Install dependencies
```bash
pip install pyserial numpy matplotlib scipy
```

### 2. Flash firmware

Open `transmitter.ino` in Arduino IDE:
- Board: ESP32S3 Dev Module
- Upload to ESP32-S3 #1

Open `receiver.ino` in Arduino IDE:
- Board: ESP32S3 Dev Module
- Baud: 921600 in Serial Monitor
- Upload to ESP32-S3 #2

### 3. Collect still-room baseline
Close Arduino Serial Monitor. Run:
```bash
python csi_logger.py
```
Keep the room completely empty for 30+ seconds. Press Ctrl+C to stop.

### 4. Find your threshold
```bash
python csi_pipeline.py --file csi_data.csv
```
Look at the stats printed — note the 99th percentile and max values. Set your threshold just above the max.

### 5. Collect motion data and run pipeline
```bash
python csi_logger.py                    # walk around, then Ctrl+C

python csi_pipeline.py --file csi_data.csv --threshold 60 --save
```

### 6. Compare still vs motion (best plot for analysis)
```bash
python csi_pipeline.py --file csi_data_moving.csv --baseline csi_data_still.csv --threshold 60 --save
```

Output files: `csi_pipeline_output.png` and `csi_pipeline_output.pdf`

---

## Pipeline Commands Reference

```bash
# See stats only — no threshold applied
python csi_pipeline.py --file csi_data.csv

# Apply threshold and show plots
python csi_pipeline.py --file csi_data.csv --threshold 60

# Save plots as PNG + PDF
python csi_pipeline.py --file csi_data.csv --threshold 60 --save

# Overlay still vs motion CDF (paper figure)
python csi_pipeline.py --file csi_data_moving.csv --baseline csi_data_still.csv --threshold 60 --save
```

---

## How to Pick the Threshold

1. Record the empty room for 30+ seconds → run pipeline with no threshold
2. Note the **max** smoothed variance value printed in the stats
3. Set threshold = that value (or slightly above it)
4. Every packet above the threshold = MOTION, below = IDLE

---

## Configuration

In `transmitter.ino`:
```cpp
#define WIFI_SSID     "your_ssid"
#define WIFI_PASS     "your_password"
#define SEND_FREQ_HZ  100       // TX rate in Hz
#define CHANNEL       11        // must match receiver
```

In `receiver.ino`:
```cpp
#define CHANNEL          11     // must match transmitter
#define MOTION_THRESHOLD 90.0f  // on-device threshold (for serial output only)
#define SMOOTH_WINDOW    10     // rolling average window
```

In `csi_logger.py`:
```python
PORT   = "COM4"         # your serial port
BAUD   = 921600
OUTPUT = "csi_data.csv" # output path
```

---

## Placement

```
[TX] ──────────── 4–8 m ──────────── [RX]
                ↑ walk here ↑
```

- Place TX and RX at opposite ends of the room at the same height
- Walk perpendicular to the line between them for strongest signal disruption
- Works best in 2.4 GHz band, single room, clear line of sight

---

## Known Limitations

- Binary MOTION/IDLE output only — no occupant count or location
- Reduced sensitivity when occupant is stationary or moves parallel to TX-RX axis
- Still-room baseline requires unoccupied space at start of session
- Packet loss at range reduces temporal resolution (~55–72 fps at 5.84 m)
- Pipeline runs offline — no real-time on-device alerts yet
- Fresh baseline required when moving to a new room

---

## Acknowledgements

CSI acquisition builds on the [Espressif ESP-CSI](https://github.com/espressif/esp-csi) open-source toolkit. The authors thank the open-source ESP32 community whose shared firmware examples informed the implementation.
