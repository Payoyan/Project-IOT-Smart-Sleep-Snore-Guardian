"""Tanpa HP, broker, atau akun. Pelajari algoritmanya dulu.
Catatan: mode offline hanya menunjukkan processing & algoritma, BUKAN komunikasi cloud MQTT.
Jalankan dari root repo: python scripts/offline_demo.py
"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nodes.detector_service.rules import SleepAnalyzer
from shared.messages import Telemetry
from shared.processing import bed_features, room_features

BASE = 1_790_000_000_000
rnd = random.Random(7)


def window(motion, snore, lux, ext=0.0, gain=1.0):
    accel = [(0.0, 0.0, 9.81 + rnd.gauss(0, motion)) for _ in range(30)]
    levels = [abs(rnd.gauss(0.006, 0.002)) for _ in range(60)]
    if snore:
        for i in range(60):
            if i % 40 < 12:
                levels[i] = snore * gain
    if ext:
        for i in range(20, 25):
            levels[i] = ext
    return accel, levels, [lux] * 3


def main():
    analyzer = SleepAnalyzer(alert_cooldown_s=0)
    plan = [("Tidur nyenyak", dict(motion=0.02, snore=0, lux=1)),
            ("Mendengkur", dict(motion=0.03, snore=0.12, lux=1)),
            ("Gelisah", dict(motion=0.7, snore=0, lux=2)),
            ("Gelisah + dengkur + lampu menyala", dict(motion=0.8, snore=0.15, lux=80)),
            ("TV menyala (bising luar)", dict(motion=0.02, snore=0, lux=2, ext=0.08))]
    seq = 0
    for title, p in plan:
        print(f"\n== {title}")
        for _ in range(5):
            now = BASE + seq * 6000
            accel, levels, lux = window(p["motion"], p["snore"], p["lux"], p.get("ext", 0))
            _, room_levels, _ = window(0.02, p["snore"], p["lux"], p.get("ext", 0), gain=0.25)
            e2 = Telemetry("edge2", "demo", seq, now, room_features(lux, room_levels).__dict__)
            e1 = Telemetry("edge1", "demo", seq, now, bed_features(accel, levels).__dict__)
            analyzer.accept(e2, now_ms=now)
            d = analyzer.accept(e1, now_ms=now)
            seq += 1
        print(f"   -> {d.status} (skor {d.score}) | {d.reason} | alert={d.alert_target}")
    print("\nSelesai. Lanjut: jalankan node dengan broker (lihat README).")


if __name__ == "__main__":
    main()
