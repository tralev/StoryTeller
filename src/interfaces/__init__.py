"""Model abstraction interfaces.

The pipeline never references specific models. All pipeline code depends
on these Protocols. Concrete implementations are resolved from config/models.yaml.
"""

from .game_master import GameMaster, GameMasterContext
from .image_generator import ImageGenerator
from .music_generator import MusicGenerator
from .text_generator import TextGenerator
from .validator import ConsistencyReport, ValidationResult, Validator, ValidatorStatus

__all__ = [
    "TextGenerator",
    "Validator",
    "ValidationResult",
    "ValidatorStatus",
    "ConsistencyReport",
    "ImageGenerator",
    "MusicGenerator",
    "GameMaster",
    "GameMasterContext",
]
