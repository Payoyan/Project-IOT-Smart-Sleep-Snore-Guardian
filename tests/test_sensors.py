import unittest

from shared.processing import bed_features, room_features
from shared.sensors import Scenario, SimAccelerometer, SimLight, SimMicrophone


class SimulatorTests(unittest.TestCase):
    def features(self, name):
        sc = Scenario(name)
        accel, mic = SimAccelerometer(sc), SimMicrophone(sc, "bed")
        mic.start(6)
        return bed_features([accel.read() for _ in range(30)], mic.collect())

    def test_deep_is_quiet(self):
        f = self.features("deep")
        self.assertLess(f.motion_rms, 0.2)
        self.assertEqual(f.snore_peaks, 0)

    def test_snoring_has_peaks(self):
        self.assertGreaterEqual(self.features("snoring").snore_peaks, 1)

    def test_restless_moves(self):
        self.assertGreater(self.features("restless").motion_rms, 0.2)

    def test_room_light(self):
        sc = Scenario("poor")
        mic = SimMicrophone(sc, "table")
        mic.start(6)
        r = room_features([SimLight(sc).read() for _ in range(3)], mic.collect())
        self.assertGreater(r.light_lux, 30)

    def test_unknown_scenario(self):
        with self.assertRaises(ValueError):
            Scenario("nope")


if __name__ == "__main__":
    unittest.main()
