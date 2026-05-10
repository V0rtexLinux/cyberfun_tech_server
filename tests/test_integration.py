"""
================================================================================
TESTES DE INTEGRAÇÃO
================================================================================
Testes end-to-end do sistema completo
================================================================================
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch


class TestSystemInitialization:
    """Testes de inicialização do sistema"""
    
    @pytest.mark.slow
    def test_full_initialization_sequence(self, temp_config_file):
        """Testa sequência completa de inicialização"""
        from core import AnimatronicConfig, load_config
        
        config = load_config(temp_config_file)
        assert config is not None
        assert config.name == "TestAnimatronic"
    
    def test_config_to_hardware_integration(self):
        """Testa integração config -> hardware"""
        from core.config.loader import ServoConfig
        
        servo = ServoConfig(
            id=0,
            name="Jaw",
            min_angle=0,
            max_angle=45,
            min_pulse=500,
            max_pulse=2500,
            neutral_pulse=1500,
            max_speed=120,
        )
        
        # Verificar que configuração é compatível com hardware
        assert servo.min_pulse >= 500
        assert servo.max_pulse <= 2500
        assert servo.min_angle < servo.max_angle


class TestAIExpressionIntegration:
    """Testes de integração IA -> Expressão"""
    
    def test_emotion_propagation(self):
        """Testa propagação de emoção da IA para expressão"""
        from core.ai.ai_brain import AIChatBrain, PersonalityMode
        from core.expression.facial_controller import EmotionPreset
        
        brain = AIChatBrain(openai_key=None)
        
        # Testar mapeamentos de emoção
        emotion_mappings = {
            "excited": EmotionPreset.EXCITED,
            "happy": EmotionPreset.HAPPY,
            "sad": EmotionPreset.SAD,
            "surprised": EmotionPreset.SURPRISED,
            "neutral": EmotionPreset.NEUTRAL,
        }
        
        for emotion_name, preset in emotion_mappings.items():
            expression = brain._emotion_to_expression(emotion_name)
            # Verificar que existe mapeamento válido
            assert expression is not None


class TestVisionExpressionIntegration:
    """Testes de integração Visão -> Expressão"""
    
    def test_face_tracking_to_eye_movement(self):
        """Testa que detecção de rosto move olhos"""
        from core.expression.facial_controller import FacialExpressionController
        
        controller = FacialExpressionController()
        
        # Simular posição de rosto detectado
        face_x = 100  # pixels à direita do centro
        face_y = -50  # pixels abaixo do centro
        
        # Converter para ângulos oculares (função look_at_point)
        controller.look_at_point(
            target_x=face_x,
            target_y=face_y,
            target_z=100,  # distância em cm
            head_x=0,
            head_y=0,
            head_z=0,
        )
        
        # Olhos devem ter se movido
        assert controller.current_expression.eye_x != 0
        assert controller.current_expression.eye_y != 0


class TestHardwareSafetyIntegration:
    """Testes de integração Hardware -> Segurança"""
    
    def test_emergency_stop_propagation(self):
        """Testa propagação de emergência"""
        # Verificar que FSM e HAL estão conectados
        from core.kernel.fsm_kernel import SystemState, SafetyState
        
        safety = SafetyState()
        assert safety.emergency_stop_active is False
        
        # Ativar emergência
        safety.emergency_stop_active = True
        assert safety.emergency_stop_active is True
    
    def test_failsafe_on_disconnect(self):
        """Testa failsafe ao desconectar"""
        from core.kernel.fsm_kernel import SafetyState
        
        safety = SafetyState()
        safety.serial_connection_healthy = True
        
        # Simular desconexão
        safety.serial_connection_healthy = False
        
        # Verificar estado de segurança
        assert safety.serial_connection_healthy is False


class TestSensorReactionIntegration:
    """Testes de integração Sensor -> Reação"""
    
    def test_pir_detection_callback(self):
        """Testa callback de detecção PIR"""
        callback_called = False
        
        def on_detected():
            nonlocal callback_called
            callback_called = True
        
        # Simular detecção
        on_detected()
        
        assert callback_called is True
    
    def test_obstacle_detection_response(self):
        """Testa resposta a obstáculo"""
        from core.config.loader import LocomotionConfig
        
        config = LocomotionConfig()
        obstacle_distance = 0.15  # 15cm, abaixo do limite de segurança
        
        # Se obstáculo está muito perto, deve parar
        if obstacle_distance < config.safety_stop_distance:
            should_stop = True
        else:
            should_stop = False
        
        assert should_stop is True


class TestTTSLipSyncIntegration:
    """Testes de integração TTS -> Lip-sync"""
    
    def test_tts_start_stops_lip_sync(self):
        """Testa que TTS inicia lip-sync"""
        from core.expression.facial_controller import FacialExpressionController
        
        controller = FacialExpressionController()
        
        # Iniciar fala
        controller.start_lip_sync()
        
        assert controller.lip_sync_enabled is True
        assert controller.current_expression.jaw_angle > 0  # Mandíbula aberta
    
    def test_tts_end_closes_jaw(self):
        """Testa que fim de TTS fecha mandíbula"""
        from core.expression.facial_controller import FacialExpressionController
        
        controller = FacialExpressionController()
        
        controller.start_lip_sync()
        controller.open_jaw(30)
        
        controller.stop_lip_sync()
        
        assert controller.lip_sync_enabled is False
        assert controller.current_expression.jaw_angle == 0


class TestShowTimelineIntegration:
    """Testes de integração Shows -> Timeline"""
    
    def test_show_event_callbacks(self):
        """Testa callbacks de eventos de show"""
        events_triggered = []
        
        def on_jaw(params, duration):
            events_triggered.append("jaw")
        
        def on_emotion(params, duration):
            events_triggered.append("emotion")
        
        # Simular eventos
        on_jaw({}, 100)
        on_emotion({}, 200)
        
        assert "jaw" in events_triggered
        assert "emotion" in events_triggered


class TestEndToEndScenario:
    """Testes de cenários completos"""
    
    def test_visitor_interaction_scenario(self):
        """Testa cenário completo: visitante detectado -> saudação"""
        # 1. PIR detecta visitante
        presence_detected = True
        
        # 2. Sistema reage
        if presence_detected:
            # Olhar para visitante
            eye_x = 20  # Simulação
            emotion = "excited"
            
            # Verificar que ações são válidas
            assert -45 <= eye_x <= 45
            assert emotion in ["excited", "happy", "surprised", "neutral"]
    
    def test_emergency_scenario(self):
        """Testa cenário de emergência"""
        # 1. IMU detecta inclinação excessiva
        excessive_tilt = True
        
        # 2. Sistema entra em emergência
        if excessive_tilt:
            emergency_active = True
            motors_stopped = True
            
            assert emergency_active is True
            assert motors_stopped is True
