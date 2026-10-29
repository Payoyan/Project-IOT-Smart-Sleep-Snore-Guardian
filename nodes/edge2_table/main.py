"""NODE 2: HP di meja/lampu tidur. Sensor cahaya + mikrofon lingkungan -> MQTT.
Menerima alert POOR_SLEEP_ALERT: getar + notifikasi."""

from shared.alarm import ring_alarm
from shared.edge_runner import run_edge

if __name__ == "__main__":
    run_edge("edge2", on_alert=ring_alarm)
