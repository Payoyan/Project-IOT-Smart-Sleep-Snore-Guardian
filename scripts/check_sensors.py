"""Kalibrasi: baca SATU jendela sensor dan cetak fitur hasil olahan.
  python scripts/check_sensors.py bed      # di HP kasur (diam, lalu berguling/dengkur)
  python scripts/check_sensors.py room     # di HP meja
Pakai angkanya untuk menyetel MOTION_THRESHOLD, SNORE_LEVEL_MIN, BRIGHT_LUX di .env.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.edge_runner import collect_bed, collect_room
from shared.sensors import Scenario, make_bed_sensors, make_room_sensors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=["bed", "room"])
    p.add_argument("--source", choices=["android", "simulator"], default="android")
    p.add_argument("--scenario", default="snoring")
    p.add_argument("--window", type=float, default=6.0)
    p.add_argument("--interval", type=float, default=0.2)
    p.add_argument("--debug-sensors", action="store_true")
    args = p.parse_args()
    scenario = Scenario(args.scenario)
    if args.role == "bed":
        print(collect_bed(make_bed_sensors(args.source, scenario), args))
    else:
        print(collect_room(make_room_sensors(args.source, scenario), args))


if __name__ == "__main__":
    main()
