"""
==============================================================================
DOUALAFLOW — Étape 2 : Traitement, Agrégation & Modèle de Prédiction ML
==============================================================================

RÔLE DE CE FICHIER :
    Lire les données brutes (au format Parquet), les analyser, calculer
    les indicateurs de trafic, entraîner un modèle de Machine Learning pour
    prédire la congestion future, et produire les fichiers de sortie prêts
    à être consommés par le serveur Flask.

    En Big Data réel :
        Ce script serait un job Apache Spark ou un pipeline Flink qui
        traiterait des téraoctets de données en parallèle sur un cluster.
        Ici, Pandas fait le travail localement, mais la LOGIQUE est identique.

SORTIES :
    - data/processed/aggregated_by_hour.parquet : Congestion par heure et axe
    - data/processed/current_state.json         : État actuel de chaque axe
    - data/processed/predictions.json           : Prédictions ML +1h, +2h, +3h
    - data/processed/model.joblib               : Modèle ML sauvegardé (réutilisable)

COMMENT LANCER :
    python backend/process_bigdata.py
==============================================================================
"""

import os
import json
import joblib
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Modèle de Machine Learning (Apprentissage Supervisé)
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score

warnings.filterwarnings("ignore")

# ==============================================================================
# CHEMINS DES FICHIERS (relatifs à la racine du projet)
# ==============================================================================
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_PARQUET   = os.path.join(BASE_DIR, "data", "raw", "traffic_parquet")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
MODEL_PATH    = os.path.join(PROCESSED_DIR, "model.joblib")
ENCODER_PATH  = os.path.join(PROCESSED_DIR, "label_encoder.joblib")

# Reconfiguration des axes (mêmes infos que generate_data, utilisées pour la réponse JSON)
AXES_METADATA = {
    "ndokoti":   {"label": "Ndokoti",   "zone": "Carrefour Central",        "lat": 4.0550, "lon": 9.7100},
    "bonaberi":  {"label": "Bonabéri",  "zone": "Pont sur le Wouri",        "lat": 4.0695, "lon": 9.6940},
    "bassa":     {"label": "Bassa",     "zone": "Zone Industrielle",         "lat": 4.0265, "lon": 9.7450},
    "akwa":      {"label": "Akwa",      "zone": "Centre-Ville & Affaires",   "lat": 4.0515, "lon": 9.7048},
    "makepe":    {"label": "Makepe",    "zone": "Zone Résidentielle Nord",   "lat": 4.0838, "lon": 9.7265},
    "logbessou": {"label": "Logbessou", "zone": "Périphérie Nord",           "lat": 4.0975, "lon": 9.7198},
}

# Coordonnées GPS complètes pour l'animation de la carte
AXES_COORDS = {
    "ndokoti":   [[4.0511,9.7085],[4.0530,9.7095],[4.0550,9.7100],[4.0570,9.7110],[4.0590,9.7105],[4.0610,9.7095]],
    "bonaberi":  [[4.0731,9.6821],[4.0720,9.6850],[4.0710,9.6880],[4.0695,9.6910],[4.0680,9.6940],[4.0660,9.6960]],
    "bassa":     [[4.0234,9.7412],[4.0250,9.7430],[4.0265,9.7450],[4.0280,9.7465],[4.0295,9.7480],[4.0310,9.7490]],
    "akwa":      [[4.0487,9.7012],[4.0500,9.7030],[4.0515,9.7048],[4.0528,9.7063],[4.0540,9.7078],[4.0555,9.7090]],
    "makepe":    [[4.0812,9.7234],[4.0825,9.7250],[4.0838,9.7265],[4.0850,9.7280],[4.0862,9.7295],[4.0875,9.7305]],
    "logbessou": [[4.1021,9.7156],[4.1005,9.7170],[4.0990,9.7185],[4.0975,9.7198],[4.0960,9.7212],[4.0945,9.7225]],
}


# ==============================================================================
# ÉTAPE 1 : LECTURE DES DONNÉES PARQUET (AVEC OPTIMISATION)
# ==============================================================================

