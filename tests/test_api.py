"""
==============================================================================
DOUALAFLOW — Tests de l'API Flask
==============================================================================

Ce fichier vérifie :
1. Que le serveur Flask est accessible
2. Que tous les endpoints répondent correctement
3. Que les données changent entre deux appels (vrai temps réel)
4. Que les axes ont des congestions DIFFÉRENTES (pas tous saturés)
5. Que la carte se met à jour en temps réel

LANCER :
    python tests/test_api.py
    (Le serveur Flask doit être lancé en parallèle)
==============================================================================
"""

import sys
import time
import json
import requests

BASE_URL = "http://localhost:5000"
TIMEOUT  = 5  # secondes

# ============================================================
# Utilitaires
# ============================================================

def ok(msg):
    print(f"  \033[92m✓\033[0m  {msg}")

def fail(msg):
    print(f"  \033[91m✗\033[0m  {msg}")

def warn(msg):
    print(f"  \033[93m⚠\033[0m  {msg}")

def header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def get(endpoint):
    """Appelle un endpoint et retourne (status_code, data)."""
    try:
        resp = requests.get(f"{BASE_URL}{endpoint}", timeout=TIMEOUT)
        return resp.status_code, resp.json()
    except requests.exceptions.ConnectionError:
        return None, None
    except Exception as e:
        return -1, str(e)


# ============================================================
# TEST 1 : Connectivité de base
# ============================================================

def test_connectivity():
    header("TEST 1 — Connectivité du serveur Flask")
    status, _ = get("/")
    if status is None:
        fail(f"Serveur inaccessible sur {BASE_URL}")
        fail("Lance : python backend/app.py")
        sys.exit(1)
    elif status == 200:
        ok(f"Serveur accessible — GET / → HTTP {status}")
    else:
        warn(f"GET / retourne HTTP {status} (attendu 200)")


# ============================================================
# TEST 2 : Tous les endpoints répondent
# ============================================================

def test_endpoints():
    header("TEST 2 — Disponibilité des endpoints API")

    endpoints = [
        ("/api/current",     "État du trafic"),
        ("/api/stats",       "Statistiques globales"),
        ("/api/vehicles",    "Positions des véhicules"),
        ("/api/chart",       "Données graphique 24h"),
        ("/api/predictions", "Prédictions ML"),
    ]

    all_ok = True
    for path, label in endpoints:
        status, data = get(path)
        if status == 200 and data:
            ok(f"{path:25} → HTTP 200  ({label})")
        elif status == 503:
            fail(f"{path:25} → HTTP 503  ({label}) — Données non générées !")
            fail("Lance : python backend/generate_data.py && python backend/process_bigdata.py")
            all_ok = False
        else:
            fail(f"{path:25} → HTTP {status}  ({label})")
            all_ok = False

    return all_ok


# ============================================================
# TEST 3 : Structure des données /api/current
# ============================================================

def test_current_structure():
    header("TEST 3 — Structure de /api/current")

    _, data = get("/api/current")
    if not data:
        fail("Données non disponibles")
        return False

    # Champs requis
    required_top = ["timestamp", "current_hour", "axes"]
    for field in required_top:
        if field in data:
            ok(f"Champ '{field}' présent")
        else:
            fail(f"Champ '{field}' MANQUANT")

    axes = data.get("axes", {})
    print(f"\n  Axes disponibles : {list(axes.keys())}")

    required_axis_fields = ["label", "congestion", "speed_kmh", "status", "color", "coords"]
    if axes:
        sample_axis = next(iter(axes.values()))
        for field in required_axis_fields:
            if field in sample_axis:
                ok(f"  Axe → champ '{field}' présent")
            else:
                fail(f"  Axe → champ '{field}' MANQUANT")

    return True


# ============================================================
# TEST 4 : Les axes ne sont pas tous saturés
# ============================================================

def test_axes_diversity():
    header("TEST 4 — Diversité des niveaux de congestion")

    _, data = get("/api/current")
    if not data:
        fail("Données non disponibles")
        return

    axes = data.get("axes", {})
    congestions = {name: info["congestion"] for name, info in axes.items()}
    statuses    = {name: info["status"]     for name, info in axes.items()}

    print("\n  Congestion actuelle par axe :")
    for name, cong in sorted(congestions.items(), key=lambda x: -x[1]):
        status = statuses[name]
        bar = "█" * int(cong / 5)
        color = "\033[91m" if cong > 70 else "\033[93m" if cong > 40 else "\033[92m"
        print(f"    {name:12} {color}{bar:20}\033[0m {cong:5.1f}% — {status}")

    # Vérifications
    all_congestions = list(congestions.values())
    min_cong = min(all_congestions)
    max_cong = max(all_congestions)
    diff = max_cong - min_cong

    print()
    if diff > 10:
        ok(f"Variation entre axes : {diff:.1f}% (min={min_cong:.1f}%, max={max_cong:.1f}%)")
    else:
        fail(f"Variation trop faible : seulement {diff:.1f}% entre les axes !")
        warn("Tous les axes semblent avoir la même congestion — problème de simulation")

    saturated = [n for n, s in statuses.items() if s == "SATURÉ"]
    fluide    = [n for n, s in statuses.items() if s == "FLUIDE"]

    if len(saturated) == len(axes):
        fail(f"TOUS les axes ({len(axes)}) sont SATURÉS — comportement anormal !")
    elif len(saturated) > 0:
        ok(f"Axes saturés : {saturated}")
    else:
        ok("Aucun axe saturé pour l'instant")

    if fluide:
        ok(f"Axes fluides : {fluide}")


