"""NODE 1: HP di kasur/bantal. Accelerometer + mikrofon -> processing -> MQTT.
Menerima alert HEAVY_SNORING: getar lembut agar berganti posisi."""

from shared.alarm import nudge_pillow
from shared.edge_runner import run_edge

if __name__ == "__main__":
    run_edge("edge1", on_alert=nudge_pillow)
