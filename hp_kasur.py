"""NODE 1 (edge1): HP di kasur.
Di HP (Termux):  python hp_kasur.py
Di laptop:       python hp_kasur.py --source simulator --scenario night
"""
from shared.alarm import nudge_pillow
from shared.edge_runner import run_edge

if __name__ == "__main__":
    run_edge("edge1", on_alert=nudge_pillow)
