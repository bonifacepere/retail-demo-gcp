# retail-demo-gcp

Prototype de centralisation de données retail multi-enseignes et de
recommandation produit, sur Google Cloud Platform.

## Le problème adressé

Une entreprise retail veut centraliser les données de vente de plusieurs
grandes enseignes partenaires, afin de proposer des recommandations
commerciales pertinentes aux clients qui achètent sur le site. Chaque
enseigne exporte ses données dans un format différent — le défi n'est pas
seulement de stocker la donnée, mais de la rendre exploitable malgré son
hétérogénéité.

## Architecture

```
                Sources hétérogènes (enseignes retail)
                CSV, exports ERP, formats variés
                                │
                                ▼
                  Cloud Storage (zone d'atterrissage)
                                │
                    déclenché par Cloud Scheduler
                                ▼
              ┌─────────────────────────────────┐
              │   Cloud Run JOB (mini_projet_gcp) │
              │   normalise chaque enseigne vers   │
              │   un schéma pivot commun            │
              └─────────────────────────────────┘
                                │
                                ▼
                BigQuery — retail_central.ventes
                (données centralisées, multi-enseignes)
                                │
                                ▼
              ┌─────────────────────────────────┐
              │  Cloud Run SERVICE (service_gcp)  │
              │  API de recommandation en HTTP,    │
              │  appelée par le site e-commerce     │
              └─────────────────────────────────┘
```

Deux composants, pour deux besoins de vitesse différents :

| Composant | Rôle | Type Cloud Run | Dossier |
|---|---|---|---|
| **Centralisation** | Ingère et normalise les données de chaque enseigne, les charge dans BigQuery | **Job** (batch, périodique) | [`mini_projet_gcp/`](./mini_projet_gcp) |
| **Recommandation** | Sert des suggestions produit en temps réel via HTTP | **Service** (toujours disponible) | [`service_gcp/`](./service_gcp) |

L'ingestion multi-enseignes n'a pas besoin d'être temps réel (un run
périodique suffit), tandis que la recommandation doit répondre en quelques
centaines de millisecondes pendant que le client navigue sur le site — d'où
deux outils Cloud Run différents plutôt qu'un seul.

## Structure du dépôt

```
retail-demo-gcp/
├── mini_projet_gcp/       # Cloud Run Job — centralisation multi-enseignes
│   ├── main.py             # extract (par enseigne) -> normalize -> transform -> load BigQuery
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── deploy.sh            # déploiement via gcloud CLI
│   └── README.md            # détails techniques du Job
├── service_gcp/            # Cloud Run Service — API de recommandation
│   ├── main.py               # FastAPI : /health, /recommandations, /recommandations/client
│   ├── Dockerfile
│   ├── requirements.txt
│   └── deploy_service.sh      # déploiement via gcloud CLI
└── README.md                # ce fichier
```

## Stack technique

- **Python** — Pandas pour la transformation, FastAPI pour l'API
- **Google Cloud Run** — Jobs (batch) et Services (HTTP), exécution serverless conteneurisée
- **Google BigQuery** — entrepôt de données centralisé
- **Cloud Build** — construction des images Docker
- **Artifact Registry** — stockage des images Docker
- **Cloud Scheduler** *(prévu, non déployé dans ce prototype)* — déclenchement périodique du Job

## Démarrage rapide

### Option A — en local, sans GCP

```bash
# Centralisation (affiche un aperçu si PROJECT_ID n'est pas défini)
cd mini_projet_gcp
pip install -r requirements.txt
python main.py

# API de recommandation (bascule sur un jeu de données en mémoire si PROJECT_ID n'est pas défini)
cd ../service_gcp
pip install -r requirements.txt
python main.py
curl "http://localhost:8080/recommandations?produit=Clavier"
```

### Option B — déploiement complet sur GCP (CLI)

Prérequis : `gcloud` installé et authentifié, projet GCP actif avec
facturation liée, APIs `run`, `artifactregistry`, `cloudbuild` et `bigquery`
activées.

```bash
cd mini_projet_gcp && ./deploy.sh    # déploie et exécute le Job
cd ../service_gcp && ./deploy_service.sh   # déploie le Service et teste ses endpoints
```

Chaque script contient toutes les commandes `gcloud` dans l'ordre (création
du dépôt Artifact Registry, du dataset BigQuery, build, déploiement,
exécution/test). Voir le README de chaque sous-dossier pour le détail.

### Option C — déploiement via la console GCP

Voir le README de `service_gcp/` pour la procédure pas à pas via l'interface
graphique (déploiement en continu depuis GitHub avec Cloud Build).

## Limites connues du prototype (assumées, à faire évoluer en production)

- Les enseignes sources sont simulées en dur dans le code (`_extract_enseigne_a`,
  `_extract_enseigne_b`) plutôt que lues depuis Cloud Storage — à brancher en
  production sur les exports réels.
- La recommandation utilise une simple analyse de panier (co-occurrence par
  `commande_id`) — une évolution naturelle serait **BigQuery ML** ou
  **Vertex AI** pour un scoring intégrant marge produit, saisonnalité, stock.
- Pas de tests automatisés, pas d'infra as code (Terraform) — volontairement
  hors périmètre pour ce prototype de démonstration.
- Le service accepte les invocations non authentifiées (`--allow-unauthenticated`)
  pour faciliter les tests ; en production ce flag serait retiré au profit
  d'IAM (`roles/run.invoker`).
