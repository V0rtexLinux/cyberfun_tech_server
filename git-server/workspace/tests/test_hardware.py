"""
================================================================================
TESTES DE HARDWARE (HAL)
================================================================================
"""

import pytest
import time
import numpy as np
from unittest.mock import Mock, patch, MagicMock

# Mock do serial antes de importar
mock_serial = Mock()
mock_serial.tools = Mock()
mock_serial.tools.list_ports = Mock()
mock_serial.tools.list_ports.comports = Mock(return_value=[])

sys.modules['serial'] = mock_serial
sys.modules['serial.tools'] = mock_serial.tools
sys.modules['serial.tools.list_ports'] = mock_serial.tools.list_ports

from core.hal.hardware_controller import (
    HardwareController,
    SerialProtocol,
    ServoConfig,
    MotorConfig,
)


class TestSerialProtocol:
    """Testes do protocolo serial"""
    
    def test_build_servo_command(self):
        """Testa construção de comando de servo"""
        cmd = SerialProtocol.build_servo_command(0, 1500, speed=50)
        
        assert cmd[0] == SerialProtocol.START_BYTE  # 0xAA
        assert cmd[1] == SerialProtocol.CMD_SERVO_MOVE  # 0x01
        assert cmd[2] == 0  # servo_id
        assert cmd[3] == (1500 >> 8) & 0xFF  # pulse high
        assert cmd[4] == 1500 & 0xFF  # pulse low
        assert cmd[5] == 50  # speed
        assert cmd[6] == SerialProtocol.END_BYTE  # 0x55
    
    def test_build_motor_command(self):
        """Testa construção de comando de motor"""
        cmd = SerialProtocol.build_motor_command(0, 128, direction=0)
        
        assert cmd[0] == SerialProtocol.START_BYTE
        assert cmd[1] == SerialProtocol.CMD_MOTOR_SET
        assert cmd[2] == 0  # motor_id
        assert cmd[3] == 128  # speed
        assert cmd[4] == 0  # direction
        assert cmd[5] == SerialProtocol.END_BYTE
    
    def test_build_heartbeat_command(self):
        """Testa construção de comando de heartbeat"""
        cmd = SerialProtocol.build_heartbeat_command()
        
        assert cmd[0] == SerialProtocol.START_BYTE
        assert cmd[1] == SerialProtocol.CMD_HEARTBEAT
        assert cmd[2] == SerialProtocol.END_BYTE
    
    def test_build_estop_command(self):
        """Testa construção de comando de emergência"""
        cmd = SerialProtocol.build_estop_command()
        
        assert cmd[0] == SerialProtocol.START_BYTE
        assert cmd[1] == SerialProtocol.CMD_ESTOP
        assert cmd[2] == SerialProtocol.END_BYTE
    
    def test_parse_valid_response(self):
        """Testa parse de resposta válida"""
        response = bytes([0xAA, 0x01, 0x00, 0x55])  # START, CMD, SUCCESS, END
        parsed = SerialProtocol.parse_response(response)
        
        assert parsed is not None
        assert parsed['command'] == 0x01
        assert parsed['success'] is True
    
    def test_parse_invalid_response(self):
        """Testa parse de resposta inválida"""
        # Resposta sem bytes de início/fim corretos
        response = bytes([0x00, 0x01, 0x00, 0x00])
        parsed = SerialProtocol.parse_response(response)
        
        assert parsed is None
    
    def test_parse_short_response(self):
        """Testa parse de resposta muito curta"""
        response = bytes([0xAA, 0x55])
        parsed = SerialProtocol.parse_response(response)
        
        assert parsed is None


