"""Sumber data sensor fisik.

'--source simulator' jalan di laptop mana pun (hanya untuk latihan/tes).
'--source android'   memakai Termux:API di HP sungguhan.

Kedua sumber punya antarmuka SAMA, sehingga processing tidak peduli asalnya:
  accelerometer.read() -> (x, y, z) m/s²
  light.read()         -> lux (atau None jika belum ada pembacaan baru)
  microphone.start(s) ; microphone.collect() -> list level suara (0..1, per 100 ms)
Audio TIDAK disimpan: file sementara dihapus segera setelah dihitung levelnya.
"""

import json
import math
import random
import shutil
import subprocess
import sys
import time
from array import array
from pathlib import Path

from shared.processing import FRAME_SECONDS, pcm_to_levels

# ---------------------------------------------------------------- simulator
# motion = std fluktuasi accelerometer, snore = amplitudo dengkuran di bantal,
# lux = cahaya kamar, ext = kebisingan luar (TV/lalu lintas) di kedua HP.
STATES = {
    "deep":       dict(motion=0.02, snore=0.00, lux=1.5, ext=0.00),
    "snoring":    dict(motion=0.03, snore=0.12, lux=1.5, ext=0.00),
    "restless":   dict(motion=0.70, snore=0.00, lux=3.0, ext=0.00),
    "poor":       dict(motion=0.80, snore=0.15, lux=80.0, ext=0.00),
    "noisy_room": dict(motion=0.02, snore=0.00, lux=2.0, ext=0.08),
}
TIMELINE = [("deep", 40), ("snoring", 60), ("restless", 50), ("poor", 60)]
SCENARIOS = list(STATES) + ["night"]


class Scenario:
    """'night' = skenario berjalan otomatis (210 dtk, berulang); lainnya tetap."""

    def __init__(self, name: str):
        if name not in SCENARIOS:
            raise ValueError(f"Skenario tidak dikenal: {name}")
        self.name = name
        self.started = time.monotonic()

    def state_name(self) -> str:
        if self.name != "night":
            return self.name
        t = (time.monotonic() - self.started) % sum(d for _, d in TIMELINE)
        for state, duration in TIMELINE:
            if t < duration:
                return state
            t -= duration
        return TIMELINE[-1][0]

    def current(self) -> dict:
        return STATES[self.state_name()]


class SimAccelerometer:
    def __init__(self, scenario: Scenario, seed: int = 1):
        self.scenario, self.rnd = scenario, random.Random(seed)

    def read(self):
        motion = self.scenario.current()["motion"]
        return (self.rnd.gauss(0, 0.02), self.rnd.gauss(0, 0.02), 9.81 + self.rnd.gauss(0, motion))


class SimLight:
    def __init__(self, scenario: Scenario, seed: int = 2):
        self.scenario, self.rnd = scenario, random.Random(seed)

    def read(self):
        lux = self.scenario.current()["lux"]
        return max(0.0, lux + self.rnd.gauss(0, lux * 0.05))


class SimMicrophone:
    def __init__(self, scenario: Scenario, role: str, seed: int = 3):
        self.scenario, self.role, self.rnd = scenario, role, random.Random(seed)
        self.seconds = 5.0

    def start(self, seconds: float):
        self.seconds = seconds

    def collect(self) -> list[float]:
        p, n = self.scenario.current(), int(self.seconds / FRAME_SECONDS)
        levels = [abs(self.rnd.gauss(0.006, 0.002)) for _ in range(n)]
        gain = 1.0 if self.role == "bed" else 0.25  # dengkuran lebih pelan dari meja
        if p["snore"] > 0:
            offset = self.rnd.randrange(40)  # napas tiap ~4 dtk, dengkuran ~1,2 dtk
            for i in range(n):
                if (i + offset) % 40 < 12:
                    levels[i] = p["snore"] * gain * (0.8 + 0.2 * self.rnd.random())
        if p["ext"] > 0:
            for _ in range(2):
                start = self.rnd.randrange(max(1, n - 6))
                for i in range(start, min(n, start + self.rnd.randint(3, 6))):
                    levels[i] = p["ext"] * (0.9 + 0.2 * self.rnd.random())
        return levels


# ------------------------------------------------------------------ android
def _termux_sensor_names() -> list[str]:
    if not shutil.which("termux-sensor"):
        raise RuntimeError("termux-sensor tidak ada. Pasang Termux:API lalu: pkg install termux-api")
    out = subprocess.run(["termux-sensor", "-l"], capture_output=True, text=True,
                         timeout=10, check=True).stdout
    names = json.loads(out)
    if isinstance(names, dict):
        names = names.get("sensors", [])
    if not isinstance(names, list):
        raise RuntimeError("Daftar sensor tidak terduga. Jalankan termux-sensor -l")
    return names


