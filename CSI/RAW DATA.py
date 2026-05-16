"""
Raw serial dump — just prints everything from the port, no filtering.
Run this to see exactly what the ESP32 is sending.
"""
import serial
 
PORT = "COM3"
BAUD = 921600
 
print(f"Opening {PORT} at {BAUD}...")
ser = serial.Serial(PORT, BAUD, timeout=2)
print("Connected. Printing everything raw. Ctrl+C to stop.\n")
 
try:
    while True:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        if line:
            print(repr(line))
except KeyboardInterrupt:
    print("\nDone.")
    ser.close()
 