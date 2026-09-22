# Source ingestion

MedlinePlus is used primarily as a discovery/index source. The documents in this
folder are the code paths that turn discovered resources into actual evidence
records.

## `medlineplus/`

Creates one small, patient-friendly document from each selected MedlinePlus
Health Topic summary.

## `web/`

Downloads trusted source documents discovered by MedlinePlus. Despite the
legacy filename `html_downloader.py`, v3 supports both HTML and text-based PDF
resources.

The actual publisher remains the citation source. For example, an NIDDK page is
stored as an NIDDK/NIH document with `discovered_via: MedlinePlus`.

The downloader intentionally does not bypass 403/405 access controls, recurse
through arbitrary links, or OCR scanned/image-only PDFs.
