"""Provider adapters — read-only source-system ingestion.

Each adapter maps one external source (QuickBooks, HubSpot, Slack, ...) into the
provider-neutral shapes defined by schemas/baseline.json. Adapters never write to
the source; they only read an export/snapshot and emit normalized records with
provenance so downstream findings can source-trace every number.
"""
from .quickbooks import QuickBooksAdapter, build_baseline

__all__ = ["QuickBooksAdapter", "build_baseline"]
