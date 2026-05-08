"""
==============================================================================
DOUALAFLOW — Étape 3 : Serveur API Flask (CORRIGÉ - Temps Réel)
==============================================================================

RÔLE DE CE FICHIER :
    Servir l'application web DoualaFlow complète via un mini-serveur HTTP.

    Ce fichier a DEUX responsabilités :
    1. Servir les fichiers statiques (HTML, CSS, JS) → l'interface utilisateur
    2. Exposer des endpoints d'API (JSON) → les données pour les graphiques

CORRECTIONS APPLIQUÉES :
    - /api/current recalcule DYNAMIQUEMENT la congestion selon l'heure réelle
    - Chaque axe a un profil de congestion unique (variabilité inter-axes)
    - Les axes ne sont plus tous saturés au même moment
    - La carte se met vraiment à jour entre les appels

ENDPOINTS DE L'API :
    GET /                          → Sert le dashboard HTML
    GET /api/current               → État actuel (recalculé dynamiquement)
    GET /api/chart                 → Données du graphique 24h
    GET /api/predictions           → Prédictions ML +1h, +2h, +3h
    GET /api/vehicles              → Positions animées des véhicules
    GET /api/stats                 → Statistiques globales (KPIs)

COMMENT LANCER :
    python backend/app.py
    → Ouvrir : http://localhost:5000
==============================================================================
"""

import os
import json
import random
import math
from datetime import datetime
from flask import Flask, jsonify, send_from_directory, abort
from flask_cors import CORS

# ==============================================================================
# INITIALISATION DE L'APPLICATION FLASK
# ==============================================================================

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
FRONTEND_DIR  = os.path.join(BASE_DIR, "frontend")

app = Flask(
    __name__,
    static_folder=os.path.join(FRONTEND_DIR),
    template_folder=os.path.join(FRONTEND_DIR)
)
# Ne pas encoder les accents en \uXXXX dans les réponses JSON
app.config['JSON_ENSURE_ASCII'] = False
CORS(app)

# ==============================================================================
# PROFILS HORAIRES PAR AXE — clé de la correction "tous saturés"
# ==============================================================================
# Chaque axe a un profil DIFFÉRENT selon sa nature (commercial, industriel, résidentiel).
# Le multiplicateur (0.0 à 1.0) représente la charge à chaque heure.
# Des valeurs différentes évitent la saturation simultanée de tous les axes.

AXIS_HOURLY_PROFILES = {
    # Carrefour principal — forte pointe matin ET soir, jamais fluide
    "ndokoti": {
        0: 0.15, 1: 0.08, 2: 0.06, 3: 0.06, 4: 0.10,
        5: 0.25, 6: 0.55,
        7: 0.82, 8: 0.95,   # Pointe matin (presque saturé)
        9: 0.72, 10: 0.58, 11: 0.52,
        12: 0.65, 13: 0.60, 14: 0.50,
        15: 0.58, 16: 0.72,
        17: 0.90, 18: 1.00,  # Pointe soir (saturé)
        19: 0.80, 20: 0.58, 21: 0.38, 22: 0.22, 23: 0.14
    },
    # Pont inter-rives — saturé le soir (navetteurs), fluide le matin
    "bonaberi": {
        0: 0.10, 1: 0.06, 2: 0.05, 3: 0.05, 4: 0.08,
        5: 0.18, 6: 0.38,
        7: 0.52, 8: 0.65,   # Pointe matin modérée
        9: 0.45, 10: 0.35, 11: 0.30,
        12: 0.42, 13: 0.38, 14: 0.32,
        15: 0.40, 16: 0.58,
        17: 0.80, 18: 0.92,  # Pointe soir forte
        19: 0.72, 20: 0.50, 21: 0.32, 22: 0.18, 23: 0.10
    },
    # Zone industrielle — actif tôt le matin, calme le soir
    "bassa": {
        0: 0.08, 1: 0.05, 2: 0.05, 3: 0.08, 4: 0.18,
        5: 0.42, 6: 0.65,   # Trafic lourd tôt
        7: 0.75, 8: 0.80,
        9: 0.60, 10: 0.55, 11: 0.52,
        12: 0.58, 13: 0.52, 14: 0.55,
        15: 0.60, 16: 0.65,
        17: 0.55, 18: 0.42,  # Pointe soir faible (industrie fermée)
        19: 0.30, 20: 0.20, 21: 0.12, 22: 0.08, 23: 0.06
    },
    # Centre-ville — actif toute la journée, congestionné midi
    "akwa": {
        0: 0.12, 1: 0.07, 2: 0.05, 3: 0.05, 4: 0.10,
        5: 0.22, 6: 0.45,
        7: 0.68, 8: 0.78,
        9: 0.65, 10: 0.62, 11: 0.68,
        12: 0.80, 13: 0.72,  # Forte pause déjeuner (commerces)
        14: 0.58, 15: 0.62, 16: 0.70,
        17: 0.82, 18: 0.88,
        19: 0.70, 20: 0.55, 21: 0.40, 22: 0.25, 23: 0.14
    },
    # Zone résidentielle nord — surtout matin et soir, calme la journée
    "makepe": {
        0: 0.08, 1: 0.05, 2: 0.04, 3: 0.04, 4: 0.07,
        5: 0.20, 6: 0.48,
        7: 0.72, 8: 0.68,   # Pointe matin (départ bureau)
        9: 0.40, 10: 0.28, 11: 0.25,
        12: 0.32, 13: 0.28, 14: 0.22,
        15: 0.28, 16: 0.42,
        17: 0.70, 18: 0.78,  # Retour domicile
        19: 0.60, 20: 0.38, 21: 0.22, 22: 0.12, 23: 0.07
    },
    # Périphérie nord / autoroute — flux régulier, jamais vraiment saturé
    "logbessou": {
        0: 0.05, 1: 0.03, 2: 0.02, 3: 0.03, 4: 0.08,
        5: 0.15, 6: 0.30,
        7: 0.45, 8: 0.52,   # Pointe matin légère
        9: 0.38, 10: 0.30, 11: 0.28,
        12: 0.35, 13: 0.30, 14: 0.28,
        15: 0.32, 16: 0.42,
        17: 0.55, 18: 0.62,  # Jamais vraiment saturé (voie express)
        19: 0.48, 20: 0.32, 21: 0.20, 22: 0.12, 23: 0.06
    },
}

