"""
================================================================================
TESTES DE CONFIGURAÇÃO
================================================================================
"""

import pytest
import os
import tempfile
import yaml
from core.config.loader import (
    AnimatronicConfig,
    ServoConfig,
    load_config,
    save_config,
    get_fredbear_default_config,
    get_springbonnie_default_config,
)


class TestServoConfig:
    """Testes de configuração de servo"""
    
    def test_servo_config_creation(self):
        """Testa criação de configuração de servo"""
        servo = ServoConfig(
            id=0,
            name="Jaw",
            min_angle=0.0,
            max_angle=45.0,
            max_speed=120.0,
        )
        assert servo.id == 0
        assert servo.name == "Jaw"
        assert servo.min_angle == 0.0
        assert servo.max_angle == 45.0
        assert servo.max_speed == 120.0
        assert not servo.inverted
    
    def test_servo_default_values(self):
        """Testa valores padrão do servo"""
        servo = ServoConfig(id=1, name="Test")
        assert servo.min_pulse == 500
        assert servo.max_pulse == 2500
        assert servo.neutral_pulse == 1500


class TestConfigLoader:
    """Testes de carregamento de configuração"""
    
    def test_load_config_from_yaml(self, temp_config_file):
        """Testa carregamento de arquivo YAML"""
        config = load_config(temp_config_file)
        
        assert isinstance(config, AnimatronicConfig)
        assert config.name == "TestAnimatronic"
        assert config.version == "3.1.0"
        assert len(config.hardware) == 1
        assert "TestServo" in config.hardware
    
    def test_load_config_sensors(self, temp_config_file):
        """Testa carregamento de configuração de sensores"""
        config = load_config(temp_config_file)
        
        assert config.sensors.pir_pin == 17
        assert config.sensors.ultrasonic_trigger == 23
        assert config.sensors.ultrasonic_echo == 24
        assert config.sensors.imu_i2c_addr == 0x68
    
    def test_load_config_ai(self, temp_config_file):
        """Testa carregamento de configuração de IA"""
        config = load_config(temp_config_file)
        
        assert config.ai.backend_priority == ["fallback"]
        assert config.ai.max_tokens == 50
        assert config.ai.temperature == 0.5
    
    def test_save_and_load_config(self):
        """Testa salvar e recarregar configuração"""
        config = get_fredbear_default_config()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_path = f.name
        
        try:
            save_config(config, temp_path)
            loaded = load_config(temp_path)
            
            assert loaded.name == config.name
            assert loaded.personality.name == config.personality.name
            assert len(loaded.personality.greetings) > 0
        finally:
            os.unlink(temp_path)


class TestDefaultConfigs:
    """Testes de configurações padrão"""
    
    def test_fredbear_default_config(self):
        """Testa configuração padrão do Fredbear"""
        config = get_fredbear_default_config()
        
        assert config.name == "Fredbear"
        assert config.personality.name == "Fredbear"
        assert config.personality.character_type == "golden_bear"
        assert "pizzaria" in config.personality.system_prompt.lower()
        assert len(config.personality.greetings) > 0
        assert len(config.personality.jokes) > 0
    
    def test_springbonnie_default_config(self):
        """Testa configuração padrão do Springbonnie"""
        config = get_springbonnie_default_config()
        
        assert config.name == "Springbonnie"
        assert config.personality.name == "Springbonnie"
        assert config.personality.character_type == "rabbit"
        assert "coelho" in config.personality.system_prompt.lower()
        assert len(config.personality.greetings) > 0
        assert len(config.personality.jokes) > 0
    
    def test_different_personalities(self):
        """Testa que personalidades são diferentes"""
        fredbear = get_fredbear_default_config()
        springbonnie = get_springbonnie_default_config()
        
        assert fredbear.personality.name != springbonnie.personality.name
        assert fredbear.personality.character_type != springbonnie.personality.character_type
        assert fredbear.personality.system_prompt != springbonnie.personality.system_prompt


class TestConfigValidation:
    """Testes de validação de configuração"""
    
    def test_invalid_servo_angles(self):
        """Testa que ângulos de servo são validados"""
        servo = ServoConfig(id=0, name="Test", min_angle=-90, max_angle=90)
        assert servo.min_angle == -90
        assert servo.max_angle == 90
    
    def test_pulse_range_validation(self):
        """Testa faixa de pulso PWM"""
        servo = ServoConfig(id=0, name="Test")
        assert 500 <= servo.min_pulse <= servo.max_pulse <= 2500
        assert servo.neutral_pulse == 1500
