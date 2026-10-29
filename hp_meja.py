"""NODE 2 (edge2): HP di meja/lampu tidur.
Di HP (Termux):  python hp_meja.py
Di laptop:       python hp_meja.py --source simulator --scenario night
"""
from shared.alarm import ring_alarm
from shared.edge_runner import run_edge

if __name__ == "__main__":
    run_edge("edge2", on_alert=ring_alarm)
