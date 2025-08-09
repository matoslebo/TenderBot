from prefect import flow, task
import pandas as pd
from validation.validate import validate_df
from app.embeddings import embed_texts
from app.qdrant_client_utils import ensure_collection, upsert_points

@task
def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

@task
def validate(df: pd.DataFrame) -> pd.DataFrame:
    validate_df(df)
    return df

@task
def index(df: pd.DataFrame):
    ensure_collection()
    texts = (df["title"] + "\n" + df["description"]).tolist()
    vecs = embed_texts(texts)
    payloads = df.to_dict(orient="records")
    upsert_points(payloads, vecs)

@flow
def ingest_flow(path: str = "sample_data/notices.csv"):
    df = load_csv(path)
    df = validate(df)
    index(df)

if __name__ == "__main__":
    ingest_flow()
