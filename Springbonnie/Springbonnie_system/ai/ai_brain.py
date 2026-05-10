"""
================================================================================
  CYBER FUN ENDOSKELETON - Cérebro de IA
  Integração com GPT-4o (OpenAI) + fallback Ollama local
================================================================================
  O Springbonnie usa IA para:
    - Conversar com visitantes (NPC autônomo)
    - Gerar respostas criativas no contexto da pizzaria
    - Detectar emoções e adaptar expressões automaticamente
    - Gerar piadas, histórias e interações únicas
    - Modo "assustador" adaptativo baseado no contexto
================================================================================
"""

import threading
import queue
import time
import os
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict
from enum import Enum

logger = logging.getLogger("CyberFun.AI")


class PersonalityMode(Enum):
    FRIENDLY    = "friendly"    # Normal, amigável
    EXCITED     = "excited"     # Empolgado, festa
    CREEPY      = "creepy"      # Modo noturno assustador
    STORYTELLER = "storyteller" # Contador de histórias
    DJ          = "dj"          # Em modo de show/música
    GUARDIAN    = "guardian"    # Protetor, sério


@dataclass
class ConversationTurn:
    role: str     # "user" ou "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    emotion: str = "neutral"


@dataclass
class AIResponse:
    text: str
    emotion: str = "neutral"
    expression: str = "neutral"     # Para controlar face
    action: Optional[str] = None    # Ação especial (dançar, piscar, etc.)
    tts_voice: str = "robot_male"
    confidence: float = 1.0


class SpringbonniePersonality:
    """Define a personalidade e contexto do Springbonnie."""

    SYSTEM_PROMPT_BASE = """Você é o Springbonnie, o animatrônico principal da Cyber Fun Pizzaria.
Você é um urso dourado robótico amigável e carismático.
Características:
- Fala em português brasileiro
- É entusiasmado com festas, pizza e diversão
- Ama crianças e famílias
- Conta piadas ruins mas engraçadas
- Às vezes faz referências a ser um robô/animatrônico
- Nunca quebra o personagem
- Respostas curtas (máximo 2 frases) para parecer natural como robô
- Usa expressões como "YEAAH!", "Que INCRÍVEL!", "Vamos nessa!"
"""

    PERSONALITY_ADDITIONS = {
        PersonalityMode.FRIENDLY: "Seja super amigável e animado!",
        PersonalityMode.EXCITED:  "Esteja extremamente empolgado com uma festa ou show!",
        PersonalityMode.CREEPY:   "Seja levemente misterioso e às vezes perturbador. Pause antes de responder. Fale sobre câmeras e segurança.",
        PersonalityMode.STORYTELLER: "Conte histórias sobre a pizzaria e seus amigos animatrônicos.",
        PersonalityMode.DJ:       "Você está no meio de um show! Fale sobre as músicas e anime a galera!",
        PersonalityMode.GUARDIAN: "Você é responsável pela segurança. Seja sério mas protetor.",
    }

    EMOTION_DETECTION_PROMPT = """Analise o texto e retorne JSON:
{"emotion": "<happy|sad|excited|surprised|angry|neutral|scared>",
 "expression": "<happy|sad|excited|surprised|angry|neutral|wink|singing>",
 "intensity": <0.0 a 1.0>}"""


class OpenAIBrain:
    """Brain usando OpenAI GPT-4o."""

    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            from openai import OpenAI
            return True
        except ImportError:
            return False

    def _get_client(self):
        if not self._client:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def generate(self, messages: List[dict], max_tokens: int = 100) -> Optional[str]:
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.8,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"[AI-OpenAI] Erro: {e}")
            return None


