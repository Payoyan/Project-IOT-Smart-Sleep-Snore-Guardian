"""Skema pesan MQTT: kontrak antara dua edge dan detector.

Edge 1 (kasur)  : motion_rms, snore_peaks, snore_level
Edge 2 (meja)   : light_lux, ambient_level, ambient_peak
Data mentah (audio/akselerasi) TIDAK pernah dikirim; hanya angka hasil olahan.
"""

from dataclasses import dataclass
import json
import math
import time

FIELDS = {
    "edge1": ("motion_rms", "snore_peaks", "snore_level"),
    "edge2": ("light_lux", "ambient_level", "ambient_peak"),
}


@dataclass(frozen=True)
class Telemetry:
    device_id: str
    boot_id: str
    sequence: int
    sent_at_ms: int
    values: dict

    def to_json(self) -> str:
        return json.dumps({
            "device_id": self.device_id, "boot_id": self.boot_id,
            "sequence": self.sequence, "sent_at_ms": self.sent_at_ms, **self.values,
        })

    @staticmethod
    def from_json(payload: str | bytes) -> "Telemetry":
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Telemetry harus berupa JSON object")
        for key in ("device_id", "boot_id"):
            if not isinstance(value.get(key), str) or not value[key]:
                raise ValueError(f"{key} tidak valid")
        device = value["device_id"]
        if device not in FIELDS:
            raise ValueError("Edge device tidak dikenal")
        sequence, timestamp = value.get("sequence"), value.get("sent_at_ms")
        if type(sequence) is not int or sequence < 0:
            raise ValueError("sequence tidak valid")
        if type(timestamp) is not int or timestamp < 0:
            raise ValueError("timestamp tidak valid")
        values = {}
        for key in FIELDS[device]:
            number = value.get(key)
            if type(number) not in (float, int) or not math.isfinite(number) or number < 0:
                raise ValueError(f"{key} tidak valid")
            values[key] = float(number)
        return Telemetry(device, value["boot_id"], sequence, timestamp, values)

    @staticmethod
    def make(device_id: str, boot_id: str, sequence: int, values: dict,
             now_ms: int | None = None) -> "Telemetry":
        return Telemetry(device_id, boot_id, sequence,
                         now_ms if now_ms is not None else int(time.time() * 1000), values)


def status_json(status: str, reason: str, monitoring: bool, score: float = 0.0,
                counts: dict | None = None, device_id: str | None = None,
                sequence: int | None = None, now_ms: int | None = None) -> str:
    """Keputusan detector terakhir (retained) untuk dashboard."""
    return json.dumps({
        "status": status, "reason": reason, "monitoring": monitoring,
        "sleep_score": score, "counts": counts or {},
        "device_id": device_id, "sequence": sequence,
        "at_ms": now_ms if now_ms is not None else int(time.time() * 1000),
    })
