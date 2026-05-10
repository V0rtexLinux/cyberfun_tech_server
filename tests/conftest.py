"""
Fixtures compartilhados entre testes
"""

import pytest
import sys
import os
import tempfile
import yaml

# Garantir que o core está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_config_file():
    """Cria um arquivo de configuração temporário"""
    config = {
        "name": "TestAnimatronic",
        "version": "3.1.0",
        "hardware": {
            "servos": [
                {
                    "id": 0,
                    "name": "TestServo",
                    "min_angle": 0.0,
                    "max_angle": 180.0,
                    "min_pulse": 500,
                    "max_pulse": 2500,
                    "neutral_pulse": 1500,
                    "max_speed": 100.0,
                    "inverted": False,
                }
            ]
        },
        "sensors": {
            "pir_pin": 17,
            "ultrasonic_trigger": 23,
            "ultrasonic_echo": 24,
            "imu_i2c_addr": 0x68,
            "mic_device": 0,
        },
        "ai": {
            "backend_priority": ["fallback"],
            "max_tokens": 50,
            "temperature": 0.5,
        },
        "logging": {"level": "DEBUG", "to_file": False},
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def mock_serial_port():
    """Retorna porta serial simulada"""
    return "/dev/ttyTEST0"


@pytest.fixture
def test_servo_config():
    """Configuração de servo para testes"""
    from core.config.loader import ServoConfig
    return ServoConfig(
        id=0,
        name="TestJaw",
        min_angle=0.0,
        max_angle=45.0,
        min_pulse=500,
        max_pulse=2500,
        neutral_pulse=1500,
        max_speed=120.0,
    )