# Vitesse libre (km/h) par axe — utilisée pour calculer la vitesse réelle
AXIS_FREE_FLOW = {
    "ndokoti":   40,
    "bonaberi":  55,
    "bassa":     38,
    "akwa":      30,
    "makepe":    45,
    "logbessou": 65,
}

# Coordonnées GPS par axe
AXES_COORDS = {
    "ndokoti":   [[4.0511,9.7085],[4.0530,9.7095],[4.0550,9.7100],[4.0570,9.7110],[4.0590,9.7105],[4.0610,9.7095]],
    "bonaberi":  [[4.0731,9.6821],[4.0720,9.6850],[4.0710,9.6880],[4.0695,9.6910],[4.0680,9.6940],[4.0660,9.6960]],
    "bassa":     [[4.0234,9.7412],[4.0250,9.7430],[4.0265,9.7450],[4.0280,9.7465],[4.0295,9.7480],[4.0310,9.7490]],
    "akwa":      [[4.0487,9.7012],[4.0500,9.7030],[4.0515,9.7048],[4.0528,9.7063],[4.0540,9.7078],[4.0555,9.7090]],
    "makepe":    [[4.0812,9.7234],[4.0825,9.7250],[4.0838,9.7265],[4.0850,9.7280],[4.0862,9.7295],[4.0875,9.7305]],
    "logbessou": [[4.1021,9.7156],[4.1005,9.7170],[4.0990,9.7185],[4.0975,9.7198],[4.0960,9.7212],[4.0945,9.7225]],
}

AXES_METADATA = {
    "ndokoti":   {"label": "Ndokoti",   "zone": "Carrefour Central — Zone très dense"},
    "bonaberi":  {"label": "Bonabéri",  "zone": "Pont sur le Wouri — Axe inter-rives"},
    "bassa":     {"label": "Bassa",     "zone": "Zone Industrielle — Trafic lourd"},
    "akwa":      {"label": "Akwa",      "zone": "Centre-Ville & Affaires"},
    "makepe":    {"label": "Makepe",    "zone": "Zone Résidentielle Nord"},
    "logbessou": {"label": "Logbessou", "zone": "Périphérie Nord — Accès autoroute"},
}

# ==============================================================================
# UTILITAIRES — Calcul dynamique du trafic
# ==============================================================================

