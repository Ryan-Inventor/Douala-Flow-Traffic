"""
==============================================================================
DOUALAFLOW — Étape 1 : Génération des Données Brutes (Simulateur GPS)
==============================================================================

RÔLE DE CE FICHIER :
    Simuler le flux de données GPS que produiraient de vrais capteurs IoT
    (caméras, boucles inductives, boîtiers GPS embarqués) installés sur les
    axes routiers de Douala.

    En Big Data réel :
        Ce script serait remplacé par un producteur Apache Kafka ou
        un flux AWS Kinesis ingérant des milliers d'événements par seconde.

SORTIE :
    - data/raw/raw_traffic.csv  : fichier CSV brut (intermédiaire lisible)
    - data/raw/raw_traffic.parquet : fichier Parquet (format Big Data optimisé)

COMMENT LANCER :
    python backend/generate_data.py
==============================================================================
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ==============================================================================
# CONFIGURATION DES AXES ROUTIERS DE DOUALA
# ==============================================================================
# Chaque axe est défini avec :
#   - name          : Identifiant unique de l'axe
#   - label         : Nom lisible pour l'affichage
#   - zone          : Description de la zone géographique
#   - speed_limit   : Vitesse limite légale (km/h) — vitesse maximale théorique
#   - free_flow     : Vitesse de circulation fluide typique (km/h)
#   - coords        : Liste de points [lat, lon] formant le tracé exact de la route
#                     (coordonnées GPS réelles approximant les routes de Douala)
#   - base_volume   : Nombre moyen de véhicules/heure en conditions normales
#   - peak_factor   : Multiplicateur de volume aux heures de pointe

AXES = [
    {
        "name": "ndokoti",
        "label": "Ndokoti",
        "zone": "Carrefour Central - Zone très dense",
        "speed_limit": 50,
        "free_flow": 40,
        "coords": [
            [4.0511, 9.7085], [4.0530, 9.7095], [4.0550, 9.7100],
            [4.0570, 9.7110], [4.0590, 9.7105], [4.0610, 9.7095]
        ],
        "base_volume": 800,   # véhicules/heure
        "peak_factor": 3.5    # x3.5 aux heures de pointe
    },
    {
        "name": "bonaberi",
        "label": "Bonabéri",
        "zone": "Pont sur le Wouri - Axe principal inter-rives",
        "speed_limit": 60,
        "free_flow": 55,
        "coords": [
            [4.0731, 9.6821], [4.0720, 9.6850], [4.0710, 9.6880],
            [4.0695, 9.6910], [4.0680, 9.6940], [4.0660, 9.6960]
        ],
        "base_volume": 500,
        "peak_factor": 2.8
    },
    {
        "name": "bassa",
        "label": "Bassa",
        "zone": "Zone Industrielle - Trafic lourd",
        "speed_limit": 50,
        "free_flow": 38,
        "coords": [
            [4.0234, 9.7412], [4.0250, 9.7430], [4.0265, 9.7450],
            [4.0280, 9.7465], [4.0295, 9.7480], [4.0310, 9.7490]
        ],
        "base_volume": 650,
        "peak_factor": 3.2
    },
    {
        "name": "akwa",
        "label": "Akwa",
        "zone": "Centre-Ville & Affaires",
        "speed_limit": 40,
        "free_flow": 30,
        "coords": [
            [4.0487, 9.7012], [4.0500, 9.7030], [4.0515, 9.7048],
            [4.0528, 9.7063], [4.0540, 9.7078], [4.0555, 9.7090]
        ],
        "base_volume": 750,
        "peak_factor": 3.0
    },
    {
        "name": "makepe",
        "label": "Makepe",
        "zone": "Zone Résidentielle Nord",
        "speed_limit": 50,
        "free_flow": 45,
        "coords": [
            [4.0812, 9.7234], [4.0825, 9.7250], [4.0838, 9.7265],
            [4.0850, 9.7280], [4.0862, 9.7295], [4.0875, 9.7305]
        ],
        "base_volume": 400,
        "peak_factor": 2.5
    },
    {
        "name": "logbessou",
        "label": "Logbessou",
        "zone": "Périphérie Nord - Accès autoroute",
        "speed_limit": 70,
        "free_flow": 65,
        "coords": [
            [4.1021, 9.7156], [4.1005, 9.7170], [4.0990, 9.7185],
            [4.0975, 9.7198], [4.0960, 9.7212], [4.0945, 9.7225]
        ],
        "base_volume": 350,
        "peak_factor": 2.0
    }
]

# ==============================================================================
# CONFIGURATION DE LA SIMULATION TEMPORELLE
# ==============================================================================

# --- Profil de la journée type à Douala ---
# Heure : Multiplicateur de congestion (1.0 = normal, >1.0 = embouteillages)
# Ces valeurs ont été choisies pour refléter la réalité camerounaise :
# - Matin 7h-9h   : Heure de pointe principale (école, bureau)
# - Midi 12h-14h  : Légère hausse (pauses déjeuner)
# - Soir 17h-20h  : Heure de pointe maximale (retours, marchés)
HOURLY_CONGESTION_PROFILE = {
    0: 0.1, 1: 0.05, 2: 0.05, 3: 0.05, 4: 0.1,
    5: 0.2, 6: 0.5,
    7: 0.85,   # <- Début heure de pointe matin
    8: 1.0,    # <- Pic absolu matin
    9: 0.75,
    10: 0.55, 11: 0.5,
    12: 0.65,  # <- Pic midi
    13: 0.6, 14: 0.5,
    15: 0.55, 16: 0.65,
    17: 0.9,   # <- Début heure de pointe soir
    18: 1.0,   # <- Pic absolu soir
    19: 0.85,
    20: 0.6, 21: 0.4, 22: 0.25, 23: 0.15
}

# Nombre de jours de données à simuler
SIMULATION_DAYS = 7

# Nombre total de lignes cible (~500 000 lignes)
# Ce volume justifie l'utilisation du format Parquet face à un simple CSV.
TARGET_ROWS = 500_000


def get_congestion_factor(hour: int, day_of_week: int) -> float:
    """
    Calcule le facteur de congestion pour une heure et un jour donnés.

    Args:
        hour (int): Heure de la journée (0-23)
        day_of_week (int): Jour de la semaine (0=Lundi, 6=Dimanche)

    Returns:
        float: Facteur de congestion entre 0 et 1
    """
    base = HOURLY_CONGESTION_PROFILE[hour]

    # Le weekend (samedi=5, dimanche=6) a moins de trafic de bureau,
    # mais plus de trafic de marché (samedi surtout).
    if day_of_week == 6:   # Dimanche : très calme
        return base * 0.4
    elif day_of_week == 5: # Samedi : marchés actifs (pic spécial 9h-13h)
        if 9 <= hour <= 13:
            return min(base * 1.1, 1.0)
        return base * 0.7
    else:                  # Semaine : profil normal
        # Légère variation aléatoire inter-journalière (+/- 10%)
        noise = np.random.uniform(0.9, 1.1)
        return min(base * noise, 1.0)


def speed_from_congestion(free_flow_speed: float, congestion_factor: float) -> float:
    """
    Calcule la vitesse réelle d'un véhicule en fonction de la congestion.

    Modèle simplifié inspiré du modèle BPR (Bureau of Public Roads) :
    Plus la congestion est élevée, plus la vitesse chute de façon non-linéaire.

    Args:
        free_flow_speed (float): Vitesse en circulation fluide (km/h)
        congestion_factor (float): Niveau de congestion entre 0 et 1

    Returns:
        float: Vitesse observée en km/h
    """
    # Formule : vitesse = vitesse_fluide * (1 - congestion)^2
    # À 0% de congestion : vitesse = free_flow (fluide)
    # À 100% de congestion : vitesse → 0 (arrêt complet)
    ratio = (1 - congestion_factor) ** 2
    speed = free_flow_speed * ratio
    # Bruit gaussien pour simuler la variabilité naturelle des conducteurs
    noise = np.random.normal(0, 2)
    return max(5, speed + noise)  # Minimum 5 km/h (même en bouchon, ça avance)


def generate_gps_point_on_axis(coords: list) -> tuple:
    """
    Génère un point GPS aléatoire sur un axe routier.

    Sélectionne un segment de la route et place le véhicule
    quelque part sur ce segment.

    Args:
        coords (list): Liste de points [lat, lon] définissant l'axe

    Returns:
        tuple: (latitude, longitude) du véhicule
    """
    # Choisir un segment aléatoire de la route
    idx = np.random.randint(0, len(coords) - 1)
    p1 = coords[idx]
    p2 = coords[idx + 1]

    # Interpoler un point aléatoire sur ce segment
    t = np.random.uniform(0, 1)
    lat = p1[0] + t * (p2[0] - p1[0])
    lon = p1[1] + t * (p2[1] - p1[1])

    # Ajouter un très léger bruit (~0-5m) pour simuler la réalité GPS
    lat += np.random.normal(0, 0.00005)
    lon += np.random.normal(0, 0.00005)

    return round(lat, 6), round(lon, 6)


def generate_dataset() -> pd.DataFrame:
    """
    Génère le dataset complet de surveillance du trafic.

    Produit un DataFrame simulant les logs GPS de véhicules circulant
    sur les axes de Douala pendant une semaine.

    Returns:
        pd.DataFrame: Dataset complet avec ~500 000 lignes
    """
    print("=" * 65)
    print("  DOUALAFLOW — Génération des Données de Trafic")
    print("=" * 65)

    all_records = []

    # Date de départ : il y a SIMULATION_DAYS jours
    start_date = datetime.now() - timedelta(days=SIMULATION_DAYS)

    # Calcul du nombre de véhicules à générer par heure et par axe
    # pour atteindre TARGET_ROWS lignes au total
    rows_per_hour_per_axis = TARGET_ROWS // (24 * SIMULATION_DAYS * len(AXES))

    vehicle_counter = 0

    for day_offset in range(SIMULATION_DAYS):
        current_date = start_date + timedelta(days=day_offset)
        day_name = current_date.strftime("%A")
        day_of_week = current_date.weekday()

        print(f"\n  Jour {day_offset + 1}/{SIMULATION_DAYS} — {day_name} {current_date.strftime('%d/%m/%Y')}")

        for hour in range(24):
            congestion_factor = get_congestion_factor(hour, day_of_week)

            for axe in AXES:
                # Nombre de véhicules cette heure : proportionnel au facteur de congestion
                n_vehicles = max(
                    10,
                    int(rows_per_hour_per_axis * (0.3 + 0.7 * congestion_factor))
                )

                for _ in range(n_vehicles):
                    # Minuterie aléatoire dans l'heure
                    minute = np.random.randint(0, 60)
                    second = np.random.randint(0, 60)
                    timestamp = current_date.replace(
                        hour=hour, minute=minute, second=second, microsecond=0
                    )

                    # Position GPS sur l'axe
                    lat, lon = generate_gps_point_on_axis(axe["coords"])

                    # Vitesse calculée en fonction de la congestion
                    speed = speed_from_congestion(axe["free_flow"], congestion_factor)

                    # Indice de congestion normalisé [0, 100]
                    # Formule : si la vitesse est moitié de la vitesse libre → 50% de congestion
                    congestion_index = round(
                        max(0, min(100, (1 - speed / axe["free_flow"]) * 100 * 1.5)), 1
                    )

                    # Identifiant unique du véhicule (simule une plaque immatriculée)
                    vehicle_counter += 1
                    vehicle_id = f"CMR-{vehicle_counter:07d}"

                    all_records.append({
                        "timestamp":        timestamp,
                        "date":             current_date.date(),
                        "hour":             hour,
                        "day_of_week":      day_of_week,
                        "day_name":         day_name,
                        "vehicle_id":       vehicle_id,
                        "axis":             axe["name"],
                        "axis_label":       axe["label"],
                        "zone":             axe["zone"],
                        "latitude":         lat,
                        "longitude":        lon,
                        "speed_kmh":        round(speed, 1),
                        "free_flow_speed":  axe["free_flow"],
                        "speed_limit":      axe["speed_limit"],
                        "congestion_index": congestion_index,
                        "congestion_level": (
                            "SATURÉ"  if congestion_index > 70 else
                            "RALENTI" if congestion_index > 40 else
                            "FLUIDE"
                        )
                    })

        print(f"    → {len(all_records):,} enregistrements générés jusqu'ici")

    df = pd.DataFrame(all_records)
    print(f"\n  Total final : {len(df):,} enregistrements générés")
    return df


def save_data(df: pd.DataFrame) -> None:
    """
    Sauvegarde les données en deux formats :
    1. CSV       : Format lisible par l'humain (pour inspection)
    2. Parquet   : Format Big Data colonnaire, compressé et partitionné

    Args:
        df (pd.DataFrame): Le DataFrame complet à sauvegarder
    """
    # --- Créer les dossiers si nécessaires ---
    raw_dir = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
    os.makedirs(raw_dir, exist_ok=True)

    # --- 1. Sauvegarde CSV (format lisible) ---
    csv_path = os.path.join(raw_dir, "raw_traffic.csv")
    df.to_csv(csv_path, index=False)
    csv_size_mb = os.path.getsize(csv_path) / (1024 * 1024)
    print(f"\n  [CSV]     Sauvegardé : {csv_path}")
    print(f"            Taille : {csv_size_mb:.1f} Mo")

    # --- 2. Sauvegarde Parquet (format Big Data) ---
    # Le partitionnement par 'date' et 'axis' est la technique clé du Big Data :
    # Quand Flask demande "quels sont les embouteillages du mercredi sur Ndokoti ?",
    # Pandas ne lit QUE le dossier date=XXXX/axis=ndokoti/ au lieu de tout le dataset.
    # Gain de performance : ~10x à ~100x vs lecture d'un CSV complet.
    parquet_dir = os.path.join(raw_dir, "traffic_parquet")
    df["date"] = df["date"].astype(str)  # Parquet exige un type string pour partitionner
    df.to_parquet(
        parquet_dir,
        partition_cols=["date", "axis"],  # Partitionnement : date / axe
        engine="pyarrow",                  # Moteur Apache Arrow
        compression="snappy",             # Compression rapide (standard Hadoop)
        index=False
    )
    # Calculer la taille totale du dossier Parquet
    parquet_size = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, files in os.walk(parquet_dir)
        for f in files
    ) / (1024 * 1024)
    print(f"\n  [PARQUET] Sauvegardé : {parquet_dir}")
    print(f"            Taille compressée : {parquet_size:.1f} Mo (vs {csv_size_mb:.1f} Mo CSV)")
    print(f"            Compression : {((1 - parquet_size/csv_size_mb)*100):.0f}% d'espace économisé")
    print(f"\n  Structure du Data Lake local :")
    print(f"    data/raw/traffic_parquet/")
    for date_dir in sorted(os.listdir(parquet_dir))[:3]:
        print(f"      {date_dir}/")
        axis_dir = os.path.join(parquet_dir, date_dir)
        if os.path.isdir(axis_dir):
            for axis_sub in sorted(os.listdir(axis_dir))[:2]:
                print(f"        {axis_sub}/")
    print(f"      ... (partitionné par date et par axe)")


if __name__ == "__main__":
    # Point d'entrée principal
    np.random.seed(42)  # Graine fixe pour la reproductibilité des résultats

    # 1. Générer le dataset
    df = generate_dataset()

    # 2. Afficher un aperçu des données générées
    print("\n" + "=" * 65)
    print("  APERÇU DES DONNÉES GÉNÉRÉES")
    print("=" * 65)
    print(df.head(3).to_string())
    print(f"\n  Colonnes : {list(df.columns)}")
    print(f"  Axes couverts : {df['axis_label'].unique().tolist()}")
    print(f"  Période : {df['date'].min()} → {df['date'].max()}")

    # 3. Sauvegarder en CSV et Parquet
    print("\n" + "=" * 65)
    print("  SAUVEGARDE DES DONNÉES")
    print("=" * 65)
    save_data(df)

    print("\n" + "=" * 65)
    print("  ✓ GÉNÉRATION TERMINÉE")
    print("  Prochaine étape : python backend/process_bigdata.py")
    print("=" * 65 + "\n")
