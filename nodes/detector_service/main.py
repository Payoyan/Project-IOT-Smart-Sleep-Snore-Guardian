"""NODE 3: detector subscribe MQTT, jalankan rules, publish status & alert.

Topic (lihat README):
  subscribe  edge/+/telemetry   telemetri kedua edge
  subscribe  control            START / PAUSE dari dashboard
  publish    alerts             HEAVY_SNORING -> edge1, POOR_SLEEP_ALERT -> edge2
  publish    status (retained)  setiap keputusan, untuk dashboard
"""

import json
import os
import time

from nodes.detector_service.rules import SleepAnalyzer
from shared.messages import Telemetry, status_json
from shared.mqtt_connection import create_client, topic


def _analyzer() -> SleepAnalyzer:
    return SleepAnalyzer(
        motion_threshold=float(os.getenv("MOTION_THRESHOLD", "0.2")),
        snore_level_min=float(os.getenv("SNORE_LEVEL_MIN", "0.03")),
        bright_lux=float(os.getenv("BRIGHT_LUX", "30")),
    )


def main():
    analyzer = _analyzer()
    status_topic = topic("status")
    offline = status_json("OFFLINE", "Detector terputus", monitoring=False)
    client = create_client("detector", will=(status_topic, offline))
    telemetry_topic, control_topic = topic("edge/+/telemetry"), topic("control")

    def publish_status(status, reason, score=0.0, counts=None, reading=None):
        client.publish(status_topic, status_json(
            status, reason, analyzer.monitoring, score, counts,
            device_id=reading.device_id if reading else None,
            sequence=reading.sequence if reading else None,
        ), qos=1, retain=True)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[DETECTOR] Koneksi MQTT ditolak: {reason_code}")
            return
        client.subscribe([(telemetry_topic, 1), (control_topic, 1)])
        print(f"[DETECTOR] Subscribed: {telemetry_topic} dan {control_topic}")
        publish_status("ONLINE", "Detector dimulai")

    def handle_control(payload: bytes):
        command = payload.decode(errors="replace").strip().upper()
        if command not in ("START", "PAUSE"):
            print(f"[DETECTOR] Kontrol tidak dikenal diabaikan: {command[:40]}")
            return
        analyzer.set_monitoring(command == "START")
        print(f"[DETECTOR] Perintah pengguna: {command}")
        publish_status("MONITORING" if analyzer.monitoring else "PAUSED", f"Pengguna mengirim {command}")

    def on_message(client, userdata, message):
        if message.topic == control_topic:
            handle_control(message.payload)
            return
        try:
            reading = Telemetry.from_json(message.payload)
            if message.topic != topic(f"edge/{reading.device_id}/telemetry"):
                print("[DETECTOR] DITOLAK: topic dan device ID tidak cocok")
                return
            decision = analyzer.accept(reading)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print(f"[DETECTOR] DITOLAK payload rusak: {exc}")
            return

        print(f"[DETECTOR] {reading.device_id} #{reading.sequence}: {decision.status} "
              f"(skor {decision.score}) — {decision.reason}")
        if not (decision.status == "WAITING" and len(analyzer.latest) == 2):
            publish_status(decision.status, decision.reason, decision.score, decision.counts, reading)
        if decision.alert_target:
            alert = {
                "event": "sleep_alert", "level": decision.status,
                "target": decision.alert_target, "sleep_score": decision.score,
                "reason": decision.reason, "detected_at_ms": int(time.time() * 1000),
            }
            client.publish(topic("alerts"), json.dumps(alert), qos=1, retain=False)

    client.on_connect, client.on_message = on_connect, on_message
    print("[DETECTOR] Mulai. Ctrl+C untuk berhenti")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("[DETECTOR] Berhenti")
    finally:
        client.loop_start()
        try:
            client.publish(status_topic, status_json("OFFLINE", "Detector berhenti", monitoring=False),
                           qos=1, retain=True).wait_for_publish(timeout=3)
        except (RuntimeError, ValueError):
            pass
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
