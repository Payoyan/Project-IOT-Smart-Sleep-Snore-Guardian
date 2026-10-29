"""DATA PROCESSING (dipakai kedua edge, tanpa dependensi eksternal).

Processing A  : Motion RMS dari accelerometer  -> seberapa gelisah kasur bergerak.
Processing B  : Noise Peak Detection dari mikrofon -> lonjakan suara dengkuran.
Processing C  : ringkasan cahaya + kebisingan ruangan (Edge 2).
"""

from dataclasses import dataclass
from math import sqrt
from statistics import median
from typing import Sequence

FRAME_SECONDS = 0.1  # satu "level suara" = RMS dari 100 ms audio


@dataclass(frozen=True)
class BedFeatures:
    motion_rms: float
    snore_peaks: int
    snore_level: float


@dataclass(frozen=True)
class RoomFeatures:
    light_lux: float
    ambient_level: float
    ambient_peak: float


def motion_rms(accelerations: Sequence[tuple[float, float, float]]) -> float:
    """RMS fluktuasi magnitudo akselerasi di sekitar rata-ratanya (detrended).

    Dikurangi rata-rata (bukan 9,81) supaya bias sensor/kemiringan HP tidak
    terbaca sebagai gerakan. Diam ~ 0; berguling di kasur >> 0.
    """
    if len(accelerations) < 2:
        raise ValueError("Minimal 2 sampel accelerometer")
    magnitudes = [sqrt(x * x + y * y + z * z) for x, y, z in accelerations]
    mean = sum(magnitudes) / len(magnitudes)
    return round(sqrt(sum((m - mean) ** 2 for m in magnitudes) / len(magnitudes)), 4)


def pcm_to_levels(pcm: Sequence[int], frame_size: int) -> list[float]:
    """PCM 16-bit mono -> daftar level RMS ternormalisasi (0..1) per frame."""
    if frame_size <= 0:
        raise ValueError("frame_size harus positif")
    return [
        sqrt(sum(s * s for s in pcm[i:i + frame_size]) / frame_size) / 32768.0
        for i in range(0, len(pcm) - frame_size + 1, frame_size)
    ]


def detect_snore_peaks(levels: Sequence[float], rel_factor: float = 3.0, abs_min: float = 0.02,
                       min_frames: int = 2, max_frames: int = 30) -> tuple[int, float]:
    """Hitung 'puncak' suara: rentetan frame di atas ambang adaptif.

    ambang = max(median * rel_factor, abs_min) -> mengikuti kebisingan dasar ruangan.
    Rentetan valid = 0,2 s .. 3 s (klik singkat dan suara sangat panjang diabaikan).
    Return (jumlah puncak, amplitudo puncak tertinggi).
    """
    if not levels:
        return 0, 0.0
    threshold = max(median(levels) * rel_factor, abs_min)
    peaks, best, run, run_max = 0, 0.0, 0, 0.0
    for value in list(levels) + [0.0]:  # sentinel menutup rentetan terakhir
        if value >= threshold:
            run += 1
            run_max = max(run_max, value)
        else:
            if min_frames <= run <= max_frames:
                peaks += 1
                best = max(best, run_max)
            run, run_max = 0, 0.0
    return peaks, round(best, 4)


def bed_features(accelerations, levels, abs_min: float = 0.02) -> BedFeatures:
    peaks, level = detect_snore_peaks(levels, abs_min=abs_min)
    return BedFeatures(motion_rms(accelerations), peaks, level)


def room_features(lux_values: Sequence[float], levels: Sequence[float]) -> RoomFeatures:
    if not lux_values:
        raise ValueError("Belum ada pembacaan sensor cahaya")
    if not levels:
        raise ValueError("Belum ada level suara")
    return RoomFeatures(
        light_lux=round(float(median(lux_values)), 2),
        ambient_level=round(sum(levels) / len(levels), 4),
        ambient_peak=round(max(levels), 4),
    )
