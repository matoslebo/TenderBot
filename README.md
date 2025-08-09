# TenderSense – RAG pre verejné zákazky (Azure-ready)

End-to-end **RAG** nad TED/NEN: ingest → validácia (**Great Expectations**) → vektory (**Qdrant**) → **/search** + **/qa** → alerty (**Prefect**).
Repo je pripravené na **Azure Container Apps** + **GitHub Actions**.

## 🚀 Lokálne spustenie

```bash
docker compose up -d qdrant
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m scripts.seed_sample
uvicorn app.main:app --reload
# UI (ak máš streamlit)
streamlit run ui/streamlit_app.py
```

## 🔧 Dôležité env premenné (`.env` alebo Azure secrets)
```
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=tendersense_mvp
EMBEDDING_MODEL_NAME=intfloat/multilingual-e5-base
EMBEDDING_DIM=768

# LLM (ak chceš plné /qa a structured extraction)
LLM_MODEL_PROVIDER=openai
LLM_MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=...

ENABLE_STRUCTURED_EXTRACT=true
RERANK_CANDIDATES=10
```

---

# ☁️ Azure nasadenie (Container Apps)

## 1) Vytvor infra (Bicep)
```bash
az login
az group create -n ts-rg -l westeurope
az deployment group create -g ts-rg -f infra/main.bicep
# zapíš si výstupy (ACR login server, env name)
```

## 2) Build & push imagov do ACR (alebo nechaj na CI)
```bash
az acr build --registry tendersenseacr --image api:latest -f Dockerfile .
az acr build --registry tendersenseacr --image ui:latest -f Dockerfile.ui .
```

## 3) Container Apps (Qdrant, API, UI)
```bash
# Qdrant (internal)
az containerapp create -n ts-qdrant -g ts-rg --environment ts-env   --image qdrant/qdrant:v1.8.4 --target-port 6333 --ingress internal   --cpu 1 --memory 2Gi

# API (external)
az containerapp create -n ts-api -g ts-rg --environment ts-env   --image $(az acr show -n tendersenseacr --query loginServer -o tsv)/api:latest   --target-port 8000 --ingress external   --registry-server $(az acr show -n tendersenseacr --query loginServer -o tsv)   --cpu 1 --memory 2Gi   --env-vars QDRANT_URL=http://ts-qdrant:6333 ENABLE_STRUCTURED_EXTRACT=true   --secret OPENAI_KEY=$OPENAI_API_KEY   --env-vars OPENAI_API_KEY=secretref:OPENAI_KEY LLM_MODEL_PROVIDER=openai LLM_MODEL_NAME=gpt-4o-mini

# UI (external)
az containerapp create -n ts-ui -g ts-rg --environment ts-env   --image $(az acr show -n tendersenseacr --query loginServer -o tsv)/ui:latest   --target-port 8501 --ingress external   --registry-server $(az acr show -n tendersenseacr --query loginServer -o tsv)   --env-vars API_BASE=https://$(az containerapp show -n ts-api -g ts-rg --query properties.configuration.ingress.fqdn -o tsv)
```

## 4) Seed a ingest (raz po deploy)
```bash
az containerapp exec -n ts-api -g ts-rg --command "python -m scripts.seed_sample"
az containerapp exec -n ts-api -g ts-rg --command "python -m flows.ingest_all dq_fail_on_error=False"
```

## 5) CI/CD (GitHub Actions)
- pridaj do **Settings → Secrets and variables → Actions**:
  - `AZURE_CREDENTIALS` (JSON z `az ad sp create-for-rbac ...`)
  - `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINERAPPS_ENV`
  - `ACR_LOGIN_SERVER`, `ACR_USERNAME`, `ACR_PASSWORD`
  - `OPENAI_KEY`

> Pozri `.github/workflows/` – **api.yml** a **ui.yml** postavia image, pushnú do ACR a nasadia do Container Apps.

---

## 📦 Štruktúra
```
infra/                  # Bicep infra (ACR + Container Apps env)
.github/workflows/      # CI/CD pre API aj UI
Dockerfile              # API (FastAPI)
Dockerfile.ui           # UI (Streamlit)
docker-compose.yml      # lokálny Qdrant
requirements.txt
README.md
app/                    # sem skopíruj svoj kód API
ui/                     # sem skopíruj streamlit UI (ak máš)
```

---

> ⚠️ Tento skeleton **neobsahuje tvoje zdrojáky** – skopíruj do `app/`, `flows/`, `validation/`, `scripts/`, `ui/` z tvojho projektu a otestuj lokálne. Potom push na GitHub a nechaj CI nasadiť do Azure.

© 2025
