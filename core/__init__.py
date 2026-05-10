"""
================================================================================
CYBER FUN CORE - Módulo Compartilhado entre Animatrônicos
================================================================================
Este módulo contém código reutilizável entre Fredbear e Springbonnie,
eliminando duplicação e facilitando manutenção.

Usage:
    from core import HardwareController, FacialExpressionController
    from core.ai import AIChatBrain
    from core.config import AnimatronicConfig
================================================================================
"""

__version__ = "3.1.0"
__author__ = "Cyber Fun Tech"

# Exportar classes principais para facilitar imports
from .hal.hardware_controller import HardwareController
from .expression.facial_controller import FacialExpressionController, EmotionPreset
from .kernel.fsm_kernel import AnimatronicKernel, SystemState
from .sensors.sensor_hub import SensorHub
from .tts.tts_engine import TTSManager
from .sequences.animation_sequences import SequencePlayer
from .config.loader import AnimatronicConfig

__all__ = [
    "HardwareController",
    "FacialExpressionController",
    "EmotionPreset",
    "AnimatronicKernel",
    "SystemState",
    "SensorHub",
    "TTSManager",
    "SequencePlayer",
    "AnimatronicConfig",
]
