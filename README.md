# 🚦 DoualaFlow — Système Big Data de Surveillance du Trafic Routier

> **Mini-projet de TD** — Cours de Systèmes de Fichiers Big Data  
> IUT Génie Informatique — Master 1  
> Contexte : Surveillance intelligente du trafic à Douala, Cameroun

---

## 🎯 Objectif Pédagogique

Ce projet démontre la **chaîne complète d'un système Big Data** :

```
Données Brutes (GPS) → Format Parquet → Traitement Pandas → Modèle ML → API Flask → Dashboard Web
```

Il illustre les **3V du Big Data** dans un contexte réel :
- **Volume** : ~500 000 enregistrements GPS simulés sur 7 jours
- **Velocity** : Dashboard rafraîchi toutes les 2-5 secondes
- **Variety** : Données GPS, vitesses, heures, météo comportementale

---

## 🏗️ Architecture du Projet

```
douala_flow/
│
├── run.py                          ← LANCEMENT EN UNE COMMANDE
├── requirements.txt                ← Dépendances Python
│
├── backend/                        ← LOGIQUE MÉTIER (Python)
│   ├── generate_data.py            ← [ÉTAPE 1] Simulateur GPS Douala
│   ├── process_bigdata.py          ← [ÉTAPE 2] Traitement + Modèle ML
│   └── app.py                      ← [ÉTAPE 3] Serveur API Flask
│
├── frontend/                       ← INTERFACE WEB (HTML/CSS/JS pur)
│   ├── index.html                  ← Structure du dashboard
│   ├── css/
│   │   └── style.css               ← Design "Apple / Spatial UI"
│   └── js/
│       ├── map.js                  ← Carte Leaflet + Véhicules animés
│       └── dashboard.js            ← Orchestrateur + Graphiques Chart.js
│
└── data/                           ← DATA LAKE LOCAL
    ├── raw/
    │   ├── raw_traffic.csv         ← Données brutes (lisible)
    │   └── traffic_parquet/        ← ★ APACHE PARQUET PARTITIONNÉ ★
    │       ├── date=2024-05-01/
    │       │   ├── axis=ndokoti/data.parquet
    │       │   ├── axis=bassa/data.parquet
    │       │   └── ...
    │       └── date=2024-05-02/...
    └── processed/
        ├── aggregated_by_hour.parquet   ← Agrégats analytiques
        ├── current_state.json           ← État actuel (API /current)
        ├── chart_data.json              ← Graphique 24h (API /chart)
        ├── predictions.json             ← Prédictions ML (API /predictions)
        ├── model.joblib                 ← Modèle Random Forest sauvegardé
        └── label_encoder.joblib        ← Encodeur des axes
```

---

## 🚀 Lancement Rapide (1 seule commande)

```bash
# Depuis le dossier douala_flow/
python run.py
```

Cette commande :
1. ✅ Vérifie et installe les dépendances Python
2. ✅ Génère ~500 000 lignes de données GPS (format Parquet)
3. ✅ Entraîne le modèle Random Forest
4. ✅ Lance le serveur Flask
5. ✅ Ouvre automatiquement le navigateur sur http://localhost:5000

### Options avancées

```bash
python run.py --reset    # Régénère toutes les données depuis zéro
python run.py --server   # Lance seulement le serveur (données déjà prêtes)
```

### Lancement manuel (étape par étape)

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Générer les données Big Data
python backend/generate_data.py

# 3. Traiter les données et entraîner le modèle ML
python backend/process_bigdata.py

