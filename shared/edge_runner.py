"""Pipeline edge bersama: sensor nyata -> processing -> MQTT Cloud.

edge1 (kasur): accelerometer + mikrofon -> motion_rms, snore_peaks, snore_level
edge2 (meja) : sensor cahaya + mikrofon -> light_lux, ambient_level, ambient_peak
Simulator hanya untuk latihan dan TIDAK boleh disebut demo edge fisik.
"""

import argparse
import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict

from shared.messages import Telemetry
from shared.mqtt_connection import create_client, topic
from shared.processing import bed_features, room_features
from shared.sensors import SCENARIOS, Scenario, make_bed_sensors, make_room_sensors

AlertHandler = Callable[[dict], None]


def _parse_args(device_id: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=f"SleepGuard {device_id}")
    p.add_argument("--source", choices=["android", "simulator"], default="android")
    p.add_argument("--scenario", choices=SCENARIOS, default="night",
                   help="Hanya untuk --source simulator")
    p.add_argument("--window", type=float, default=6.0, help="Panjang jendela (detik)")
    p.add_argument("--interval", type=float, default=0.2, help="Jeda antar pembacaan sensor (detik)")
    p.add_argument("--debug-sensors", action="store_true", help="Cetak data sensor mentah")
    args = p.parse_args()
    if args.window < 2 or args.interval <= 0:
        p.error("--window minimal 2 dan --interval harus positif")
    return args


def collect_bed(sensors, args) -> dict:
    accel, mic = sensors
    mic.start(args.window)
    samples, end = [], time.monotonic() + args.window
    while time.monotonic() < end:
        samples.append(accel.read())
        if args.debug_sensors:
            print(f"[EDGE1 | RAW] accel={samples[-1]}", flush=True)
        time.sleep(args.interval)
    levels = mic.collect()
    return asdict(bed_features(samples, levels, float(os.getenv("SNORE_ABS_MIN", "0.02"))))


def collect_room(sensors, args) -> dict:
    light, mic = sensors
    mic.start(args.window)
    lux_values, end = [], time.monotonic() + args.window
    while time.monotonic() < end:
        value = light.read()
        if value is not None:
            lux_values.append(value)
            if args.debug_sensors:
                print(f"[EDGE2 | RAW] lux={value}", flush=True)
        time.sleep(max(args.interval, args.window / 3))  # cahaya berubah lambat
    levels = mic.collect()
    return asdict(room_features(lux_values, levels))


def run_edge(device_id: str, on_alert: AlertHandler | None = None):
    args = _parse_args(device_id)
    label = device_id.upper()
    scenario = Scenario(args.scenario)
    if device_id == "edge1":
        sensors, collect = make_bed_sensors(args.source, scenario), collect_bed
    else:
        sensors, collect = make_room_sensors(args.source, scenario), collect_room
    client = create_client(device_id)

    if on_alert is not None:
        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                print(f"[{label}] Koneksi MQTT ditolak: {reason_code}")
                return
            client.subscribe(topic("alerts"), qos=1)
            print(f"[{label}] Subscribed ke {topic('alerts')}")

        def on_message(client, userdata, message):
            try:
                alert = json.loads(message.payload)
                if not isinstance(alert, dict):
                    raise ValueError
            except ValueError:
                print(f"[{label}] Alert rusak diabaikan")
                return
            if alert.get("target") == device_id:  # hanya alert untuk HP ini
                on_alert(alert)

        client.on_connect, client.on_message = on_connect, on_message

    client.loop_start()
    boot_id, sequence = uuid.uuid4().hex, 0
    telemetry_topic = topic(f"edge/{device_id}/telemetry")
    print(f"[{label}] Source: {args.source}" + (f" / scenario: {args.scenario}" if args.source == "simulator" else ""))
    print(f"[{label}] Publishes to: {telemetry_topic}")

    try:
        while True:
            try:
                values = collect(sensors, args)
            except (RuntimeError, ValueError) as exc:  # jangan mati di tengah malam
                print(f"[{label}] Gagal baca sensor, coba lagi: {exc}")
                time.sleep(2)
                continue
            telemetry = Telemetry.make(device_id, boot_id, sequence, values)
            client.publish(telemetry_topic, telemetry.to_json(), qos=1).wait_for_publish(timeout=10)
            print(f"[{label}] #{sequence} " + ", ".join(f"{k}={v:g}" for k, v in values.items()), flush=True)
            sequence += 1
    except KeyboardInterrupt:
        print(f"[{label}] Berhenti")
    finally:
        client.loop_stop()
        client.disconnect()
