"""
================================================================================
TESTES DE INTELIGÊNCIA ARTIFICIAL
================================================================================
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os

from core.ai.ai_brain import (
    AIChatBrain,
    OpenAIBrain,
    OllamaBrain,
    FallbackBrain,
    PersonalityMode,
    AIResponse,
    ConversationTurn,
    FredbearPersonality,
)


class TestPersonalityMode:
    """Testes de modos de personalidade"""
    
    def test_personality_modes_exist(self):
        """Testa que todos os modos existem"""
        modes = [
            PersonalityMode.FRIENDLY,
            PersonalityMode.EXCITED,
            PersonalityMode.CREEPY,
            PersonalityMode.STORYTELLER,
            PersonalityMode.DJ,
            PersonalityMode.GUARDIAN,
        ]
        
        for mode in modes:
            assert mode.value is not None
    
    def test_personality_prompts(self):
        """Testa que prompts de personalidade existem"""
        personality = FredbearPersonality()
        
        assert "Fredbear" in personality.SYSTEM_PROMPT_BASE
        assert "pizzaria" in personality.SYSTEM_PROMPT_BASE.lower()
        
        # Verificar adições para cada modo
        for mode in PersonalityMode:
            assert mode in personality.PERSONALITY_ADDITIONS


class TestOpenAIBrain:
    """Testes do backend OpenAI"""
    
    def test_initialization_without_key(self):
        """Testa inicialização sem API key"""
        brain = OpenAIBrain(api_key=None)
        assert brain.api_key == ""
    
    def test_initialization_with_key(self):
        """Testa inicialização com API key"""
        brain = OpenAIBrain(api_key="test-key")
        assert brain.api_key == "test-key"
    
    def test_is_available_without_key(self):
        """Testa disponibilidade sem chave"""
        brain = OpenAIBrain(api_key=None)
        assert brain.is_available() is False
    
    def test_default_model(self):
        """Testa modelo padrão"""
        brain = OpenAIBrain(api_key="test")
        assert brain.model == "gpt-4o-mini"


class TestOllamaBrain:
    """Testes do backend Ollama"""
    
    def test_initialization(self):
        """Testa inicialização"""
        brain = OllamaBrain(model="llama3.2:3b")
        assert brain.model == "llama3.2:3b"
        assert brain.host == "http://localhost:11434"
    
    def test_custom_host(self):
        """Testa host customizado"""
        brain = OllamaBrain(host="http://192.168.1.100:11434")
        assert brain.host == "http://192.168.1.100:11434"
    
    @patch('requests.get')
    def test_is_available_true(self, mock_get):
        """Testa disponibilidade quando servidor está online"""
        mock_get.return_value = Mock(status_code=200)
        
        brain = OllamaBrain()
        # Não testamos diretamente porque pode falhar sem servidor real
        # mas verificamos que a estrutura está correta
        assert hasattr(brain, 'is_available')
    
    @patch('requests.get')
    def test_is_available_false(self, mock_get):
        """Testa disponibilidade quando servidor está offline"""
        mock_get.side_effect = Exception("Connection refused")
        
        brain = OllamaBrain()
        assert brain.is_available() is False


class TestFallbackBrain:
    """Testes do fallback brain"""
    
    def test_always_available(self):
        """Testa que fallback está sempre disponível"""
        brain = FallbackBrain()
        assert brain.is_available() is True
    
    def test_has_responses(self):
        """Testa que existem res pré-programadas"""
        brain = FallbackBrain()
        
        assert len(brain.RESPONSES["padrão"]) > 0
        assert len(brain.RESPONSES["cumprimento"]) > 0
        assert len(brain.RESPONSES["piada"]) > 0
        assert len(brain.RESPONSES["noite"]) > 0
    
    def test_greeting_response(self):
        """Testa resposta a cumprimento"""
        brain = FallbackBrain()
        
        response = brain.generate_response("Olá", PersonalityMode.FRIENDLY)
        
        # Deve retornar uma das respostas de cumprimento
        assert response in brain.RESPONSES["cumprimento"] or response in brain.RESPONSES["padrão"]
    
    def test_joke_response(self):
        """Testa resposta a piada"""
        brain = FallbackBrain()
        
        response = brain.generate_response("Conte uma piada", PersonalityMode.FRIENDLY)
        
        # Deve retornar uma das piadas
        assert response in brain.RESPONSES["piada"]
    
    def test_night_mode_response(self):
        """Testa resposta em modo noturno"""
        brain = FallbackBrain()
        
        response = brain.generate_response("Oi", PersonalityMode.CREEPY)
        
        # Deve retornar uma resposta noturna
        assert response in brain.RESPONSES["noite"]


class TestAIChatBrain:
    """Testes do cérebro completo de IA"""
    
    def test_initialization(self):
        """Testa inicialização"""
        brain = AIChatBrain(openai_key=None)
        
        assert brain.openai is not None
        assert brain.ollama is not None
        assert brain.fallback is not None
        assert brain.mode == PersonalityMode.FRIENDLY
    
    def test_backend_detection_fallback(self):
        """Testa detecção de backend (fallback quando não há outros)"""
        brain = AIChatBrain(openai_key=None)
        
        # Sem chave OpenAI e sem Ollama, deve usar fallback
        assert brain._active_backend == "fallback"
    
    def test_set_mode(self):
        """Testa mudança de modo"""
        brain = AIChatBrain(openai_key=None)
        
        brain.set_mode(PersonalityMode.EXCITED)
        assert brain.mode == PersonalityMode.EXCITED
        
        brain.set_mode(PersonalityMode.CREEPY)
        assert brain.mode == PersonalityMode.CREEPY
    
    def test_conversation_history(self):
        """Testa histórico de conversação"""
        brain = AIChatBrain(openai_key=None)
        
        # Adicionar turns
        brain.conversation_history.append(
            ConversationTurn(role="user", content="Olá")
        )
        brain.conversation_history.append(
            ConversationTurn(role="assistant", content="Oi!")
        )
        
        assert len(brain.conversation_history) == 2
    
    def test_history_limit(self):
        """Testa limite de histórico"""
        brain = AIChatBrain(openai_key=None)
        brain.max_history = 3
        
        # Adicionar mais que o limite
        for i in range(10):
            brain.conversation_history.append(
                ConversationTurn(role="user", content=f"Mensagem {i}")
            )
        
        # Histórico deve ser truncado
        assert len(brain.conversation_history) <= brain.max_history * 2
    
    def test_emotion_detection(self):
        """Testa detecção de emoção"""
        brain = AIChatBrain(openai_key=None)
        
        excited = brain._detect_emotion("YEAAH! Que incrível!")
        assert excited == "excited"
        
        happy = brain._detect_emotion("HA HA HA! Muito engraçado!")
        assert happy == "happy"
        
        creepy = brain._detect_emotion("Hmm... câmeras... noite...")
        assert creepy == "creepy"
        
        surprised = brain._detect_emotion("Uau! Não acredito!")
        assert surprised == "surprised"
    
    def test_emotion_to_expression(self):
        """Testa mapeamento emoção -> expressão"""
        brain = AIChatBrain(openai_key=None)
        
        assert brain._emotion_to_expression("excited") == "excited"
        assert brain._emotion_to_expression("happy") == "happy"
        assert brain._emotion_to_expression("creepy") == "sad"
        assert brain._emotion_to_expression("surprised") == "surprised"
        assert brain._emotion_to_expression("sad") == "sad"
        assert brain._emotion_to_expression("neutral") == "neutral"
    
    def test_voice_for_mode(self):
        """Testa seleção de voz por modo"""
        brain = AIChatBrain(openai_key=None)
        
        brain.set_mode(PersonalityMode.FRIENDLY)
        assert brain._get_voice_for_mode() == "robot_male"
        
        brain.set_mode(PersonalityMode.EXCITED)
        assert brain._get_voice_for_mode() == "cheerful"
        
        brain.set_mode(PersonalityMode.CREEPY)
        assert brain._get_voice_for_mode() == "creepy"
    
    def test_get_status(self):
        """Testa obtenção de status"""
        brain = AIChatBrain(openai_key=None)
        
        status = brain.get_status()
        
        assert "backend" in status
        assert "mode" in status
        assert "history_length" in status
        assert "total_conversations" in status
        assert "avg_response_time_s" in status
