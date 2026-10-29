"""OUTPUT / AKTUATOR: reaksi HP saat ada alert (Termux:API).
Di laptop hanya mencetak ke terminal, jadi bisa dijalankan di mana saja."""

import shutil
import subprocess


def _run_quietly(command: list[str]):
    try:
        subprocess.run(command, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[ALARM] Tidak bisa menjalankan {command[0]}: {exc}")


def nudge_pillow(alert: dict):
    """Edge 1 (di bantal): getaran pendek & lembut agar pengguna berganti posisi."""
    print(f"\n[EDGE1 | NUDGE] Dengkuran keras: getar lembut. skor={alert.get('sleep_score', '?')}\n")
    if shutil.which("termux-vibrate"):
        _run_quietly(["termux-vibrate", "-d", "500"])


def ring_alarm(alert: dict):
    """Edge 2 (di meja): getar + notifikasi untuk kualitas tidur buruk."""
    reason = str(alert.get("reason", "Kualitas tidur buruk"))
    score = alert.get("sleep_score", "?")
    print(f"\n[EDGE2 | ALARM] Tidur buruk! skor={score} — {reason}\n")
    if shutil.which("termux-vibrate"):
        _run_quietly(["termux-vibrate", "-d", "1500"])
    if shutil.which("termux-notification"):
        _run_quietly([
            "termux-notification", "--id", "sleepguard",
            "--title", "SleepGuard: kualitas tidur buruk",
            "--content", f"Skor {score}. {reason}", "--priority", "high",
        ])