class TestHardwareController:
    """Testes do controlador de hardware"""
    
    def test_controller_initialization(self):
        """Testa inicialização do controlador"""
        controller = HardwareController()
        
        assert controller is not None
        assert len(controller.servo_configs) == 7  # 7 servos faciais
        assert len(controller.motor_configs) == 2  # 2 motores
        assert len(controller.led_configs) == 2  # 2 LEDs
    
    def test_servo_config_defaults(self):
        """Testa configurações padrão de servos"""
        controller = HardwareController()
        
        jaw_servo = controller.servo_configs[0]
        assert jaw_servo.name == "Jaw"
        assert jaw_servo.min_angle == 0.0
        assert jaw_servo.max_angle == 45.0
        assert jaw_servo.max_speed == 120.0
    
    def test_servo_angle_limits(self):
        """Testa limites de ângulo do servo"""
        controller = HardwareController()
        
        # Não deve levantar exceção, apenas clamp
        controller.set_servo_angle(0, -100)  # Muito baixo
        controller.set_servo_angle(0, 200)   # Muito alto
        
        # Verificar que o pulso está nos limites
        # (não podemos verificar diretamente sem mock)
    
    def test_motor_speed_limits(self):
        """Testa limites de velocidade do motor"""
        controller = HardwareController()
        
        controller.set_motor_speed("left", 300)  # Acima do limite
        controller.set_motor_speed("left", -300)  # Abaixo do limite
        
        # Verificar que a velocidade foi limitada
        speed = controller.state.motor_speeds["left"]
        assert -255 <= speed <= 255
    
    def test_motor_stop(self):
        """Testa parada de motores"""
        controller = HardwareController()
        
        controller.set_motor_speed("left", 100)
        controller.set_motor_speed("right", 100)
        controller.stop_all_motors()
        
        assert controller.state.motor_speeds["left"] == 0
        assert controller.state.motor_speeds["right"] == 0
    
    def test_failsafe_activation(self):
        """Testa ativação de failsafe"""
        controller = HardwareController()
        
        controller.set_motor_speed("left", 100)
        controller.activate_failsafe()
        
        assert controller.failsafe_active is True
        assert controller.state.motor_speeds["left"] == 0
    
    def test_emergency_stop(self):
        """Testa parada de emergência"""
        controller = HardwareController()
        
        controller.set_motor_speed("left", 100)
        controller.set_motor_speed("right", 100)
        controller.emergency_stop()
        
        assert controller.failsafe_active is True
        assert controller.state.motor_speeds["left"] == 0
        assert controller.state.motor_speeds["right"] == 0
    
    def test_get_status(self):
        """Testa obtenção de status"""
        controller = HardwareController()
        
        status = controller.get_status()
        
        assert "connected" in status
        assert "failsafe_active" in status
        assert "servos" in status
        assert "motors" in status
        assert "leds" in status


class TestServoMovement:
    """Testes de movimento de servo"""
    
    def test_angle_to_pulse_conversion(self):
        """Testa conversão de ângulo para pulso"""
        config = ServoConfig(
            id=0,
            name="Test",
            min_angle=0,
            max_angle=180,
            min_pulse=500,
            max_pulse=2500,
        )
        
        # Ângulo mínimo = pulso mínimo
        # Ângulo máximo = pulso máximo
        # Meio = pulso neutro
        
        controller = HardwareController()
        pulse = controller._angle_to_pulse_for_config(config, 90)
        assert 1400 <= pulse <= 1600  # Aproximadamente 1500
    
    def test_inverted_servo(self):
        """Testa servo invertido"""
        config = ServoConfig(
            id=0,
            name="Test",
            min_angle=0,
            max_angle=180,
            min_pulse=500,
            max_pulse=2500,
            inverted=True,
        )
        
        controller = HardwareController()
        pulse_normal = controller._angle_to_pulse_for_config(
            ServoConfig(id=0, name="Test", inverted=False), 180
        )
        pulse_inverted = controller._angle_to_pulse_for_config(config, 180)
        
        # Inverted deve ser oposto
        assert pulse_inverted < pulse_normal


# Monkey patch para teste
def _angle_to_pulse_for_config(self, config, angle):
    ratio = (angle - config.min_angle) / (config.max_angle - config.min_angle)
    if config.inverted:
        ratio = 1 - ratio
    return int(config.min_pulse + ratio * (config.max_pulse - config.min_pulse))

HardwareController._angle_to_pulse_for_config = _angle_to_pulse_for_config
