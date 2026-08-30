"""P8.C05A — Worldgen contract freeze and zero-gap coverage ledger.

This package owns:
  requirements.py       — Every normative requirement from the three absorbed docs
  profiles.py           — Named WorldSpec profiles (tiny, conformance, default)
  legacy_inventory.py   — Legacy symbol inventory (P8.C05H: all symbols deleted)
  generator.py          — In-memory human-readable requirement report
"""

from .evidence import validate_evidence
from .generator import generate_markdown
from .profiles import (
    FROZEN_CONTRACT_HASHES,
    FROZEN_PROFILE_HASHES,
    PROFILE_CONFORMANCE,
    PROFILE_DEFAULT,
    PROFILE_TINY,
    contract_hashes,
    expand_profile,
    profile_hash,
    validate_profile_contract,
    verify_contract_hashes,
)
from .requirements import (
    DOMAIN_OWNER,
    REQUIREMENTS,
    Requirement,
    Status,
    requirement_owner,
    validate_requirements,
)
from .source_coverage import SOURCE_CLAUSES, SourceClause, validate_source_coverage

__all__ = [
    "PROFILE_TINY",
    "PROFILE_CONFORMANCE",
    "PROFILE_DEFAULT",
    "FROZEN_CONTRACT_HASHES",
    "FROZEN_PROFILE_HASHES",
    "validate_profile_contract",
    "contract_hashes",
    "verify_contract_hashes",
    "expand_profile",
    "profile_hash",
    "REQUIREMENTS",
    "Requirement",
    "Status",
    "validate_requirements",
    "DOMAIN_OWNER",
    "requirement_owner",
    "generate_markdown",
    "SOURCE_CLAUSES",
    "SourceClause",
    "validate_source_coverage",
    "validate_evidence",
]
