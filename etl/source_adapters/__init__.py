"""Source readers for unordered clinical evidence acquisition."""

from .eicu import EICUSourceAdapter
from .mcmed import MCMEDSourceAdapter
from .mimic import MIMICSourceAdapter
from .narrative import NEJMSourceAdapter, PMCSourceAdapter
from .interaction import (
    MediScopeSourceAdapter,
    MedPISourceAdapter,
    PatientSimSourceAdapter,
    MeddiesSourceAdapter,
    MedMemoryBenchSourceAdapter,
    MedDialogRubricsSourceAdapter,
)

__all__ = [
    "MCMEDSourceAdapter",
    "MIMICSourceAdapter",
    "EICUSourceAdapter",
    "PMCSourceAdapter",
    "NEJMSourceAdapter",
    "MediScopeSourceAdapter",
    "MedPISourceAdapter",
    "PatientSimSourceAdapter",
    "MeddiesSourceAdapter",
    "MedMemoryBenchSourceAdapter",
    "MedDialogRubricsSourceAdapter",
]
