"""
Springbonnie Expression Module
Sistema de Expressão Facial Multi-Eixo
"""

from .facial_controller import (
    FacialExpressionController,
    ServoController,
    EasingFunctions,
    EmotionPreset,
    FacialPosition,
    ServoConfig,
    ServoState,
    ExpressionTransition
)

__all__ = [
    'FacialExpressionController',
    'ServoController',
    'EasingFunctions',
    'EmotionPreset',
    'FacialPosition',
    'ServoConfig',
    'ServoState',
    'ExpressionTransition'
]
