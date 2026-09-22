# Medical Chatbot Ingestion Pipeline

This folder contains the complete **data-ingestion side** of the custom medical chatbot project.
It is intentionally separate from the future FastAPI backend and Next.js frontend.

## What it does

```text
MedlinePlus Health Topic XML
        ↓
Select 10 starter topics
        ↓
Keep English topics only
        ↓
Extract summaries + linked resources
        ↓
Keep only trusted Tier-1 domains
        ↓
Download linked HTML pages
        ↓
Reject Spanish / non-HTML / untrusted pages
        ↓
Clean article text
        ↓
Save each source as its own JSON document
        ↓
Chunk documents for later embeddings / RAG
```

## Starter trusted domains

Version 1 automatically accepts only:

- `medlineplus.gov`
- `nih.gov` and `*.nih.gov`
- `cdc.gov` and `*.cdc.gov`
- `cancer.gov` and `*.cancer.gov`

Everything else is excluded from the RAG corpus and remains auditable in the topic JSON's `excluded_resources` list.

## Important design choices

- **English only for Version 1.** The schema still stores `language: "en"` so multilingual support can be added later.
- **No recursive crawling.** Only resources directly listed on the selected MedlinePlus topic records are considered.
- **The raw MedlinePlus XML is not committed to Git.** The script downloads it locally.
- **Non-HTML resources are skipped for now.** PDF handling can be added later as a separate ingestion path.
- **A MedlinePlus link is not treated as automatic permission to redistribute another site's content.** Review source terms before publishing or redistributing stored third-party content.

## Folder structure

```text
medical_chatbot_ingestion/
├── ingestion/
│   ├── medlineplus/
│   │   ├── extract_medlineplus_topics.py
│   │   ├── language_filters.py
│   │   ├── trusted_sources.py
│   │   ├── resource_downloader.py
│   │   └── selected_topics.txt
│   ├── cleaners/
│   │   ├── html_cleaner.py
│   │   └── text_cleaner.py
│   ├── chunking/
│   │   └── chunker.py
│   └── pipeline/
│       └── ingest.py
├── scripts/
│   └── run_ingestion.py
├── data/
│   ├── raw/
│   ├── topics/
│   ├── documents/
│   ├── chunks/
│   └── logs/
├── tests/
├── requirements.txt
├── .gitignore
└── README.md
```

## Setup

From the project root:

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run only XML extraction

This downloads the large MedlinePlus XML locally if it is not already present and creates the 10 topic JSON files.

```powershell
python -m ingestion.medlineplus.extract_medlineplus_topics
```

Outputs:

```text
data/topics/
├── diabetes.json
├── asthma.json
├── high_blood_pressure.json
├── flu.json
├── migraine.json
├── anemia.json
├── hypothyroidism.json
├── cholesterol.json
├── allergy.json
├── pneumonia.json
├── index.json
└── topics.jsonl
```

## Run the full ingestion pipeline

```powershell
python scripts/run_ingestion.py
```

The pipeline will:

1. download the MedlinePlus XML if necessary;
2. extract the selected topics;
3. filter resources by language and trusted domain;
4. download eligible HTML resources;
5. clean the article text;
6. save documents under `data/documents/`;
7. create overlapping text chunks in `data/chunks/chunks.jsonl`;
8. write download/audit logs to `data/logs/`.

## Run without downloading linked resources

Useful when you only want to inspect the XML extraction step:

```powershell
python scripts/run_ingestion.py --skip-downloads
```

## Chunk settings

Defaults:

- chunk size: `350` words
- overlap: `60` words

Override them with:

```powershell
python scripts/run_ingestion.py --chunk-size-words 500 --overlap-words 75
```

## Run tests

```powershell
pytest -q
```

## What comes next

The generated `data/chunks/chunks.jsonl` is the handoff point to the RAG stage:

```text
chunks.jsonl
    ↓
embedding model
    ↓
FAISS / pgvector
    ↓
retriever
    ↓
LLM with citations
```

Do **not** add embeddings to this ingestion package yet. Keeping collection/cleaning/chunking separate from retrieval makes the project easier to test and debug.
