"""
Springbonnie Vision Module
Sistema de Visão Computacional com TFLite
"""

from .face_detector import (
    FaceDetectorTFLite,
    InteractionManager,
    FaceDetectionState,
    DetectedFace,
    LEDState
)

__all__ = [
    'FaceDetectorTFLite',
    'InteractionManager',
    'FaceDetectionState',
    'DetectedFace',
    'LEDState'
]