import csv
import struct
import time
from datetime import datetime
from smbus2 import SMBus

# BQ76952 Default 7-bit I2C Address (0x10 in 8-bit TI notation)
I2C_BUS = 1
BQ76952_ADDR = 0x08
CSV_FILENAME = "bq76952_telemetry.csv"
SAMPLE_INTERVAL_SEC = 1.0

# Direct Command Register Map
REG_CELL1_VOLTAGE = 0x14   # 0x14 to 0x32 (16 cells, 2 bytes each, mV)
REG_STACK_VOLTAGE = 0x34   # 10 mV units
REG_PACK_VOLTAGE  = 0x36   # 10 mV units
REG_CC2_CURRENT   = 0x3A   # mA (signed int16 with 1 mOhm sense resistor)
REG_INT_TEMP      = 0x68   # 0.1 K units
REG_TS1_TEMP      = 0x70   # 0.1 K units
REG_ALARM_STATUS  = 0x62   # 16-bit bitmask
REG_FET_STATUS    = 0x7F   # 8-bit status (Bit 0: CHG_FET, Bit 2: DSG_FET)

def read_u16(bus, reg):
    """Read 16-bit unsigned little-endian integer from a direct command register."""
    data = bus.read_i2c_block_data(BQ76952_ADDR, reg, 2)
    return struct.unpack("<H", bytes(data))[0]

def read_s16(bus, reg):
    """Read 16-bit signed little-endian integer from a direct command register."""
    data = bus.read_i2c_block_data(BQ76952_ADDR, reg, 2)
    return struct.unpack("<h", bytes(data))[0]

def acquire_sample(bus):
    """Poll voltages, current, temperatures, and status from BQ76952."""
    # Read Cell 1..16 voltages in mV
    cell_mv = []
    for cell_idx in range(16):
        reg = REG_CELL1_VOLTAGE + (cell_idx * 2)
        cell_mv.append(read_s16(bus, reg))
        time.sleep(0.001)  # Small inter-command delay

    stack_v = read_u16(bus, REG_STACK_VOLTAGE) * 0.01  # Convert 10mV to V
    pack_v  = read_u16(bus, REG_PACK_VOLTAGE) * 0.01   # Convert 10mV to V
    curr_ma = read_s16(bus, REG_CC2_CURRENT)           # mA

    int_temp_c = (read_s16(bus, REG_INT_TEMP) * 0.1) - 273.15
    ts1_temp_c = (read_s16(bus, REG_TS1_TEMP) * 0.1) - 273.15

    alarm_hex = f"0x{read_u16(bus, REG_ALARM_STATUS):04X}"
    fet_stat  = bus.read_byte_data(BQ76952_ADDR, REG_FET_STATUS)
    chg_fet   = int(bool(fet_stat & 0x01))
    dsg_fet   = int(bool(fet_stat & 0x04))

    return {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "stack_v": round(stack_v, 2),
        "pack_v": round(pack_v, 2),
        "current_ma": curr_ma,
        "int_temp_c": round(int_temp_c, 2),
        "ts1_temp_c": round(ts1_temp_c, 2),
        "chg_fet": chg_fet,
        "dsg_fet": dsg_fet,
        "alarm_status": alarm_hex,
        **{f"cell_{i+1}_mv": cell_mv[i] for i in range(16)},
    }

def main():
    fieldnames = (
        ["timestamp", "stack_v", "pack_v", "current_ma", "int_temp_c", "ts1_temp_c", "chg_fet", "dsg_fet", "alarm_status"]
        + [f"cell_{i+1}_mv" for i in range(16)]
    )

    with SMBus(I2C_BUS) as bus, open(CSV_FILENAME, mode="a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if csvfile.tell() == 0:
            writer.writeheader()

        print(f"Logging BQ76952 data to {CSV_FILENAME} (Press Ctrl+C to stop)...")
        try:
            while True:
                row = acquire_sample(bus)
                writer.writerow(row)
                csvfile.flush()
                print(
                    f"[{row['timestamp']}] Stack: {row['stack_v']:.2f}V | "
                    f"Curr: {row['current_ma']}mA | TS1: {row['ts1_temp_c']:.1f}C | "
                    f"C1: {row['cell_1_mv']}mV"
                )
                time.sleep(SAMPLE_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\nData logging stopped safely.")

if __name__ == "__main__":
    main()