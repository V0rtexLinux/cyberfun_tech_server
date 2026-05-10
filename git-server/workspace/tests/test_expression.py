"""
================================================================================
TESTES DE EXPRESSÃO FACIAL
================================================================================
"""

import pytest
import time
import numpy as np
from core.expression.facial_controller import (
    FacialExpressionController,
    EmotionPreset,
    FacialPosition,
    ServoController,
    ServoConfig,
    EasingFunctions,
)


class TestEasingFunctions:
    """Testes de funções de easing"""
    
    def test_linear_easing(self):
        """Testa easing linear"""
        assert EasingFunctions.linear(0) == 0
        assert EasingFunctions.linear(0.5) == 0.5
        assert EasingFunctions.linear(1) == 1
    
    def test_ease_in_out(self):
        """Testa ease in-out"""
        assert EaseOut.ease_in_out(0) == 0
        assert EaseOut.ease_in_out(1) == 1
        # Meio deve ser ~0.5
        mid = EasingFunctions.ease_in_out(0.5)
        assert 0.4 <= mid <= 0.6
    
    def test_ease_bounce_bounds(self):
        """Testa bounce mantém bounds"""
        for t in [0, 0.25, 0.5, 0.75, 1.0]:
            result = EasingFunctions.ease_bounce(t)
            assert 0 <= result <= 1 or abs(result) < 0.1  # Pode ter pequeno overshoot


class TestServoController:
    """Testes do controlador de servo individual"""
    
    def test_servo_initialization(self, test_servo_config):
        """Testa inicialização de servo"""
        servo = ServoController(test_servo_config)
        
        assert servo.get_angle() == test_servo_config.neutral_angle
        assert servo.get_pulse() == test_servo_config.neutral_pulse
    
    def test_servo_angle_limits(self, test_servo_config):
        """Testa limites de ângulo"""
        servo = ServoController(test_servo_config)
        
        servo.set_angle(-50)  # Abaixo do mínimo
        assert servo.state.target_angle >= test_servo_config.min_angle
        
        servo.set_angle(100)  # Acima do máximo
        assert servo.state.target_angle <= test_servo_config.max_angle
    
    def test_servo_update(self, test_servo_config):
        """Testa atualização de posição"""
        servo = ServoController(test_servo_config)
        
        servo.set_angle(30)
        
        # Simular múltiplos ciclos de update
        for _ in range(100):
            servo.update(0.01)
        
        # Deveria ter chegado perto do target
        assert abs(servo.get_angle() - 30) < 1.0
    
    def test_immediate_move(self, test_servo_config):
        """Testa movimento imediato"""
        servo = ServoController(test_servo_config)
        
        servo.set_angle(30, immediate=True)
        
        assert servo.get_angle() == 30
        assert servo.state.current_pulse == servo._angle_to_pulse(30)


class TestFacialExpressionController:
    """Testes do controlador de expressão facial"""
    
    def test_controller_initialization(self):
        """Testa inicialização do controlador"""
        controller = FacialExpressionController()
        
        assert len(controller.servos) == 7
        assert controller.SERVO_JAW == 0
        assert controller.SERVO_EYE_X == 3
        assert controller.SERVO_EYE_Y == 4
    
    def test_emotion_presets_exist(self):
        """Testa que presets de emoção existem"""
        controller = FacialExpressionController()
        
        expected_emotions = [
            EmotionPreset.NEUTRAL,
            EmotionPreset.HAPPY,
            EmotionPreset.EXCITED,
            EmotionPreset.SURPRISED,
            EmotionPreset.SAD,
            EmotionPreset.ANGRY,
            EmotionPreset.WINK,
            EmotionPreset.BLINK,
            EmotionPreset.TALKING,
            EmotionPreset.SINGING,
            EmotionPreset.LAUGHING,
            EmotionPreset.SLEEPY,
        ]
        
        for emotion in expected_emotions:
            assert emotion in controller.emotion_presets
    
    def test_set_emotion(self):
        """Testa aplicação de emoção"""
        controller = FacialExpressionController()
        
        controller.set_emotion(EmotionPreset.HAPPY)
        
        # Verificar que transition foi criada
        assert controller.transition is not None
        assert controller.transition.end_expression == controller.emotion_presets[EmotionPreset.HAPPY]
    
    def test_look_at(self):
        """Testa movimento ocular"""
        controller = FacialExpressionController()
        
        controller.look_at(30, 15)
        
        assert controller.current_expression.eye_x == 30
        assert controller.current_expression.eye_y == 15
    
    def test_look_at_limits(self):
        """Testa limites de movimento ocular"""
        controller = FacialExpressionController()
        
        controller.look_at(100, 100)  # Acima dos limites
        
        assert controller.current_expression.eye_x <= 45
        assert controller.current_expression.eye_y <= 30
    
    def test_open_jaw(self):
        """Testa abertura de mandíbula"""
        controller = FacialExpressionController()
        
        controller.open_jaw(30)
        
        assert controller.current_expression.jaw_angle == 30
    
    def test_jaw_limits(self):
        """Testa limites de mandíbula"""
        controller = FacialExpressionController()
        
        controller.open_jaw(100)  # Acima do limite
        
        assert controller.current_expression.jaw_angle <= 45
    
    def test_do_wink(self):
        """Testa piscadela"""
        controller = FacialExpressionController()
        
        controller.do_wink("right", duration=0.1)
        
        # Verificar que transition foi criada
        assert controller.transition is not None
    
    def test_lip_sync_toggle(self):
        """Testa ativação/desativação de lip-sync"""
        controller = FacialExpressionController()
        
        controller.start_lip_sync()
        assert controller.lip_sync_enabled is True
        
        controller.stop_lip_sync()
        assert controller.lip_sync_enabled is False
    
    def test_lerp(self):
        """Testa interpolação linear"""
        result = FacialExpressionController._lerp(0, 100, 0.5)
        assert result == 50
        
        result = FacialExpressionController._lerp(0, 100, 0)
        assert result == 0
        
        result = FacialExpressionController._lerp(0, 100, 1)
        assert result == 100
    
    def test_get_status(self):
        """Testa obtenção de status"""
        controller = FacialExpressionController()
        
        status = controller.get_status()
        
        assert "current_expression" in status
        assert "transition_active" in status
        assert "auto_blink_enabled" in status
        assert "lip_sync_enabled" in status
        assert "servo_angles" in status


class TestFacialPosition:
    """Testes de posição facial"""
    
    def test_default_position(self):
        """Testa posição padrão"""
        pos = FacialPosition()
        
        assert pos.jaw_angle == 0
        assert pos.left_eyelid == 100
        assert pos.right_eyelid == 100
        assert pos.eye_x == 0
        assert pos.eye_y == 0
        assert pos.left_ear == 0
        assert pos.right_ear == 0
    
    def test_custom_position(self):
        """Testa posição customizada"""
        pos = FacialPosition(
            jaw_angle=20,
            left_eyelid=80,
            right_eyelid=80,
            eye_x=15,
            eye_y=-10,
            left_ear=10,
            right_ear=10,
        )
        
        assert pos.jaw_angle == 20
        assert pos.left_eyelid == 80
        assert pos.eye_x == 15
        assert pos.eye_y == -10
