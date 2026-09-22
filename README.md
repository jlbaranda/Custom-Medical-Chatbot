# Medical Data Ingestion

This folder contains the ingestion pipeline used to build the medical corpus for the chatbot.

The pipeline uses MedlinePlus as a discovery source, follows trusted English-language links from approved government health domains, downloads HTML and PDF content, cleans the text, and splits the documents into chunks for retrieval.

## Requirements

Use Python 3.12.

Create a virtual environment if one does not already exist:

```powershell
py -3.12 -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Confirm the Python version:

```powershell
python --version
```

It should show Python 3.12.x.

Install the project dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run the Tests

Before running ingestion, run the test suite:

```powershell
python -m pytest -q
```

All tests should pass before generating the corpus.

## Run the Ingestion Pipeline

From the project root:

```powershell
python scripts/run_ingestion.py
```

The pipeline will:

1. Download or reuse the MedlinePlus health-topic XML dataset.
2. Find the selected medical topics.
3. Discover trusted English-language sources linked through MedlinePlus.
4. Create MedlinePlus summary documents.
5. Download trusted HTML and PDF sources.
6. Clean the extracted text.
7. Split documents into chunks.
8. Write logs and corpus statistics.

## Run a Clean Rebuild

To remove previously generated documents, chunks, and logs before rebuilding the corpus:

```powershell
python scripts/run_ingestion.py --clean-generated
```

This is recommended after changing ingestion, cleaning, or chunking code.

The command does not delete the ingestion source code or the raw MedlinePlus XML file.

## Selected Topics

The topics used by the pipeline are defined in:

```text
ingestion/discovery/medlineplus/selected_topics.txt
```

The current topics are:

```text
Diabetes
Asthma
High Blood Pressure
Flu
Migraine
Anemia
Hypothyroidism
Cholesterol
Allergy
Pneumonia
```

## Trusted Sources

The pipeline currently accepts content from:

```text
medlineplus.gov
nih.gov and NIH subdomains
cdc.gov and CDC subdomains
cancer.gov and NCI subdomains
```

MedlinePlus is mainly used as a discovery source.

If MedlinePlus links to an NIH, CDC, or NCI article, the actual organization that published the article is stored as the publisher.

## Generated Data

### Raw Data

```text
data/raw/
```

Contains downloaded source datasets such as the MedlinePlus XML file.

### Discovery Data

```text
data/discovery/
```

Contains information about the selected MedlinePlus topics and the external sources discovered for them.

### Documents

```text
data/documents/
```

Contains cleaned full documents from MedlinePlus, NIH, CDC, NCI, and other approved source groups.

Each document includes metadata such as:

```text
document_id
title
publisher
source_url
source_format
language
parent_topics
trusted_domain
text
```

### Chunks

```text
data/chunks/chunks.jsonl
```

This is the main output used by the retrieval system.

Each line contains one chunk of medical text and its metadata.

The chatbot's retrieval system should primarily build from this file.

Example fields include:

```text
chunk_id
document_id
text
word_count
title
publisher
source_url
parent_topics
source_group
source_format
language
trust_tier
```

### Logs

```text
data/logs/
```

Contains information about the ingestion run.

Important files include:

```text
source_downloads.jsonl
summary.json
corpus_manifest.json
```

`source_downloads.jsonl` records whether each source was downloaded, skipped, or failed.

`summary.json` contains overall corpus statistics.

`corpus_manifest.json` describes the composition of the generated corpus.

## HTML and PDF Support

The pipeline supports both HTML pages and PDFs.

HTML pages are cleaned to remove content such as:

```text
navigation
footers
share buttons
resource cards
page-maintenance metadata
related-link sections
```

PDF text is extracted using `pypdf`.

Image-only or scanned PDFs without usable embedded text are skipped. OCR is not currently used.

## Chunking

Documents are split into smaller chunks before retrieval.

The current chunking settings are approximately:

```text
maximum chunk size: 350 words
overlap: 60 words
minimum trailing chunk: 80 words
```

The overlap helps preserve context between neighboring chunks.

Small final chunks are either merged into the previous chunk or removed when they contain only overlapping text.

## Failed or Skipped Sources

Some sources may fail or be skipped because of:

```text
HTTP 403
HTTP 405
unavailable pages
insufficient article text
scanned or image-only PDFs
language filtering
untrusted domains
```

The pipeline does not attempt to bypass website access restrictions.

Failures and skipped sources are recorded in:

```text
data/logs/source_downloads.jsonl
```
