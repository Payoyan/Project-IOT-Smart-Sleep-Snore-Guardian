import unittest

from shared.processing import (bed_features, detect_snore_peaks, motion_rms,
                               pcm_to_levels, room_features)


class ProcessingTests(unittest.TestCase):
    def test_still_bed_has_near_zero_motion(self):
        self.assertAlmostEqual(motion_rms([(0, 0, 9.81)] * 10), 0, places=3)

    def test_rolling_increases_motion(self):
        samples = [(0, 0, 9.81 + (1.5 if i % 2 else -1.5)) for i in range(10)]
        self.assertGreater(motion_rms(samples), 1.0)

    def test_tilted_phone_bias_is_ignored(self):
        self.assertAlmostEqual(motion_rms([(3, 0, 9.0)] * 10), 0, places=3)

    def test_need_two_samples(self):
        with self.assertRaises(ValueError):
            motion_rms([(0, 0, 9.81)])

    def test_two_snore_bursts_counted(self):
        levels = [0.005] * 60
        for start in (5, 35):
            for i in range(start, start + 8):
                levels[i] = 0.12
        peaks, level = detect_snore_peaks(levels)
        self.assertEqual(peaks, 2)
        self.assertAlmostEqual(level, 0.12)

    def test_single_click_ignored(self):
        levels = [0.005] * 60
        levels[10] = 0.5
        self.assertEqual(detect_snore_peaks(levels)[0], 0)

    def test_silence_has_no_peaks(self):
        self.assertEqual(detect_snore_peaks([0.004] * 60), (0, 0.0))

    def test_burst_at_end_is_closed(self):
        levels = [0.005] * 55 + [0.1] * 5
        self.assertEqual(detect_snore_peaks(levels)[0], 1)

    def test_pcm_to_levels_full_scale(self):
        levels = pcm_to_levels([16384] * 800, 800)
        self.assertAlmostEqual(levels[0], 0.5, places=3)

    def test_features(self):
        f = bed_features([(0, 0, 9.81)] * 5, [0.005] * 60)
        self.assertEqual((f.snore_peaks, f.snore_level), (0, 0.0))
        r = room_features([10, 12, 11], [0.01, 0.03])
        self.assertEqual(r.light_lux, 11.0)
        self.assertEqual(r.ambient_peak, 0.03)


if __name__ == "__main__":
    unittest.main()
