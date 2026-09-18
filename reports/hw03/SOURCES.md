# HW3 Corpus Sources

Access date will be recorded by `code/download_corpus.py` in `CORPUS_MANIFEST.json`.

1. Federal Transit Administration, *FRA Regulated Mode Major Security Events*.
   Source: https://data.transportation.gov/d/65fa-qbkf
   Download: https://data.transportation.gov/resource/65fa-qbkf.csv?$limit=300
   The local snapshot contains the first 300 records returned by the official Socrata API. It contains individual security events reported to the National Transit Database for FRA-regulated commuter rail, Alaska Railroad, and specified rail services.

2. Federal Transit Administration, *Accessing National Transit Database Safety and Security Event Data*.
   Source: https://www.transit.dot.gov/ntd/accessing-national-transit-database-ntd-safety-and-security-event-data
   The page documents the scope, publication schedule, and types of safety and security data released by the FTA.

The local snapshots and their byte sizes and SHA-256 hashes are recorded in
`CORPUS_MANIFEST.json`.