def load_data() -> pd.DataFrame:
    """
    Charge les données brutes depuis le Data Lake Parquet local.

    Avantage du format Parquet partitionné :
        Si on demande seulement les données de 'ndokoti', Pandas ne lit
        que le sous-dossier axis=ndokoti/, pas les 6 autres axes.
        C'est le principe de "predicate pushdown" en Big Data.

    Returns:
        pd.DataFrame: Toutes les données de trafic chargées en mémoire
    """
    print("\n  [1/5] Lecture des données Parquet (Data Lake local)...")

    if not os.path.exists(RAW_PARQUET):
        raise FileNotFoundError(
            f"Données introuvables : {RAW_PARQUET}\n"
            "Lancez d'abord : python backend/generate_data.py"
        )

    # Lecture optimisée : on ne charge que les colonnes nécessaires
    # (économie de mémoire — concept important en Big Data)
    columns_needed = [
        "timestamp", "date", "hour", "day_of_week", "day_name",
        "axis", "axis_label", "speed_kmh", "free_flow_speed",
        "congestion_index", "congestion_level"
    ]

    df = pd.read_parquet(
        RAW_PARQUET,
        engine="pyarrow",
        columns=columns_needed  # "Column Pruning" : technique Big Data
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"]      = pd.to_datetime(df["date"])

    print(f"    → {len(df):,} enregistrements chargés depuis {RAW_PARQUET}")
    print(f"    → Mémoire utilisée : {df.memory_usage(deep=True).sum() / (1024*1024):.1f} Mo")
    return df


# ==============================================================================
# ÉTAPE 2 : AGRÉGATION DES DONNÉES (MOTEUR ANALYTIQUE)
# ==============================================================================

def aggregate_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège les données brutes pour calculer les métriques de trafic
    par axe, par heure et par jour de la semaine.

    Cette agrégation transforme ~500 000 lignes de GPS logs en ~1 008 lignes
    de synthèse analytique exploitables. C'est le travail typique d'un
    "job de traitement" (batch processing) en Big Data.

    Args:
        df (pd.DataFrame): Données brutes complètes

    Returns:
        pd.DataFrame: Données agrégées (une ligne par axe/heure/jour)
    """
    print("\n  [2/5] Agrégation des données (calcul des métriques)...")

    agg = df.groupby(["axis", "axis_label", "hour", "day_of_week", "day_name"]).agg(
        # Congestion : moyenne de l'indice de congestion calculé
        avg_congestion   = ("congestion_index",  "mean"),
        max_congestion   = ("congestion_index",  "max"),
        # Vitesse : moyenne et percentile 25 (les plus lents)
        avg_speed        = ("speed_kmh",          "mean"),
        p25_speed        = ("speed_kmh",          lambda x: x.quantile(0.25)),
        # Volume de trafic (nombre d'enregistrements = proxy pour le nombre de véhicules)
        vehicle_count    = ("axis",               "count"),
    ).reset_index()

    # Arrondir les valeurs décimales
    agg["avg_congestion"] = agg["avg_congestion"].round(1)
    agg["max_congestion"] = agg["max_congestion"].round(1)
    agg["avg_speed"]      = agg["avg_speed"].round(1)

    print(f"    → {len(agg):,} agrégats produits ({len(agg.columns)} métriques par agrégat)")
    return agg


# ==============================================================================
# ÉTAPE 3 : ENTRAÎNEMENT DU MODÈLE DE MACHINE LEARNING
# ==============================================================================

def train_model(agg: pd.DataFrame) -> tuple:
    """
    Entraîne un modèle Random Forest pour prédire la congestion.

    Le Random Forest est idéal ici car :
    - Il capture les effets non-linéaires (ex: l'heure de pointe soir
      est bien pire un vendredi qu'un mardi)
    - Il est rapide à entraîner sur un PC normal
    - Il est facilement interprétable pour une présentation de cours

    Entrées (features) du modèle :
        - L'axe routier (encodé numériquement)
        - L'heure de la journée (0-23)
        - Le jour de la semaine (0-6)
        - La congestion de l'heure précédente (lag feature)

    Sortie (target) :
        - avg_congestion : l'indice de congestion en %

    Args:
        agg (pd.DataFrame): Données agrégées par heure et axe

    Returns:
        tuple: (model_entraîné, label_encoder_des_axes)
    """
    print("\n  [3/5] Entraînement du modèle de prédiction (Random Forest)...")

    # --- Encodage de la variable catégorielle 'axis' ---
    # Le modèle ML ne peut pas traiter des chaînes de caractères,
    # on convertit : ndokoti → 0, bonaberi → 1, bassa → 2, etc.
    le = LabelEncoder()
    agg["axis_encoded"] = le.fit_transform(agg["axis"])

    # --- Feature Engineering : Lag Feature ---
    # La congestion à l'heure H est fortement corrélée à la congestion à H-1.
    # C'est une "feature temporelle" (lag=1) que le modèle utilisera.
    agg = agg.sort_values(["axis", "day_of_week", "hour"])
    agg["lag_congestion"] = agg.groupby(["axis", "day_of_week"])["avg_congestion"].shift(1)
    agg["lag_congestion"] = agg["lag_congestion"].fillna(agg["avg_congestion"].mean())

    # --- Définition des features et de la cible ---
    features = ["axis_encoded", "hour", "day_of_week", "lag_congestion"]
    target   = "avg_congestion"

    X = agg[features]
    y = agg[target]

    # --- Split : 80% entraînement, 20% test ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # --- Entraînement du modèle Random Forest ---
    model = RandomForestRegressor(
        n_estimators=100,    # 100 arbres de décision
        max_depth=10,        # Profondeur maximale (évite le sur-apprentissage)
        min_samples_split=5,
        random_state=42,
        n_jobs=-1            # Utiliser tous les cœurs du processeur
    )
    model.fit(X_train, y_train)

    # --- Évaluation du modèle ---
    y_pred = model.predict(X_test)
    mae    = mean_absolute_error(y_test, y_pred)
    r2     = r2_score(y_test, y_pred)

    print(f"    → Modèle entraîné sur {len(X_train):,} exemples")
    print(f"    → MAE (Erreur moyenne absolue) : {mae:.2f}%")
    print(f"    → R² Score (précision)          : {r2:.3f} (1.0 = parfait)")

    # --- Importance des features (interprétabilité pour la soutenance) ---
    importances = dict(zip(features, model.feature_importances_))
    print(f"    → Importance des variables :")
    for feat, imp in sorted(importances.items(), key=lambda x: -x[1]):
        bar = "█" * int(imp * 30)
        print(f"       {feat:<20} {bar}  {imp:.1%}")

    return model, le, agg


# ==============================================================================
# ÉTAPE 4 : GÉNÉRATION DES FICHIERS DE SORTIE POUR L'API
# ==============================================================================

def generate_current_state(agg: pd.DataFrame) -> dict:
    """
    Génère le fichier JSON "état actuel" du trafic.

    Ce fichier représente la situation à l'heure actuelle.
    Pour chaque axe, on prend la moyenne des jours de semaine à cette heure,
    ce qui donne une valeur représentative et réaliste.

    Args:
        agg (pd.DataFrame): Données agrégées

    Returns:
        dict: État actuel de chaque axe, prêt à être envoyé en JSON
    """
    # Heure actuelle à Douala (UTC+1)
    now   = datetime.now()
    hour  = now.hour
    dow   = now.weekday()

    # Agréger par axe à cette heure — une seule valeur par axe
    # On préfère les jours de semaine similaires, sinon on fait la moyenne de tous les jours
    mask_exact = (agg["hour"] == hour) & (agg["day_of_week"] == dow)
    if agg[mask_exact].shape[0] > 0:
        current_source = agg[mask_exact]
    else:
        # Fallback : moyenne de tous les jours disponibles pour cette heure
        current_source = agg[agg["hour"] == hour]

    # Grouper par axe pour avoir UNE seule ligne par axe
    current = current_source.groupby(["axis", "axis_label"]).agg(
        avg_congestion = ("avg_congestion", "mean"),
        avg_speed      = ("avg_speed",      "mean"),
        vehicle_count  = ("vehicle_count",  "mean"),
    ).reset_index()

    state = {"timestamp": now.isoformat(), "current_hour": hour, "axes": {}}

    for _, row in current.iterrows():
        axis_name = row["axis"]
        meta = AXES_METADATA.get(axis_name, {})
        congestion = float(row["avg_congestion"])
        speed      = float(row["avg_speed"])

        state["axes"][axis_name] = {
            "label":          row["axis_label"],
            "zone":           meta.get("zone", ""),
            "congestion":     round(congestion, 1),
            "speed_kmh":      round(speed, 1),
            "vehicle_count":  int(row["vehicle_count"]),
            "status":        (
                "SATURÉ"  if congestion > 70 else
                "RALENTI" if congestion > 40 else
                "FLUIDE"
            ),
            "color": (
                "#ef4444" if congestion > 70 else
                "#f97316" if congestion > 55 else
                "#eab308" if congestion > 40 else
                "#22c55e"
            ),
            "coords":         AXES_COORDS.get(axis_name, []),
            "center_lat":     meta.get("lat", 0),
            "center_lon":     meta.get("lon", 0),
        }

    return state


def generate_hourly_chart(agg: pd.DataFrame) -> dict:
    """
    Génère les données pour le graphique d'évolution de la congestion sur 24h.
    Données moyennées sur tous les jours de semaine.

    Args:
        agg (pd.DataFrame): Données agrégées

    Returns:
        dict: Données pour le graphique, par heure et par axe
    """
    # Moyenner sur tous les jours de semaine (lundi-vendredi)
    weekday_agg = agg[agg["day_of_week"] < 5].groupby(["axis", "axis_label", "hour"]).agg(
        avg_congestion = ("avg_congestion", "mean"),
        avg_speed      = ("avg_speed",      "mean"),
    ).reset_index()

    chart_data = {"labels": list(range(24)), "datasets": {}}

    for axis_name, meta in AXES_METADATA.items():
        axis_data = weekday_agg[weekday_agg["axis"] == axis_name]
        if not axis_data.empty:
            # S'assurer qu'on a bien 24 valeurs (une par heure)
            full_hours = pd.DataFrame({"hour": range(24)})
            merged = full_hours.merge(axis_data, on="hour", how="left").fillna(0)
            chart_data["datasets"][axis_name] = {
                "label":      meta["label"],
                "congestion": [round(float(v), 1) for v in merged["avg_congestion"]],
                "speed":      [round(float(v), 1) for v in merged["avg_speed"]],
            }

    return chart_data


def generate_predictions(model, le, agg: pd.DataFrame) -> dict:
    """
    Utilise le modèle ML entraîné pour prédire la congestion
    pour les 3 prochaines heures.

    Args:
        model: Modèle Random Forest entraîné
        le: LabelEncoder des noms d'axes
        agg (pd.DataFrame): Données agrégées

    Returns:
        dict: Prédictions JSON par axe et heure future
    """
    now  = datetime.now()
    dow  = now.weekday()
    predictions = {"generated_at": now.isoformat(), "horizons": {}}

    for h_offset in [1, 2, 3]:
        future_hour = (now.hour + h_offset) % 24
        future_time = (now + timedelta(hours=h_offset)).strftime("%H:%M")
        predictions["horizons"][f"+{h_offset}h"] = {
            "label": f"Dans {h_offset}h ({future_time})",
            "axes": {}
        }

        for axis_name in AXES_METADATA.keys():
            # Trouver la congestion actuelle de cet axe (lag feature)
            current_mask = (
                (agg["axis"] == axis_name) &
                (agg["hour"] == now.hour) &
                (agg["day_of_week"] == dow)
            )
            if agg[current_mask].empty:
                lag_cong = 50.0
            else:
                lag_cong = float(agg[current_mask]["avg_congestion"].mean())

            # Préparer le vecteur de features pour la prédiction
            try:
                axis_encoded = le.transform([axis_name])[0]
            except ValueError:
                axis_encoded = 0

            X_pred = np.array([[axis_encoded, future_hour, dow, lag_cong]])
            predicted_cong = float(np.clip(model.predict(X_pred)[0], 0, 100))
            predicted_speed = max(5, AXES_METADATA[axis_name].get("speed", 40) * (1 - predicted_cong / 100))

            predictions["horizons"][f"+{h_offset}h"]["axes"][axis_name] = {
                "label":      AXES_METADATA[axis_name]["label"],
                "congestion": round(predicted_cong, 1),
                "status": (
                    "SATURÉ"  if predicted_cong > 70 else
                    "RALENTI" if predicted_cong > 40 else
                    "FLUIDE"
                ),
                "color": (
                    "#ef4444" if predicted_cong > 70 else
                    "#f97316" if predicted_cong > 55 else
                    "#eab308" if predicted_cong > 40 else
                    "#22c55e"
                ),
            }

    return predictions


def save_outputs(model, le, agg, current_state, chart_data, predictions) -> None:
    """
    Sauvegarde tous les artefacts produits par le pipeline de traitement.

    Args:
        model: Modèle ML
        le: LabelEncoder
        agg (pd.DataFrame): Données agrégées
        current_state (dict): État actuel
        chart_data (dict): Données graphique
        predictions (dict): Prédictions ML
    """
    print("\n  [4/5] Sauvegarde des fichiers de sortie...")
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # --- Données agrégées en Parquet (couche analytique du Data Lake) ---
    agg_path = os.path.join(PROCESSED_DIR, "aggregated_by_hour.parquet")
    agg.drop(columns=["lag_congestion", "axis_encoded"], errors="ignore").to_parquet(
        agg_path, engine="pyarrow", compression="snappy", index=False
    )
    print(f"    → {agg_path}")

    # --- État actuel en JSON ---
    state_path = os.path.join(PROCESSED_DIR, "current_state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(current_state, f, ensure_ascii=False, indent=2)
    print(f"    → {state_path}")

    # --- Données du graphique en JSON ---
    chart_path = os.path.join(PROCESSED_DIR, "chart_data.json")
    with open(chart_path, "w", encoding="utf-8") as f:
        json.dump(chart_data, f, ensure_ascii=False, indent=2)
    print(f"    → {chart_path}")

    # --- Prédictions ML en JSON ---
    pred_path = os.path.join(PROCESSED_DIR, "predictions.json")
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)
    print(f"    → {pred_path}")

    # --- Modèle ML sérialisé (pour rechargement rapide) ---
    joblib.dump(model, MODEL_PATH)
    joblib.dump(le,    ENCODER_PATH)
    print(f"    → {MODEL_PATH}")
    print(f"    → {ENCODER_PATH}")


# ==============================================================================
# POINT D'ENTRÉE PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    print("=" * 65)
    print("  DOUALAFLOW — Pipeline de Traitement Big Data")
    print("=" * 65)

    # 1. Charger les données depuis le Data Lake Parquet
    df = load_data()

    # 2. Agréger pour obtenir les métriques par heure et par axe
    agg = aggregate_data(df)

    # 3. Entraîner le modèle de prédiction
    model, le, agg = train_model(agg)

    # 4. Générer les fichiers de sortie pour l'API Flask
    print("\n  [4/5] Génération des fichiers de sortie pour l'API...")
    current_state = generate_current_state(agg)
    chart_data    = generate_hourly_chart(agg)
    predictions   = generate_predictions(model, le, agg)

    # 5. Sauvegarder tout
    save_outputs(model, le, agg, current_state, chart_data, predictions)

    # 6. Résumé final
    print("\n" + "=" * 65)
    print("  [5/5] PIPELINE TERMINÉ — RÉSUMÉ")
    print("=" * 65)
    print(f"  Axes analysés   : {list(AXES_METADATA.keys())}")
    now = datetime.now()
    print(f"  Heure courante  : {now.strftime('%H:%M')} (Jour {now.weekday()}/6)")
    print(f"  État actuel     :")
    for axis, data in current_state["axes"].items():
        print(f"    {data['label']:<12} : {data['congestion']:5.1f}%  {data['status']}")
    print(f"\n  ✓ Tous les fichiers sont prêts dans data/processed/")
    print(f"  Prochaine étape : python backend/app.py")
    print("=" * 65 + "\n")
