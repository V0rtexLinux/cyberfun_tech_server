"""
Fredbear Audio Module
Sistema de Orquestração de Show e Áudio
"""

from .show_orchestrator import (
    ShowOrchestrator,
    AudioProcessor,
    TimelineParser,
    ShowBuilder,
    ShowState,
    EventType,
    ShowTrack,
    TimelineEvent,
    AudioData
)

__all__ = [
    'ShowOrchestrator',
    'AudioProcessor',
    'TimelineParser',
    'ShowBuilder',
    'ShowState',
    'EventType',
    'ShowTrack',
    'TimelineEvent',
    'AudioData'
]