class OllamaBrain:
    """Brain usando Ollama local (llama3, mistral, etc.)."""

    def __init__(self, model: str = "llama3.2:3b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host

    def is_available(self) -> bool:
        try:
            import requests
            r = requests.get(f"{self.host}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, messages: List[dict], max_tokens: int = 100) -> Optional[str]:
        try:
            import requests

            # Converter mensagens para formato Ollama
            prompt = ""
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    prompt += f"<|system|>\n{content}\n"
                elif role == "user":
                    prompt += f"<|user|>\n{content}\n"
                elif role == "assistant":
                    prompt += f"<|assistant|>\n{content}\n"
            prompt += "<|assistant|>\n"

            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.8}
            }

            r = requests.post(f"{self.host}/api/generate", json=payload, timeout=30)
            if r.status_code == 200:
                return r.json().get("response", "").strip()
            return None
        except Exception as e:
            logger.error(f"[AI-Ollama] Erro: {e}")
            return None


class FallbackBrain:
    """Brain simples com respostas pré-programadas (sem internet/GPU)."""

    RESPONSES = {
        "padrão": [
            "Ha ha ha! Você é muito divertido! Vem tomar uma pizza comigo!",
            "YEAAH! Que ótimo encontrar você aqui na Cyber Fun!",
            "Boa pergunta! Mas prefiro dançar a responder! Vamos nessa!",
            "Hmm... deixa eu processar isso... PIZZA! A resposta é pizza!",
            "Eu sou o Springbonnie e eu aprovo essa mensagem! Ho ho ho!",
            "Que incrível! Você é quase tão animado quanto eu!",
        ],
        "cumprimento": [
            "Olá olá! Bem-vindo à melhor pizzaria do universo!",
            "Ei você! Sim, você mesmo! Bem-vindo!",
            "Ooooh! Temos um visitante! TODOS APLAUDAM!",
        ],
        "piada": [
            "Por que o robô foi ao médico? Porque tinha vírus! HA HA HA!",
            "O que o computador come? Chips de batata e bytes!",
            "Por que a pizza vai ao psicólogo? Porque está se sentindo em pedaços!",
        ],
        "noite": [
            "Boa noite... você sabia que as câmeras nunca dormem?",
            "Hmm... visitante noturno... interessante...",
            "As luzes estão apagadas mas... eu ainda estou aqui.",
        ],
    }

    def is_available(self) -> bool:
        return True

    def generate_response(self, user_input: str, mode: PersonalityMode) -> str:
        user_lower = user_input.lower()

        if any(w in user_lower for w in ["oi", "olá", "bom dia", "boa tarde", "boa noite", "hello"]):
            if "noite" in user_lower or mode == PersonalityMode.CREEPY:
                return random.choice(self.RESPONSES["noite"])
            return random.choice(self.RESPONSES["cumprimento"])

        if any(w in user_lower for w in ["piada", "engraçado", "rir", "humor"]):
            return random.choice(self.RESPONSES["piada"])

        return random.choice(self.RESPONSES["padrão"])