# ============================================================
# TEST 5 : Temps réel — Les données changent entre appels
# ============================================================

def test_realtime_variation():
    header("TEST 5 — Variation en temps réel (3 appels espacés de 3s)")

    print("  Appel 1...")
    _, data1 = get("/api/current")
    time.sleep(3)

    print("  Appel 2...")
    _, data2 = get("/api/current")
    time.sleep(3)

    print("  Appel 3...")
    _, data3 = get("/api/current")

    if not data1 or not data2 or not data3:
        fail("Données non disponibles")
        return

    # Comparer les congestions
    print("\n  Variation de congestion entre les 3 appels :")
    print(f"  {'Axe':12} {'Appel 1':>8} {'Appel 2':>8} {'Appel 3':>8} {'Variation':>10}")
    print(f"  {'-'*50}")

    all_varied = True
    for name in data1["axes"]:
        c1 = data1["axes"][name]["congestion"]
        c2 = data2["axes"].get(name, {}).get("congestion", c1)
        c3 = data3["axes"].get(name, {}).get("congestion", c1)
        variation = max(c1, c2, c3) - min(c1, c2, c3)
        varied = variation > 0.1

        marker = "\033[92m✓\033[0m" if varied else "\033[91m✗\033[0m"
        print(f"  {marker} {name:12} {c1:>7.1f}% {c2:>7.1f}% {c3:>7.1f}%  Δ={variation:5.2f}%")
        if not varied:
            all_varied = False

    print()
    if all_varied:
        ok("Toutes les valeurs varient entre les appels ✓")
    else:
        fail("Certaines valeurs ne varient pas — la simulation ne fonctionne pas !")


# ============================================================
# TEST 6 : Véhicules sur la carte
# ============================================================

def test_vehicles():
    header("TEST 6 — Véhicules sur la carte")

    _, data = get("/api/vehicles")
    if not data:
        fail("Données non disponibles")
        return

    vehicles = data.get("vehicles", [])
    count    = data.get("count", 0)

    ok(f"{count} véhicules retournés")

    if not vehicles:
        fail("Aucun véhicule ! La carte sera vide.")
        return

    # Vérifier structure d'un véhicule
    v = vehicles[0]
    for field in ["id", "lat", "lon", "color", "speed"]:
        if field in v:
            ok(f"  Véhicule → champ '{field}' = {v[field]}")
        else:
            fail(f"  Véhicule → champ '{field}' MANQUANT")

    # Vérifier que les véhicules couvrent plusieurs axes
    axes_covered = set(v.get("axis", "?") for v in vehicles)
    ok(f"Axes couverts par les véhicules : {axes_covered}")

    # Appel 2 : vérifier que les positions changent
    time.sleep(2)
    _, data2 = get("/api/vehicles")
    if data2:
        v2 = {v["id"]: v for v in data2.get("vehicles", [])}
        if v["id"] in v2:
            lat1 = v["lat"]
            lat2 = v2[v["id"]]["lat"]
            if abs(lat1 - lat2) > 1e-6:
                ok(f"Position du véhicule {v['id']} a changé ✓")
            else:
                warn(f"Position du véhicule {v['id']} n'a pas changé")


# ============================================================
# TEST 7 : Prédictions ML
# ============================================================

def test_predictions():
    header("TEST 7 — Prédictions ML")

    _, data = get("/api/predictions")
    if not data:
        fail("Données non disponibles")
        return

    horizons = data.get("horizons", {})
    for h in ["+1h", "+2h", "+3h"]:
        if h in horizons:
            label = horizons[h].get("label", "?")
            nb_axes = len(horizons[h].get("axes", {}))
            ok(f"Horizon {h} : '{label}' — {nb_axes} axes prédits")
        else:
            fail(f"Horizon {h} manquant")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  DOUALAFLOW — Suite de Tests de l'API")
    print("  Serveur cible : " + BASE_URL)
    print("=" * 60)

    test_connectivity()

    if not test_endpoints():
        print("\n\033[91m  ✗ Les données ne sont pas générées.\033[0m")
        print("  Lancez ces commandes dans l'ordre :")
        print("    python backend/generate_data.py")
        print("    python backend/process_bigdata.py")
        print("    python backend/app.py")
        sys.exit(1)

    test_current_structure()
    test_axes_diversity()
    test_realtime_variation()
    test_vehicles()
    test_predictions()

    print("\n" + "=" * 60)
    print("  Tests terminés.")
    print("=" * 60 + "\n")