# 4. Lancer le serveur
python backend/app.py
# → Ouvrir : http://localhost:5000
```

---

## 📊 Fonctionnalités du Dashboard

### 🗺️ Carte Interactive (Douala en mode nuit)
- Vraie carte géographique de Douala (fond sombre "Stadia Dark")
- 6 axes routiers tracés avec leurs vraies coordonnées GPS
- **Code couleur dynamique** : Vert (fluide) → Orange → Rouge (saturé)
- **Véhicules animés** : Points lumineux se déplaçant en temps réel sur les routes
- **Popups d'information** au clic : Congestion, vitesse, nombre de véhicules

### 📡 Sidebar — Données en Temps Réel
- **KPIs globaux** : Congestion max, vitesse moyenne, axes surveillés, véhicules actifs
- **Liste des axes** : Barres de progression et badges de statut, filtrables
- **Prédictions ML** : Prévisions +1h, +2h, +3h par le modèle Random Forest

### 📈 Graphique Temporel
- Évolution de la congestion sur une journée typique (Lundi-Vendredi)
- 6 courbes (une par axe) en couleurs distinctives
- Ligne verticale indiquant l'heure actuelle
- Légende interactive (cliquer pour masquer/afficher un axe)

### 🚨 Alertes
- Bandeau d'alerte automatique si un axe est SATURÉ (congestion > 70%)

---

## 🗺️ Axes Surveillés à Douala

| Axe | Zone | Description |
|-----|------|-------------|
| **Ndokoti** | Carrefour Central | Nœud le plus chargé de la ville |
| **Bonabéri** | Pont sur le Wouri | Axe inter-rives principal |
| **Bassa** | Zone Industrielle | Trafic lourd (camions, usines) |
| **Akwa** | Centre-Ville | Zone commerciale et d'affaires |
| **Makepe** | Résidentiel Nord | Flux domicile-travail |
| **Logbessou** | Périphérie Nord | Accès autoroute Yaoundé |

---

## 🤖 Modèle de Machine Learning

- **Algorithme** : Random Forest Regressor (scikit-learn)
- **Features (entrées)** :
  - Axe routier (encodé numériquement)
  - Heure de la journée (0-23)
  - Jour de la semaine (0=Lundi, 6=Dimanche)
  - Congestion de l'heure précédente (lag feature)
- **Target (sortie)** : Indice de congestion (0-100%)
- **Performance typique** : MAE ≈ 3-5%, R² ≈ 0.92+
- **Horizon de prédiction** : +1h, +2h, +3h

---

## 💾 Pourquoi Apache Parquet ? (Lien avec le cours)

| Critère | CSV classique | **Apache Parquet (ce projet)** |
|---------|---------------|-------------------------------|
| Taille | ~80 Mo | **~8 Mo** (compression Snappy) |
| Lecture partielle | Non (lit tout) | **Oui** (column pruning, predicate pushdown) |
| Partitionnement | Non | **Oui** (par date et par axe) |
| Utilisé par | Excel | **Hadoop, Spark, AWS S3, Databricks** |
| Performance | Lent sur gros volumes | **10x-100x plus rapide** |

La structure `data/raw/traffic_parquet/date=.../axis=.../` est identique
à ce que vous trouveriez dans un vrai Data Lake sur HDFS ou Amazon S3.

---

## 🔌 API Flask — Endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Dashboard HTML |
| `/api/current` | GET | État actuel de chaque axe (rafraîchi toutes les 5s) |
| `/api/chart` | GET | Données du graphique 24h |
| `/api/predictions` | GET | Prédictions ML (+1h, +2h, +3h) |
| `/api/vehicles` | GET | Positions animées des véhicules (rafraîchi toutes les 2s) |
| `/api/stats` | GET | KPIs globaux (congestion moyenne, axe critique, etc.) |

---

## 📈 Scalabilité — Du TD au Projet Gigantesque

Ce projet est conçu comme une **base évolutive**. Voici comment chaque composant
peut évoluer sans modifier les autres :

| Composant | Maintenant (TD) | Futur (Production) |
|-----------|-----------------|-------------------|
| Données | Script Python simulé | Capteurs IoT + Apache Kafka |
| Stockage | Parquet local | HDFS / Amazon S3 / Delta Lake |
| Traitement | Pandas (1 PC) | Apache Spark (cluster) |
| Modèle ML | Random Forest | LSTM / Transformer temporel |
| Serveur | Flask (1 processus) | FastAPI + Redis + Kubernetes |
| Frontend | Vanilla JS | React + MapboxGL / WebGL |

---

## 📦 Dépendances Python

```
pandas>=2.0.0         # Manipulation des DataFrames
pyarrow>=12.0.0       # Moteur Apache Parquet
numpy>=1.24.0         # Calculs numériques
scikit-learn>=1.3.0   # Modèle Random Forest
joblib>=1.3.0         # Sérialisation du modèle
Flask>=3.0.0          # Serveur API web
flask-cors>=4.0.0     # Cross-Origin Resource Sharing
```

---

*Projet réalisé dans le cadre du cours de Systèmes de Fichiers Big Data — IUT Génie Informatique, Master 1*
