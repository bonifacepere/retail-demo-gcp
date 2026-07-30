"""
Pipeline ETL — Centralisation de données retail multi-enseignes
------------------------------------------------------------------
Cloud Run Job.

Contexte : plusieurs grandes enseignes retail envoient leurs données de
vente dans des formats différents (noms de colonnes, structure). L'objectif
est de les normaliser vers un schéma commun et de les centraliser dans
BigQuery, pour ensuite alimenter un moteur de recommandation exposé côté
site e-commerce (voir service_gcp/main.py).

Étapes :
  1. EXTRACT  : récupère un fichier brut par enseigne (Cloud Storage en
                production, ex: gs://raw-retail-data/{enseigne}/*.csv)
  2. NORMALIZE: chaque enseigne a son propre schéma -> on les fait
                converger vers un schéma pivot commun
  3. TRANSFORM: nettoyage, typage, calculs (montant, panier)
  4. LOAD     : écrit dans la table BigQuery centrale `ventes`

Variables d'environnement :
  PROJECT_ID   -> id du projet GCP
  DATASET_ID   -> dataset BigQuery (défaut: retail_central)
  TABLE_ID     -> table BigQuery (défaut: ventes)
  SOURCE_PREFIX-> préfixe Cloud Storage des fichiers sources, ex:
                  gs://raw-retail-data (optionnel, données d'exemple sinon)
"""

import os
import sys
import logging
from datetime import datetime, timezone

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Schéma pivot commun vers lequel on normalise toutes les enseignes.
SCHEMA_PIVOT = [
    "enseigne",
    "produit",
    "prix_unitaire",
    "quantite",
    "commande_id",
    "client_id",
    "date_vente",
]


def _extract_enseigne_a() -> pd.DataFrame:
    """Simule un export brut de l'enseigne A (ex: format 'à la française')."""
    df = pd.DataFrame(
        {
            "reference_produit": ["Clavier", "Souris", "Ecran", "Clavier"],
            "prix": [45.0, 20.0, 150.0, 45.0],
            "quantite_vendue": [3, 10, 2, 5],
            "commande": ["CMD-A-001", "CMD-A-001", "CMD-A-002", "CMD-A-003"],
            "client": ["CLI-1001", "CLI-1001", "CLI-1002", "CLI-1003"],
            "date": ["2026-07-01", "2026-07-01", "2026-07-02", "2026-07-03"],
        }
    )
    df["enseigne"] = "EnseigneA"
    return df.rename(
        columns={
            "reference_produit": "produit",
            "prix": "prix_unitaire",
            "quantite_vendue": "quantite",
            "commande": "commande_id",
            "client": "client_id",
            "date": "date_vente",
        }
    )


def _extract_enseigne_b() -> pd.DataFrame:
    """Simule un export brut de l'enseigne B (schéma différent, ex: export
    d'un ERP anglophone)."""
    df = pd.DataFrame(
        {
            "sku": ["Souris", "Ecran", "Clavier", "Souris"],
            "unit_price": [20.0, 160.0, 45.0, 20.0],
            "qty": [7, 1, 2, 4],
            "order_id": ["ORD-B-501", "ORD-B-501", "ORD-B-502", "ORD-B-503"],
            "customer_id": ["CUST-77", "CUST-77", "CUST-78", "CUST-79"],
            "sale_date": ["2026-07-03", "2026-07-03", "2026-07-04", "2026-07-04"],
        }
    )
    df["enseigne"] = "EnseigneB"
    return df.rename(
        columns={
            "sku": "produit",
            "unit_price": "prix_unitaire",
            "qty": "quantite",
            "order_id": "commande_id",
            "customer_id": "client_id",
            "sale_date": "date_vente",
        }
    )


# Registre des enseignes connues -> permet d'ajouter facilement une nouvelle
# enseigne sans toucher au reste du pipeline (juste ajouter une fonction
# d'extraction + normalisation ici).
ENSEIGNES = {
    "EnseigneA": _extract_enseigne_a,
    "EnseigneB": _extract_enseigne_b,
}


def extract() -> pd.DataFrame:
    """EXTRACT + NORMALIZE : récupère et unifie les données de toutes les
    enseignes vers le schéma pivot commun."""
    source_prefix = os.environ.get("SOURCE_PREFIX")

    if source_prefix:
        # En production : lecture réelle depuis Cloud Storage, un fichier
        # (ou plusieurs) par enseigne, avec un mapping de colonnes propre à
        # chaque enseigne (à définir selon les contrats de données réels).
        logger.info("Lecture des fichiers sources depuis %s", source_prefix)
        raise NotImplementedError(
            "Brancher ici la lecture réelle des fichiers par enseigne "
            "(ex: pd.read_csv(f'{source_prefix}/{enseigne}/*.csv'))"
        )

    logger.info(
        "Aucun SOURCE_PREFIX fourni : génération de données d'exemple "
        "pour %d enseignes simulées",
        len(ENSEIGNES),
    )
    frames = [extractor() for extractor in ENSEIGNES.values()]
    df = pd.concat(frames, ignore_index=True)[SCHEMA_PIVOT]
    logger.info(
        "Extraction + normalisation terminées : %d lignes issues de %d enseignes",
        len(df),
        df["enseigne"].nunique(),
    )
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """TRANSFORM : nettoyage et enrichissement métier communs, une fois le
    schéma déjà unifié."""
    logger.info("Début de la transformation")

    df = df.dropna(subset=["produit", "prix_unitaire", "quantite"])
    df["produit"] = df["produit"].str.strip().str.title()
    df["date_vente"] = pd.to_datetime(df["date_vente"]).dt.date
    df["prix_unitaire"] = df["prix_unitaire"].astype(float)
    df["quantite"] = df["quantite"].astype(int)

    df["montant_total"] = df["prix_unitaire"] * df["quantite"]
    df["date_traitement"] = datetime.now(timezone.utc)

    logger.info("Transformation terminée : %d lignes, %d colonnes", *df.shape)
    return df


def load(df: pd.DataFrame) -> None:
    """LOAD : écrit le résultat centralisé dans BigQuery."""
    project_id = os.environ.get("PROJECT_ID")
    dataset_id = os.environ.get("DATASET_ID", "retail_central")
    table_id = os.environ.get("TABLE_ID", "ventes")

    if not project_id:
        logger.warning(
            "PROJECT_ID non défini : le chargement BigQuery est ignoré. "
            "Aperçu des données transformées :\n%s",
            df.head(10).to_string(),
        )
        return

    from google.cloud import bigquery

    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    logger.info("Chargement dans BigQuery : %s", table_ref)

    client = bigquery.Client(project=project_id)

    job_config = bigquery.LoadJobConfig(
        # WRITE_APPEND ici : contrairement au mini projet simple, on veut
        # accumuler l'historique multi-enseignes dans le temps plutôt que
        # tout écraser à chaque run. L'idempotence se gère alors par un
        # identifiant de run ou un filtre sur date_traitement en aval.
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
    )

    load_job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    load_job.result()

    table = client.get_table(table_ref)
    logger.info("Chargement terminé : %d lignes dans %s", table.num_rows, table_ref)


def main() -> int:
    logger.info("=== Démarrage du job de centralisation retail ===")
    try:
        df_raw = extract()
        df_clean = transform(df_raw)
        load(df_clean)
    except Exception:
        logger.exception("Le job a échoué")
        return 1
    logger.info("=== Job terminé avec succès ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