def compute_congestion(axis_name: str, hour: int, minute: int = 0) -> float:
    """
    Calcule le niveau de congestion pour un axe à une heure donnée.

    Utilise une interpolation entre les heures pour une évolution fluide
    (la congestion ne saute pas brusquement à chaque heure pile).

    Args:
        axis_name: Nom de l'axe
        hour: Heure (0-23)
        minute: Minute (0-59) — pour l'interpolation

    Returns:
        float: Congestion en % (0-100)
    """
    profile = AXIS_HOURLY_PROFILES.get(axis_name, {})
    if not profile:
        return 50.0

    # Interpolation linéaire entre l'heure H et H+1
    h_next = (hour + 1) % 24
    val_now  = profile.get(hour,  0.5)
    val_next = profile.get(h_next, 0.5)
    t = minute / 60.0
    base_factor = val_now + t * (val_next - val_now)

    # Bruit stochastique : simule les micro-fluctuations du trafic réel
    # Chaque axe a un bruit indépendant → ils ne saturent pas ensemble
    noise = random.gauss(0, 0.04)  # σ=4% de variation aléatoire
    factor = max(0.0, min(1.0, base_factor + noise))

    # Convertir le facteur [0,1] en indice de congestion [0,100]
    # Formule calibrée : factor=1.0 → 90% max (jamais 100% sauf incident)
    congestion = factor * 88 + random.uniform(-2, 2)
    return round(max(0.0, min(98.0, congestion)), 1)


def congestion_to_speed(congestion: float, free_flow: float) -> float:
    """
    Convertit la congestion en vitesse observée (km/h).
    Modèle BPR (Bureau of Public Roads) simplifié.
    """
    ratio = (1 - congestion / 100) ** 1.5
    speed = free_flow * ratio
    speed += random.gauss(0, 1.5)  # Bruit naturel
    return round(max(3.0, speed), 1)


def get_color(congestion: float) -> str:
    if congestion > 70: return "#ef4444"
    if congestion > 55: return "#f97316"
    if congestion > 40: return "#eab308"
    return "#22c55e"


def get_status(congestion: float) -> str:
    if congestion > 70: return "SATURÉ"
    if congestion > 40: return "RALENTI"
    return "FLUIDE"


def load_json(filename: str) -> dict:
    """Charge un fichier JSON depuis data/processed/ (fallback statique)."""
    path = os.path.join(PROCESSED_DIR, filename)
    if not os.path.exists(path):
        abort(
            503,
            description="Données non générées. Lancez d'abord : python backend/process_bigdata.py"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# ROUTES FRONTEND
# ==============================================================================

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, "css"), filename)

@app.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, "js"), filename)


# ==============================================================================
# ROUTES API
# ==============================================================================

@app.route("/api/current")
def api_current():
    """
    État actuel de chaque axe — RECALCULÉ DYNAMIQUEMENT à chaque appel.

    Contrairement à la version précédente qui lisait un JSON statique,
    cette version calcule la congestion en temps réel selon :
    - L'heure et la minute actuelles
    - Le profil horaire spécifique à chaque axe
    - Une composante aléatoire (micro-fluctuations)

    Résultat : les axes ont des niveaux DIFFÉRENTS et les valeurs
    CHANGENT entre les appels (vrai temps réel).
    """
    now    = datetime.now()
    hour   = now.hour
    minute = now.minute

    axes = {}
    for axis_name, meta in AXES_METADATA.items():
        free_flow  = AXIS_FREE_FLOW[axis_name]
        congestion = compute_congestion(axis_name, hour, minute)
        speed      = congestion_to_speed(congestion, free_flow)

        # Estimation du nombre de véhicules (proportionnel à la congestion)
        base_vehicles = {"ndokoti": 800, "bonaberi": 500, "bassa": 650,
                         "akwa": 750, "makepe": 400, "logbessou": 350}
        vehicle_count = int(base_vehicles.get(axis_name, 500) * (0.3 + 0.7 * congestion / 100))

        axes[axis_name] = {
            "label":         meta["label"],
            "zone":          meta["zone"],
            "congestion":    congestion,
            "speed_kmh":     speed,
            "vehicle_count": vehicle_count,
            "status":        get_status(congestion),
            "color":         get_color(congestion),
            "coords":        AXES_COORDS[axis_name],
        }

    return jsonify({
        "timestamp":    now.isoformat(),
        "current_hour": hour,
        "axes":         axes,
    })


@app.route("/api/chart")
def api_chart():
    """
    Données du graphique 24h (statiques — proviennent du pipeline ML).
    Ces données représentent la courbe typique d'une journée de semaine.
    """
    return jsonify(load_json("chart_data.json"))


@app.route("/api/predictions")
def api_predictions():
    """Prédictions ML pour les 3 prochaines heures."""
    return jsonify(load_json("predictions.json"))


