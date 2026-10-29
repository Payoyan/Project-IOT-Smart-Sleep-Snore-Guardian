import json
import unittest

from nodes.detector_service.rules import SleepAnalyzer
from shared.messages import Telemetry, status_json

NOW = 1_790_000_000_000


def bed(seq, motion=0.02, peaks=0, level=0.0, t=NOW):
    return Telemetry("edge1", "b", seq, t, {"motion_rms": motion, "snore_peaks": peaks, "snore_level": level})


def room(seq, lux=1.0, peak=0.006, t=NOW):
    return Telemetry("edge2", "b", seq, t, {"light_lux": lux, "ambient_level": 0.005, "ambient_peak": peak})


def feed(analyzer, n, **kw):
    """n jendela berurutan; kembalikan keputusan terakhir."""
    decision, analyzer.alerts = None, []
    for i in range(n):
        seq = getattr(analyzer, "_seq", 0)
        analyzer._seq = seq + 1
        t = NOW + seq * 6000
        analyzer.accept(room(seq, kw.get("lux", 1.0), kw.get("ext", 0.006), t), now_ms=t)
        decision = analyzer.accept(bed(seq, kw.get("motion", 0.02), kw.get("peaks", 0),
                                       kw.get("level", 0.0), t), now_ms=t)
        if decision.alert_target:
            analyzer.alerts.append(decision.alert_target)
    return decision


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.a = SleepAnalyzer(alert_cooldown_s=60)

    def test_deep_sleep(self):
        d = feed(self.a, 5)
        self.assertEqual((d.status, d.score), ("DEEP_SLEEP", 100.0))

    def test_restless(self):
        self.assertEqual(feed(self.a, 5, motion=0.6).status, "RESTLESS")

    def test_heavy_snoring_targets_edge1(self):
        d = feed(self.a, 5, peaks=2, level=0.12, ext=0.03)
        self.assertEqual(d.status, "HEAVY_SNORING")
        self.assertEqual(self.a.alerts, ["edge1"])  # sekali saja (cooldown)

    def test_poor_sleep_targets_edge2(self):
        d = feed(self.a, 5, motion=0.8, peaks=2, level=0.15, ext=0.04, lux=80)
        self.assertEqual(d.status, "POOR_SLEEP_ALERT")
        self.assertEqual(self.a.alerts, ["edge2"])

    def test_bright_plus_restless_is_poor(self):
        self.assertEqual(feed(self.a, 5, motion=0.6, lux=80).status, "POOR_SLEEP_ALERT")

    def test_external_noise_not_snoring(self):
        d = feed(self.a, 5, peaks=2, level=0.08, ext=0.08)
        self.assertEqual(d.status, "ENV_NOISE")
        self.assertIsNone(d.alert_target)

    def test_alert_cooldown(self):
        feed(self.a, 5, peaks=2, level=0.12, ext=0.03)
        self.assertEqual(self.a.alerts, ["edge1"])
        feed(self.a, 5, peaks=2, level=0.12, ext=0.03)  # 30 dtk kemudian, masih cooldown
        self.assertEqual(self.a.alerts, [])
        self.a.alert_cooldown_ms = 0
        feed(self.a, 1, peaks=2, level=0.12, ext=0.03)
        self.assertEqual(self.a.alerts, ["edge1"])

    def test_single_noisy_window_not_enough(self):
        feed(self.a, 4)
        self.assertEqual(feed(self.a, 1, peaks=2, level=0.12, ext=0.03).status, "DEEP_SLEEP")

    def test_waits_for_both_edges(self):
        d = self.a.accept(bed(0), now_ms=NOW)
        self.assertEqual(d.status, "WAITING")

    def test_pause_and_resume_clears_history(self):
        feed(self.a, 5, motion=0.6)
        self.a.set_monitoring(False)
        self.assertEqual(self.a.accept(bed(99), now_ms=NOW).status, "PAUSED")
        self.a.set_monitoring(True)
        self.assertEqual(len(self.a.history), 0)

    def test_replay_and_stale_rejected(self):
        r = bed(3)
        self.a.accept(r, now_ms=NOW)
        self.assertEqual(self.a.accept(r, now_ms=NOW).status, "REJECTED_REPLAY")
        self.assertEqual(self.a.accept(bed(4, t=NOW - 31_000), now_ms=NOW).status, "REJECTED_STALE")

    def test_reference_too_old(self):
        self.a.accept(room(0, t=NOW - 20_000), now_ms=NOW - 20_000)
        self.assertEqual(self.a.accept(bed(0), now_ms=NOW).status, "REFERENCE_OLD")


class MessageTests(unittest.TestCase):
    def test_roundtrip(self):
        t = bed(1, 0.5, 2, 0.1)
        self.assertEqual(Telemetry.from_json(t.to_json()), t)

    def test_rejects_bad_payloads(self):
        good = json.loads(bed(1).to_json())
        for patch in ({"motion_rms": "inf"}, {"snore_peaks": -1}, {"device_id": "edge9"},
                      {"sequence": 1.5}, {"snore_level": None}):
            with self.assertRaises(ValueError):
                Telemetry.from_json(json.dumps({**good, **patch}))
        with self.assertRaises(ValueError):  # edge2 tidak boleh membawa field edge1
            Telemetry.from_json(json.dumps({**good, "device_id": "edge2"}))

    def test_status_json(self):
        s = json.loads(status_json("DEEP_SLEEP", "ok", True, 100.0, {"windows": 5}))
        self.assertEqual((s["status"], s["sleep_score"], s["monitoring"]), ("DEEP_SLEEP", 100.0, True))


if __name__ == "__main__":
    unittest.main()
