"""NODE 3 — Laptop: detector MQTT + dashboard browser.

Jalankan: python detector.py
Buka link http://localhost:8000 yang tercetak di laptop ini.
"""

from nodes.detector_service.main import main
from shared.dashboard_server import start_dashboard_server
from shared.mqtt_connection import project_id


def run():
    try:
        server, thread, url = start_dashboard_server()
    except OSError as exc:
        raise SystemExit(f"[DASHBOARD] Gagal membuka port dashboard: {exc}. "
                         "Tutup aplikasi lain di port itu atau set DASHBOARD_PORT di .env.") from exc

    print("\nSmart Sleep & Snore Guardian — NODE 3 / Laptop", flush=True)
    print(f"[DASHBOARD] Buka di laptop: {url}", flush=True)
    print(f"[CONFIG] PROJECT_ID: {project_id()}", flush=True)
    print("[DETECTOR] Menunggu Edge 1 (kasur) dan Edge 2 (meja) dari MQTT Cloud...\n", flush=True)
    try:
        main()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    run()