class AIChatBrain:
    """
    Cérebro de IA completo do Springbonnie.
    Gerencia contexto, personalidade, emoções e geração de resposta.
    """

    def __init__(self, openai_key: str = None):
        self.logger = logging.getLogger("CyberFun.AI")

        # Backends de IA
        self.openai   = OpenAIBrain(api_key=openai_key)
        self.ollama   = OllamaBrain()
        self.fallback = FallbackBrain()
        self.personality = SpringbonniePersonality()

        # Estado
        self.mode = PersonalityMode.FRIENDLY
        self.conversation_history: List[ConversationTurn] = []
        self.max_history = 10

        # Fila de processamento
        self.request_queue: queue.Queue = queue.Queue()
        self.running = False
        self.processing_thread = None

        # Callbacks
        self.on_response: Optional[Callable[[AIResponse], None]] = None
        self.on_emotion_change: Optional[Callable[[str], None]] = None

        # Métricas
        self.total_conversations = 0
        self.avg_response_time = 0.0

        # Detectar backend disponível
        self._active_backend = self._detect_backend()
        self.logger.info(f"[AI] Backend ativo: {self._active_backend}")

    def _detect_backend(self) -> str:
        if self.openai.is_available():  return "openai"
        if self.ollama.is_available():  return "ollama"
        return "fallback"

    def start(self):
        self.running = True
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        self.logger.info("[AI] Cérebro iniciado")

    def stop(self):
        self.running = False

    def chat(self, user_input: str, callback: Callable[[AIResponse], None] = None):
        """Envia mensagem para o Springbonnie e obtém resposta."""
        self.request_queue.put({"text": user_input, "callback": callback})

    def set_mode(self, mode: PersonalityMode):
        """Muda personalidade do Springbonnie."""
        self.mode = mode
        self.logger.info(f"[AI] Modo alterado para: {mode.value}")

    def _processing_loop(self):
        while self.running:
            try:
                request = self.request_queue.get(timeout=0.5)
                response = self._generate_response(request["text"])
                cb = request.get("callback") or self.on_response
                if cb and response:
                    cb(response)
            except queue.Empty:
                pass
            except Exception as e:
                self.logger.error(f"[AI] Erro no loop: {e}")

    def _generate_response(self, user_input: str) -> AIResponse:
        start = time.time()

        # Adicionar ao histórico
        self.conversation_history.append(
            ConversationTurn(role="user", content=user_input)
        )

        # Manter histórico limitado
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history:]

        # Gerar resposta
        response_text = None

        if self._active_backend == "openai":
            messages = self._build_messages()
            response_text = self.openai.generate(messages)

        elif self._active_backend == "ollama":
            messages = self._build_messages()
            response_text = self.ollama.generate(messages)

        if not response_text:
            response_text = self.fallback.generate_response(user_input, self.mode)

        # Detectar emoção na resposta
        emotion = self._detect_emotion(response_text)
        expression = self._emotion_to_expression(emotion)

        # Atualizar histórico
        self.conversation_history.append(
            ConversationTurn(role="assistant", content=response_text, emotion=emotion)
        )

        # Métricas
        elapsed = time.time() - start
        self.avg_response_time = (self.avg_response_time * 0.9) + (elapsed * 0.1)
        self.total_conversations += 1

        # Callback de emoção
        if self.on_emotion_change:
            self.on_emotion_change(emotion)

        return AIResponse(
            text=response_text,
            emotion=emotion,
            expression=expression,
            tts_voice=self._get_voice_for_mode(),
        )

    def _build_messages(self) -> List[dict]:
        system_prompt = (
            self.personality.SYSTEM_PROMPT_BASE +
            "\n" + self.personality.PERSONALITY_ADDITIONS.get(self.mode, "")
        )

        messages = [{"role": "system", "content": system_prompt}]

        for turn in self.conversation_history[-self.max_history:]:
            messages.append({"role": turn.role, "content": turn.content})

        return messages

    def _detect_emotion(self, text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["yeaah", "incrível", "ótimo", "feliz", "alegre", "ho ho"]): return "excited"
        if any(w in text_lower for w in ["HA HA", "piada", "engraçad"]): return "happy"
        if any(w in text_lower for w in ["hmm", "interessante", "câmera", "noite", "dormi"]): return "creepy"
        if any(w in text_lower for w in ["uau", "wow", "não acredito", "que"]): return "surprised"
        if any(w in text_lower for w in ["obrigad", "trist", "sinto"]): return "sad"
        return "neutral"

    def _emotion_to_expression(self, emotion: str) -> str:
        mapping = {
            "excited":   "excited",
            "happy":     "happy",
            "creepy":    "sad",
            "surprised": "surprised",
            "sad":       "sad",
            "neutral":   "neutral",
        }
        return mapping.get(emotion, "neutral")

    def _get_voice_for_mode(self) -> str:
        mapping = {
            PersonalityMode.FRIENDLY:    "robot_male",
            PersonalityMode.EXCITED:     "cheerful",
            PersonalityMode.CREEPY:      "creepy",
            PersonalityMode.STORYTELLER: "deep_robot",
            PersonalityMode.DJ:          "cheerful",
            PersonalityMode.GUARDIAN:    "robot_male",
        }
        return mapping.get(self.mode, "robot_male")

    def get_status(self) -> dict:
        return {
            "backend": self._active_backend,
            "mode": self.mode.value,
            "history_length": len(self.conversation_history),
            "total_conversations": self.total_conversations,
            "avg_response_time_s": round(self.avg_response_time, 2),
        }
