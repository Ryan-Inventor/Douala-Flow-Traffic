"""
==============================================================================
DOUALAFLOW — Moniteur Temps Réel (Terminal)
==============================================================================

Ce script affiche en direct les données de trafic toutes les 2 secondes
pour vérifier que le système fonctionne vraiment en temps réel.

LANCER :
    python tests/test_realtime.py
    (Le serveur Flask doit tourner : python backend/app.py)
==============================================================================
"""

import sys
import time
import requests
import os

BASE_URL = "http://localhost:5000"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def color_for(cong):
    if cong > 70: return "\033[91m"   # Rouge
    if cong > 55: return "\033[33m"   # Orange
    if cong > 40: return "\033[93m"   # Jaune
    return "\033[92m"                  # Vert

def bar(value, width=20):
    filled = int(value / 100 * width)
    return "█" * filled + "░" * (width - filled)

def fetch():
    try:
        r = requests.get(f"{BASE_URL}/api/current", timeout=3)
        return r.json() if r.ok else None
    except:
        return None

def fetch_vehicles():
    try:
        r = requests.get(f"{BASE_URL}/api/vehicles", timeout=3)
        return r.json() if r.ok else None
    except:
        return None

def monitor(duration_seconds=60):
    print("\n  DOUALAFLOW — Moniteur Temps Réel")
    print(f"  Appuyez sur Ctrl+C pour arrêter\n")

    prev_data = None
    start     = time.time()
    calls     = 0
    changes   = 0

    try:
        while time.time() - start < duration_seconds:
            calls += 1
            data = fetch()
            veh  = fetch_vehicles()

            clear()
            now = time.strftime("%H:%M:%S")
            elapsed = int(time.time() - start)

            print(f"\033[1m  DoualaFlow — Moniteur Temps Réel\033[0m")
            print(f"  Heure : {now}  |  Durée : {elapsed}s  |  Appels API : {calls}  |  Variations détectées : {changes}")
            print(f"  {'─'*65}")

            if not data:
                print("\n  \033[91m✗ Serveur non joignable sur " + BASE_URL + "\033[0m")
                print("  Lance : python backend/app.py\n")
                time.sleep(2)
                continue

            axes = data.get("axes", {})
            timestamp = data.get("timestamp", "?")[:19]

            print(f"\n  Timestamp API : {timestamp}")
            print(f"  Heure trafic  : {data.get('current_hour', '?')}h\n")
            print(f"  {'Axe':<12}  {'Congestion':>10}  {'Barre':22}  {'Vitesse':>8}  {'Statut':<10}  {'Δ'}")
            print(f"  {'─'*75}")

            for name, info in sorted(axes.items(), key=lambda x: -x[1]["congestion"]):
                cong   = info["congestion"]
                speed  = info["speed_kmh"]
                status = info["status"]
                c      = color_for(cong)

                # Détecter les changements vs l'appel précédent
                delta_str = ""
                if prev_data and name in prev_data.get("axes", {}):
                    prev_cong = prev_data["axes"][name]["congestion"]
                    delta = cong - prev_cong
                    if abs(delta) > 0.05:
                        changes += 1
                        arrow = "↑" if delta > 0 else "↓"
                        delta_col = "\033[91m" if delta > 0 else "\033[92m"
                        delta_str = f"{delta_col}{arrow}{abs(delta):.1f}%\033[0m"

                print(f"  {name:<12}  {c}{cong:>9.1f}%\033[0m  {c}{bar(cong)}\033[0m  {speed:>6.1f}km/h  {c}{status:<10}\033[0m  {delta_str}")

            # Stats globales
            congs = [a["congestion"] for a in axes.values()]
            avg   = sum(congs) / len(congs) if congs else 0
            print(f"\n  Moyenne : {avg:.1f}%  |  Min : {min(congs):.1f}%  |  Max : {max(congs):.1f}%  |  Écart : {max(congs)-min(congs):.1f}%")

            # Véhicules
            if veh:
                count = veh.get("count", 0)
                print(f"  Véhicules sur la carte : {count}")

            # Diagnostic
            print(f"\n  {'─'*65}")
            if max(congs) - min(congs) < 5:
                print("  \033[91m⚠ ATTENTION : Tous les axes ont une congestion similaire !\033[0m")
                print("  \033[91m  → Le générateur de données produit des valeurs trop uniformes.\033[0m")
            else:
                print("  \033[92m✓ Les axes ont des niveaux de congestion variés.\033[0m")

            saturated = sum(1 for c in congs if c > 70)
            if saturated == len(congs):
                print("  \033[91m⚠ TOUS les axes sont saturés — comportement anormal !\033[0m")
            elif saturated > 0:
                print(f"  \033[93m⚠ {saturated}/{len(congs)} axes saturés.\033[0m")
            else:
                print("  \033[92m✓ Aucun axe saturé.\033[0m")

            prev_data = data
            time.sleep(2)

    except KeyboardInterrupt:
        pass

    print(f"\n\n  Moniteur arrêté.")
    print(f"  Résumé : {calls} appels, {changes} variations détectées")
    if calls > 0 and changes == 0:
        print("  \033[91m✗ Aucune variation — le temps réel ne fonctionne PAS !\033[0m")
    elif changes > calls * 0.3:
        print("  \033[92m✓ Le temps réel fonctionne correctement.\033[0m")
    else:
        print("  \033[93m⚠ Peu de variations — le temps réel est limité.\033[0m")
    print()


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    monitor(duration)
