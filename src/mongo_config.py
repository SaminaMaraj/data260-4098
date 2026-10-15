"""MongoDB configuration for DATA 260 Homework 6."""

import os


MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "s4098_doc")
MONGO_INCIDENTS_COLLECTION = "incidents"