@app.route("/api/vehicles")
def api_vehicles():
    """
    Positions des véhicules animés sur la carte.
    Appelé toutes les 2 secondes — génère des positions différentes à chaque fois.
    """
    now    = datetime.now()
    hour   = now.hour
    minute = now.minute

    vehicles = []

    for axis_name, meta in AXES_METADATA.items():
        coords = AXES_COORDS[axis_name]
        if len(coords) < 2:
            continue

        congestion = compute_congestion(axis_name, hour, minute)
        color      = get_color(congestion)
        speed_kmh  = congestion_to_speed(congestion, AXIS_FREE_FLOW[axis_name])

        # Nombre de véhicules proportionnel à la congestion
        n_vehicles = max(2, int(congestion / 10))

        for i in range(n_vehicles):
            # Position aléatoire sur l'axe — change à chaque appel
            progress = random.random()
            total_segments = len(coords) - 1
            seg_idx = int(progress * total_segments)
            seg_idx = min(seg_idx, total_segments - 1)

            p1, p2 = coords[seg_idx], coords[seg_idx + 1]
            local_t = (progress * total_segments) - seg_idx

            lat = p1[0] + local_t * (p2[0] - p1[0]) + random.gauss(0, 0.0001)
            lon = p1[1] + local_t * (p2[1] - p1[1]) + random.gauss(0, 0.0001)

            vehicles.append({
                "id":    f"veh_{axis_name}_{i}",
                "axis":  axis_name,
                "label": meta["label"],
                "lat":   round(lat, 6),
                "lon":   round(lon, 6),
                "speed": speed_kmh,
                "color": color,
            })

    return jsonify({"vehicles": vehicles, "count": len(vehicles)})


@app.route("/api/stats")
def api_stats():
    """Statistiques globales calculées dynamiquement."""
    now    = datetime.now()
    hour   = now.hour
    minute = now.minute

    all_axes = {}
    for axis_name, meta in AXES_METADATA.items():
        cong  = compute_congestion(axis_name, hour, minute)
        speed = congestion_to_speed(cong, AXIS_FREE_FLOW[axis_name])
        all_axes[axis_name] = {
            "label":      meta["label"],
            "congestion": cong,
            "speed_kmh":  speed,
            "status":     get_status(cong),
        }

    congestion_values = [a["congestion"] for a in all_axes.values()]
    speed_values      = [a["speed_kmh"]  for a in all_axes.values()]

    avg_congestion = sum(congestion_values) / len(congestion_values)
    avg_speed      = sum(speed_values)      / len(speed_values)

    most_congested_key = max(all_axes, key=lambda k: all_axes[k]["congestion"])
    most_fluid_key     = min(all_axes, key=lambda k: all_axes[k]["congestion"])

    saturated = [a["label"] for a in all_axes.values() if a["status"] == "SATURÉ"]
    alert = None
    if saturated:
        alert = f"⚠ Axes saturés : {', '.join(saturated)} — Ralentissements importants"

    return jsonify({
        "avg_congestion":  round(avg_congestion, 1),
        "avg_speed_kmh":   round(avg_speed, 1),
        "axes_count":      len(all_axes),
        "most_congested": {
            "name":       most_congested_key,
            "label":      all_axes[most_congested_key]["label"],
            "congestion": all_axes[most_congested_key]["congestion"],
        },
        "most_fluid": {
            "name":       most_fluid_key,
            "label":      all_axes[most_fluid_key]["label"],
            "congestion": all_axes[most_fluid_key]["congestion"],
        },
        "alert":     alert,
        "timestamp": now.isoformat(),
    })


# ==============================================================================
# GESTION DES ERREURS
# ==============================================================================

@app.errorhandler(503)
def service_unavailable(e):
    return jsonify({
        "error":    str(e),
        "solution": "Lancez d'abord les deux scripts de préparation :",
        "step1":    "python backend/generate_data.py",
        "step2":    "python backend/process_bigdata.py"
    }), 503


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint introuvable", "message": str(e)}), 404


# ==============================================================================
# POINT D'ENTRÉE PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  DOUALAFLOW - Serveur API Flask (Mode Temps Reel)")
    print("=" * 65)
    print(f"  Frontend : {FRONTEND_DIR}")
    print(f"  Donnees  : {PROCESSED_DIR}")
    print()
    print("  [OK] Congestion calculee DYNAMIQUEMENT a chaque appel")
    print("  [OK] Chaque axe a un profil horaire UNIQUE")
    print("  [OK] Les axes ne saturent PAS tous au meme moment")
    print()

    state_path = os.path.join(PROCESSED_DIR, "current_state.json")
    chart_path = os.path.join(PROCESSED_DIR, "chart_data.json")
    if not os.path.exists(chart_path):
        print("  [!!] ATTENTION : Les donnees graphique ne sont pas generees.")
        print("  Les endpoints /api/chart et /api/predictions retourneront 503.")
        print("  Lancez : python backend/generate_data.py")
        print("           python backend/process_bigdata.py")
    else:
        print("  [OK] Donnees graphique disponibles")

    print()
    print("  >> Ouvrez votre navigateur : http://localhost:5000")
    print("=" * 65 + "\n")

    app.run(debug=True, host="0.0.0.0", port=5000)
