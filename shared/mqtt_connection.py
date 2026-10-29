"""SATU implementasi koneksi MQTT, dipakai SEMUA node."""

import os
import uuid

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

load_dotenv()

DEFAULT_HOST = "broker.hivemq.com"
DEFAULT_PROJECT_ID = "sleepguard_demo"
TOPIC_ROOT = "sleepguard"


def project_id() -> str:
    value = os.getenv("PROJECT_ID", DEFAULT_PROJECT_ID)
    if not value.replace("_", "").replace("-", "").isalnum():
        raise ValueError("PROJECT_ID hanya boleh huruf, angka, - dan _")
    return value


def topic(suffix: str) -> str:
    return f"{TOPIC_ROOT}/{project_id()}/{suffix}"


def create_client(role: str, will: tuple[str, str] | None = None) -> mqtt.Client:
    """Connect ke broker di .env. `will` = (topic, payload) retained yang
    dipublish broker jika client putus mendadak."""
    host = os.getenv("MQTT_HOST") or DEFAULT_HOST
    if project_id() == DEFAULT_PROJECT_ID:
        print(f"[MQTT] Peringatan: PROJECT_ID masih '{DEFAULT_PROJECT_ID}'. "
              "Ganti di .env agar topic tidak bercampur dengan kelompok lain.")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{project_id()}-{role}-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv311,
    )
    username = os.getenv("MQTT_USERNAME", "")
    if username:
        client.username_pw_set(username, os.getenv("MQTT_PASSWORD", ""))

    use_tls = os.getenv("MQTT_TLS", "true").lower() == "true"
    if use_tls:
        client.tls_set()
    elif os.getenv("ALLOW_INSECURE_LOCAL") != "true":
        raise RuntimeError("TLS dimatikan. Hanya boleh untuk development lokal: ALLOW_INSECURE_LOCAL=true")

    if will is not None:
        client.will_set(will[0], will[1], qos=1, retain=True)

    port = int(os.getenv("MQTT_PORT", "8883" if use_tls else "1883"))
    client.connect(host, port, keepalive=30)
    return client
