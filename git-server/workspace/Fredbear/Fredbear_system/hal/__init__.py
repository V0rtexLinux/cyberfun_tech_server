"""
Fredbear HAL Module
Hardware Abstraction Layer e Sistema de Segurança
"""

from .hardware_controller import (
    HardwareController,
    SerialProtocol,
    ServoConfig,
    MotorConfig,
    LEDConfig,
    HardwareType,
    ServoProfile,
    HardwareState
)

from .safety_system import (
    SafetyMonitor,
    EmergencyStopHandler,
    SafetyThresholds,
    SafetyState,
    SafetyEvent,
    SafetyLevel,
    SafetyEventType
)

__all__ = [
    # Hardware
    'HardwareController',
    'SerialProtocol',
    'ServoConfig',
    'MotorConfig',
    'LEDConfig',
    'HardwareType',
    'ServoProfile',
    'HardwareState',
    # Safety
    'SafetyMonitor',
    'EmergencyStopHandler',
    'SafetyThresholds',
    'SafetyState',
    'SafetyEvent',
    'SafetyLevel',
    'SafetyEventType'
]