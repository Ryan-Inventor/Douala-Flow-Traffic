"""
==============================================================================
DOUALAFLOW — run.py : Script de Lancement en Une Commande
==============================================================================

RÔLE DE CE FICHIER :
    Script tout-en-un qui automatise les 3 étapes de démarrage du projet :
    1. Vérifier les dépendances Python (et les installer si manquantes)
    2. Générer les données et entraîner le modèle ML (si pas encore fait)
    3. Lancer le serveur Flask et ouvrir automatiquement le navigateur

UTILISATION :
    python run.py           → Lance le projet complet (données + serveur)
    python run.py --reset   → Régénère toutes les données depuis zéro
    python run.py --server  → Lance seulement le serveur (données déjà prêtes)
==============================================================================
"""

import os
import sys
import time
import argparse
import subprocess
import webbrowser
import importlib.util

# ==============================================================================
# CONFIGURATION
# ==============================================================================

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
DATA_DIR    = os.path.join(BASE_DIR, "data")
PROCESSED   = os.path.join(DATA_DIR, "processed", "current_state.json")
RAW_PARQUET = os.path.join(DATA_DIR, "raw", "traffic_parquet")

REQUIRED_PACKAGES = [
    "pandas", "pyarrow", "numpy",
    "sklearn", "joblib", "flask", "flask_cors"
]

SERVER_URL = "http://localhost:5000"
WAIT_BEFORE_BROWSER = 1.5  # Secondes avant d'ouvrir le navigateur


# ==============================================================================
# UTILITAIRES
# ==============================================================================

def banner(msg: str) -> None:
    """Affiche un message formaté dans la console."""
    print(f"\n{'=' * 65}")
    print(f"  {msg}")
    print(f"{'=' * 65}")


def check(msg: str) -> None:
    """Affiche une ligne de validation (✓)."""
    print(f"  ✓  {msg}")


def warn(msg: str) -> None:
    """Affiche un avertissement."""
    print(f"  ⚠  {msg}")


def error(msg: str) -> None:
    """Affiche une erreur et quitte."""
    print(f"\n  ✗  ERREUR : {msg}\n")
    sys.exit(1)


# ==============================================================================
# ÉTAPE 1 : Vérification des dépendances
# ==============================================================================

def ensure_dependencies() -> None:
    """
    Vérifie que toutes les librairies Python nécessaires sont installées.
    Si une librairie manque, tente de l'installer automatiquement via pip.
    """
    banner("Étape 1/3 — Vérification des dépendances Python")

    missing = []
    for pkg in REQUIRED_PACKAGES:
        spec = importlib.util.find_spec(pkg.replace("-", "_"))
        if spec is None:
            missing.append(pkg)
        else:
            check(f"{pkg} installé")

    if missing:
        warn(f"Librairies manquantes : {', '.join(missing)}")
        warn("Installation automatique en cours...")
        req_file = os.path.join(BASE_DIR, "requirements.txt")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "-q"],
            capture_output=False
        )
        if result.returncode != 0:
            error(
                f"Impossible d'installer les dépendances.\n"
                f"Lancez manuellement : pip install -r requirements.txt"
            )
        check("Toutes les dépendances sont installées.")
    else:
        check("Toutes les dépendances sont disponibles.")


# ==============================================================================
# ÉTAPE 2 : Génération des données et entraînement du modèle
# ==============================================================================

def ensure_data(force_reset: bool = False) -> None:
    """
    Génère les données Parquet et entraîne le modèle ML si nécessaire.

    Args:
        force_reset (bool): Si True, régénère tout même si les fichiers existent.
    """
    banner("Étape 2/3 — Préparation des données Big Data")

    # Vérifier si les fichiers existent déjà
    raw_exists  = os.path.exists(RAW_PARQUET)
    proc_exists = os.path.exists(PROCESSED)

    if raw_exists and proc_exists and not force_reset:
        check("Données Parquet déjà générées → Étape ignorée")
        check("Modèle ML déjà entraîné → Étape ignorée")
        print()
        print("  (Utilisez --reset pour régénérer les données depuis zéro)")
        return

    if force_reset:
        warn("Mode --reset : régénération complète des données")

    # Lancer la génération des données
    print("\n  [1/2] Génération des données (peut prendre 30-60 secondes)...")
    result = subprocess.run(
        [sys.executable, os.path.join(BACKEND_DIR, "generate_data.py")],
        cwd=BASE_DIR
    )
    if result.returncode != 0:
        error("La génération des données a échoué.")
    check("Données GPS simulées générées (format Parquet partitionné)")

    # Lancer le traitement et l'entraînement du modèle
    print("\n  [2/2] Traitement des données et entraînement du modèle ML...")
    result = subprocess.run(
        [sys.executable, os.path.join(BACKEND_DIR, "process_bigdata.py")],
        cwd=BASE_DIR
    )
    if result.returncode != 0:
        error("Le traitement des données a échoué.")
    check("Modèle Random Forest entraîné et sauvegardé")
    check("Fichiers JSON de l'API générés")


# ==============================================================================
# ÉTAPE 3 : Lancement du serveur Flask
# ==============================================================================

def launch_server() -> None:
    """
    Lance le serveur Flask et ouvre automatiquement le navigateur.
    """
    banner("Étape 3/3 — Lancement du Serveur Flask")
    print(f"  → URL du dashboard : {SERVER_URL}")
    print(f"  → Appuyez sur Ctrl+C pour arrêter le serveur\n")

    # Ouvrir le navigateur après un court délai
    def open_browser():
        time.sleep(WAIT_BEFORE_BROWSER)
        webbrowser.open(SERVER_URL)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # Lancer Flask (ce processus restera actif jusqu'au Ctrl+C)
    subprocess.run(
        [sys.executable, os.path.join(BACKEND_DIR, "app.py")],
        cwd=BASE_DIR
    )


# ==============================================================================
# POINT D'ENTRÉE
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="DoualaFlow — Système de surveillance du trafic à Douala"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Régénère toutes les données depuis zéro"
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Lance uniquement le serveur (sans régénérer les données)"
    )
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  🚦 DOUALAFLOW — Système Big Data de Surveillance du Trafic")
    print("     Douala, Cameroun")
    print("=" * 65)

    # 1. Vérifier les dépendances
    ensure_dependencies()

    # 2. Préparer les données (sauf si --server uniquement)
    if not args.server:
        ensure_data(force_reset=args.reset)

    # 3. Lancer le serveur
    launch_server()