def _read_sensor(name: str, timeout: float = 12) -> list[float]:
    try:
        out = subprocess.run(["termux-sensor", "-s", name, "-d", "100", "-n", "1"],
                             capture_output=True, text=True, timeout=timeout, check=True).stdout
        return [float(v) for v in json.loads(out)[name]["values"]]
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(name) from exc
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Gagal membaca sensor {name}. Cek izin Termux:API.") from exc


class AndroidAccelerometer:
    def __init__(self):
        names = _termux_sensor_names()
        self.name = next((n for n in names if "accelerometer" in n.lower()
                          and "uncalibrated" not in n.lower()), None)
        if not self.name:
            raise RuntimeError(f"Accelerometer tidak ditemukan. Daftar: {names}")
        print(f"[SENSOR] Accelerometer: {self.name}")

    def read(self):
        values = _read_sensor(self.name)[:3]
        if len(values) != 3:
            raise RuntimeError("Accelerometer harus 3 sumbu")
        return tuple(values)


class AndroidLight:
    def __init__(self):
        names = [n for n in _termux_sensor_names() if "light" in n.lower()]
        preferred = [n for n in names if "non-wakeup" in n.lower() or "wakeup" not in n.lower()]
        self.name = (preferred or names or [None])[0]
        if not self.name:
            raise RuntimeError("Sensor cahaya tidak ditemukan (termux-sensor -l)")
        print(f"[SENSOR] Light: {self.name}")

    def read(self):
        try:  # sensor on-change kadang tidak mengirim jika nilai tetap -> None
            return _read_sensor(self.name, timeout=4)[0]
        except TimeoutError:
            return None


class AndroidMicrophone:
    """Rekam jendela pendek via Termux:API, hitung level per 100 ms lewat ffmpeg,
    lalu HAPUS file-nya. Hanya angka level yang dipakai."""

    RATE = 8000

    def __init__(self):
        for tool in ("termux-microphone-record", "ffmpeg"):
            if not shutil.which(tool):
                raise RuntimeError(f"{tool} belum terpasang. Jalankan: pkg install termux-api ffmpeg")
        self.path = Path.home() / ".sleepguard_window.m4a"
        self.deadline = 0.0

    def _run(self, *args):
        subprocess.run(["termux-microphone-record", *args], capture_output=True, timeout=10, check=False)

    def start(self, seconds: float):
        self._run("-q")
        self.path.unlink(missing_ok=True)
        self._run("-f", str(self.path), "-l", str(math.ceil(seconds)), "-e", "aac", "-r", "16000", "-c", "1")
        self.deadline = time.monotonic() + seconds

    def collect(self) -> list[float]:
        time.sleep(max(0.0, self.deadline - time.monotonic()) + 0.7)
        try:
            for _ in range(10):
                if self.path.exists() and self.path.stat().st_size > 0:
                    break
                time.sleep(0.3)
            else:
                raise RuntimeError("Rekaman kosong. Izinkan mikrofon untuk Termux:API di pengaturan Android.")
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(self.path), "-f", "s16le",
                 "-ac", "1", "-ar", str(self.RATE), "pipe:1"],
                capture_output=True, timeout=20, check=True).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("ffmpeg gagal membaca rekaman") from exc
        finally:
            self.path.unlink(missing_ok=True)  # privasi: audio tidak disimpan
        pcm = array("h")
        pcm.frombytes(raw[: len(raw) // 2 * 2])
        if sys.byteorder == "big":
            pcm.byteswap()
        return pcm_to_levels(pcm, int(self.RATE * FRAME_SECONDS))


def make_bed_sensors(source: str, scenario: Scenario):
    if source == "android":
        return AndroidAccelerometer(), AndroidMicrophone()
    if source == "simulator":
        return SimAccelerometer(scenario), SimMicrophone(scenario, "bed")
    raise ValueError(f"Sumber sensor tidak dikenal: {source}")


def make_room_sensors(source: str, scenario: Scenario):
    if source == "android":
        return AndroidLight(), AndroidMicrophone()
    if source == "simulator":
        return SimLight(scenario), SimMicrophone(scenario, "table")
    raise ValueError(f"Sumber sensor tidak dikenal: {source}")
