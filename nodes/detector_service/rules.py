"""NODE 3: algoritma status tidur (Python murni, tanpa MQTT).

Rule-based SENSOR FUSION dari dua edge, dihaluskan dengan riwayat N jendela:
  Edge 1: motion_rms, snore_peaks, snore_level   (kasur)
  Edge 2: light_lux, ambient_peak                (meja)

Per jendela:
  restless  = motion_rms >= motion_threshold
  loud      = snore_peaks >= 1 dan snore_level >= snore_level_min
  env_noise = loud, tetapi Edge 2 mendengar level yang hampir sama
              (level_edge1 / ambient_peak_edge2 < ext_ratio) -> TV/lalu lintas
  snoring   = loud dan bukan env_noise (suara dominan di bantal)
  bright    = light_lux >= bright_lux

Status (prioritas dari atas), dihitung atas `history_windows` jendela terakhir:
  POOR_SLEEP_ALERT  skor <= poor_score (butuh >= 3 jendela)
  HEAVY_SNORING     jendela snoring >= snore_min_windows
  RESTLESS          jendela restless >= restless_min_windows
  ENV_NOISE         jendela env_noise >= 2
  DEEP_SLEEP        selain itu

sleep_score = 100 - 40*frac(restless) - 35*frac(snoring) - 25*frac(bright)

Ini INDIKASI dari sensor HP, bukan diagnosis medis / pengukuran fase tidur.
"""

from collections import deque
from dataclasses import dataclass, field
import time

from shared.messages import Telemetry

ALERT_TARGETS = {"HEAVY_SNORING": "edge1", "POOR_SLEEP_ALERT": "edge2"}


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    score: float = 0.0
    alert_target: str | None = None
    counts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WindowResult:
    restless: bool
    snoring: bool
    env_noise: bool
    bright: bool


class SleepAnalyzer:
    def __init__(self, motion_threshold: float = 0.2, snore_level_min: float = 0.03,
                 bright_lux: float = 30.0, ext_min: float = 0.03, ext_ratio: float = 1.5,
                 history_windows: int = 5, snore_min_windows: int = 3,
                 restless_min_windows: int = 2, poor_score: float = 50.0,
                 alert_cooldown_s: float = 60.0):
        self.motion_threshold, self.snore_level_min = motion_threshold, snore_level_min
        self.bright_lux, self.ext_min, self.ext_ratio = bright_lux, ext_min, ext_ratio
        self.snore_min_windows, self.restless_min_windows = snore_min_windows, restless_min_windows
        self.poor_score, self.alert_cooldown_ms = poor_score, int(alert_cooldown_s * 1000)
        self.monitoring = True
        self.history: deque[WindowResult] = deque(maxlen=history_windows)
        self.latest: dict[str, Telemetry] = {}
        self.last_seq: dict[tuple[str, str], int] = {}
        self.last_alert_ms: dict[str, int] = {}

    def set_monitoring(self, on: bool):
        self.monitoring = on
        self.history.clear()  # sesi pemantauan baru mulai dari nol
        self.last_alert_ms.clear()

    def accept(self, data: Telemetry, now_ms: int | None = None) -> Decision:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        if abs(now - data.sent_at_ms) > 30_000:
            return Decision("REJECTED_STALE", "Timestamp di luar jendela 30 detik (cek jam HP)")
        key = (data.device_id, data.boot_id)
        if data.sequence <= self.last_seq.get(key, -1):
            return Decision("REJECTED_REPLAY", "Sequence berulang/tidak berurutan untuk boot ID ini")
        self.last_seq[key] = data.sequence
        self.latest[data.device_id] = data

        if not self.monitoring:
            return Decision("PAUSED", "Pemantauan dijeda oleh pengguna")
        if "edge1" not in self.latest or "edge2" not in self.latest:
            return Decision("WAITING", "Menunggu kedua edge device")
        if data.device_id != "edge1":  # edge2 hanya memperbarui referensi lingkungan
            return Decision("WAITING", "Referensi lingkungan diperbarui")

        bed, room = self.latest["edge1"], self.latest["edge2"]
        if abs(bed.sent_at_ms - room.sent_at_ms) > 15_000:
            return Decision("REFERENCE_OLD", "Data kasur dan meja beda jendela waktu")
        return self._evaluate(bed.values, room.values, now)

    def _evaluate(self, bed: dict, room: dict, now: int) -> Decision:
        level, ext_peak = bed["snore_level"], room["ambient_peak"]
        loud = bed["snore_peaks"] >= 1 and level >= self.snore_level_min
        env = loud and ext_peak >= self.ext_min and level / ext_peak < self.ext_ratio
        self.history.append(WindowResult(
            restless=bed["motion_rms"] >= self.motion_threshold,
            snoring=loud and not env, env_noise=env,
            bright=room["light_lux"] >= self.bright_lux,
        ))

        n = len(self.history)
        c = {k: sum(getattr(w, k) for w in self.history)
             for k in ("restless", "snoring", "env_noise", "bright")}
        c["windows"] = n
        score = round(max(0.0, 100 - 40 * c["restless"] / n - 35 * c["snoring"] / n
                          - 25 * c["bright"] / n), 1)

        causes = []
        if c["restless"] >= self.restless_min_windows:
            causes.append(f"gelisah {c['restless']}/{n}")
        if c["snoring"] >= self.snore_min_windows:
            causes.append(f"mendengkur {c['snoring']}/{n}")
        if c["bright"] >= self.snore_min_windows:
            causes.append(f"kamar terang {c['bright']}/{n}")

        if n >= 3 and score <= self.poor_score:
            status, reason = "POOR_SLEEP_ALERT", "Kualitas tidur buruk: " + ", ".join(causes or ["skor rendah"])
        elif c["snoring"] >= self.snore_min_windows:
            status, reason = "HEAVY_SNORING", f"Dengkuran berulang terdeteksi di bantal ({c['snoring']}/{n} jendela)"
        elif c["restless"] >= self.restless_min_windows:
            status, reason = "RESTLESS", f"Kasur sering bergerak ({c['restless']}/{n} jendela)"
        elif c["env_noise"] >= 2:
            status, reason = "ENV_NOISE", "Suara keras juga terdengar di meja: kebisingan luar, bukan dengkuran"
        else:
            status = "DEEP_SLEEP"
            reason = "Gerakan minimal dan tanpa dengkuran" + (
                " (kamar agak terang)" if c["bright"] >= self.snore_min_windows else "")
        return Decision(status, reason, score, self._alert_target(status, now), c)

    def _alert_target(self, status: str, now: int) -> str | None:
        target = ALERT_TARGETS.get(status)
        if target and now - self.last_alert_ms.get(status, -10**15) >= self.alert_cooldown_ms:
            self.last_alert_ms[status] = now
            return target
        return None
