"""
================================================================================
  CYBER FUN ENDOSKELETON - Motor de Síntese de Voz (TTS)
  Suporte a múltiplos backends: pyttsx3, gTTS, espeak-ng, Coqui TTS
================================================================================
  O Springbonnie pode literalmente falar usando qualquer um dos engines:
    - espeak-ng     : offline, rápido, voz robótica (melhor para animatrônico)
    - pyttsx3       : offline, usa vozes do sistema (natural)
    - gTTS          : online, Google Text-to-Speech (melhor qualidade)
    - Coqui TTS     : offline, neural, qualidade excelente (requer GPU/CPU rápida)
================================================================================
"""

import threading
import queue
import time
import os
import subprocess
import tempfile
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable, List
from enum import Enum
import json

logger = logging.getLogger("CyberFun.TTS")


class TTSEngine(Enum):
    ESPEAK   = "espeak"
    PYTTSX3  = "pyttsx3"
    GTTS     = "gtts"
    COQUI    = "coqui"
    AUTO     = "auto"   # Escolhe melhor disponível


class TTSVoice(Enum):
    """Vozes predefinidas para o animatrônico"""
    ROBOT_MALE      = "robot_male"
    ROBOT_FEMALE    = "robot_female"
    CREEPY          = "creepy"
    DEEP_ROBOT      = "deep_robot"
    CHEERFUL        = "cheerful"
    SPOOKY          = "spooky"
    CHILD_ROBOT     = "child_robot"


@dataclass
class TTSRequest:
    text: str
    voice: TTSVoice = TTSVoice.ROBOT_MALE
    engine: TTSEngine = TTSEngine.AUTO
    speed: float = 1.0          # 0.5 = metade, 2.0 = dobro
    pitch: float = 1.0          # 0.5 = grave, 2.0 = agudo
    volume: float = 1.0
    priority: int = 5           # 0=máxima, 10=mínima
    callback: Optional[Callable] = None
    on_word: Optional[Callable] = None   # Chamado a cada palavra (lip-sync)
    language: str = "pt"


@dataclass
class PhonemeData:
    """Dado de fonema para lip-sync preciso"""
    timestamp_ms: int
    phoneme: str
    duration_ms: int
    mouth_openness: float   # 0.0 a 1.0


class EspeakEngine:
    """
    Engine espeak-ng: offline, voz robótica perfeita para animatrônico.
    Suporta SSML para controle preciso de entonação.
    """

    VOICE_PARAMS = {
        TTSVoice.ROBOT_MALE:   {"voice": "pt+m1", "speed": 140, "pitch": 40, "amplitude": 100, "gap": 8},
        TTSVoice.ROBOT_FEMALE: {"voice": "pt+f2", "speed": 145, "pitch": 65, "amplitude": 100, "gap": 8},
        TTSVoice.CREEPY:       {"voice": "pt+m3", "speed": 110, "pitch": 25, "amplitude": 80,  "gap": 15},
        TTSVoice.DEEP_ROBOT:   {"voice": "pt+m7", "speed": 120, "pitch": 10, "amplitude": 120, "gap": 10},
        TTSVoice.CHEERFUL:     {"voice": "pt+m2", "speed": 170, "pitch": 60, "amplitude": 100, "gap": 5},
        TTSVoice.SPOOKY:       {"voice": "pt+whisper", "speed": 100, "pitch": 30, "amplitude": 70, "gap": 20},
        TTSVoice.CHILD_ROBOT:  {"voice": "pt+f3", "speed": 180, "pitch": 90, "amplitude": 100, "gap": 5},
    }

    def is_available(self) -> bool:
        try:
            result = subprocess.run(["espeak-ng", "--version"], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def speak(self, request: TTSRequest) -> Optional[str]:
        """Fala o texto e retorna caminho do arquivo de áudio gerado."""
        params = self.VOICE_PARAMS.get(request.voice, self.VOICE_PARAMS[TTSVoice.ROBOT_MALE])

        # Ajustar velocidade/pitch com request
        speed = int(params["speed"] * request.speed)
        pitch = int(params["pitch"] * request.pitch)
        amplitude = int(params["amplitude"] * request.volume)

        # Arquivo de saída
        out_file = tempfile.mktemp(suffix=".wav")

        cmd = [
            "espeak-ng",
            "-v", params["voice"],
            "-s", str(speed),
            "-p", str(pitch),
            "-a", str(amplitude),
            "-g", str(params["gap"]),
            "-w", out_file,
            request.text
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and os.path.exists(out_file):
                logger.info(f"[TTS-espeak] Áudio gerado: {out_file}")
                return out_file
            else:
                logger.error(f"[TTS-espeak] Erro: {result.stderr.decode()}")
                return None
        except Exception as e:
            logger.error(f"[TTS-espeak] Exceção: {e}")
            return None

    def speak_immediate(self, request: TTSRequest):
        """Fala diretamente sem arquivo (mais rápido)."""
        params = self.VOICE_PARAMS.get(request.voice, self.VOICE_PARAMS[TTSVoice.ROBOT_MALE])
        speed = int(params["speed"] * request.speed)
        pitch = int(params["pitch"] * request.pitch)
        amplitude = int(params["amplitude"] * request.volume)

        cmd = [
            "espeak-ng",
            "-v", params["voice"],
            "-s", str(speed),
            "-p", str(pitch),
            "-a", str(amplitude),
            "-g", str(params["gap"]),
            request.text
        ]

        subprocess.Popen(cmd)

    def get_phonemes(self, text: str, voice: TTSVoice) -> List[PhonemeData]:
        """Extrai fonemas do texto para lip-sync preciso."""
        params = self.VOICE_PARAMS.get(voice, self.VOICE_PARAMS[TTSVoice.ROBOT_MALE])

        cmd = ["espeak-ng", "-v", params["voice"], "-x", "--ipa", text]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
            phonemes = []
            # Parsear saída de fonemas do espeak
            lines = result.stdout.strip().split('\n')
            t = 0
            for line in lines:
                for phoneme in line.strip().split():
                    openness = self._phoneme_to_openness(phoneme)
                    dur = 80  # ms estimado por fonema
                    phonemes.append(PhonemeData(t, phoneme, dur, openness))
                    t += dur
            return phonemes
        except Exception:
            return []

    def _phoneme_to_openness(self, phoneme: str) -> float:
        """Converte fonema para abertura de mandíbula (0-1)."""
        # Vogais abertas
        OPEN_VOWELS    = {'a', 'æ', 'ɐ', 'ɑ', 'ɶ'}
        MID_VOWELS     = {'e', 'ɛ', 'o', 'ɔ', 'ə'}
        CLOSED_VOWELS  = {'i', 'u', 'ɪ', 'ʊ', 'y'}
        CONSONANT_OPEN = {'m', 'b', 'p', 'v', 'f'}

        clean = phoneme.lower().strip("'ˈˌ")
        if any(v in clean for v in OPEN_VOWELS):    return 0.9
        if any(v in clean for v in MID_VOWELS):     return 0.6
        if any(v in clean for v in CLOSED_VOWELS):  return 0.3
        if any(c in clean for c in CONSONANT_OPEN): return 0.2
        return 0.1


class Pyttsx3Engine:
    """Engine pyttsx3: offline, usa vozes do sistema operacional."""

    def is_available(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False

    def speak(self, request: TTSRequest) -> Optional[str]:
        try:
            import pyttsx3
            engine = pyttsx3.init()

            voices = engine.getProperty('voices')
            pt_voices = [v for v in voices if 'pt' in v.languages or 'brazil' in v.name.lower()]

            if pt_voices:
                engine.setProperty('voice', pt_voices[0].id)

            rate = int(200 * request.speed)
            engine.setProperty('rate', rate)
            engine.setProperty('volume', request.volume)

            out_file = tempfile.mktemp(suffix=".wav")
            engine.save_to_file(request.text, out_file)
            engine.runAndWait()

            return out_file if os.path.exists(out_file) else None
        except Exception as e:
            logger.error(f"[TTS-pyttsx3] Erro: {e}")
            return None


class GTTSEngine:
    """Engine gTTS: Google Text-to-Speech (requer internet)."""

    def is_available(self) -> bool:
        try:
            from gtts import gTTS
            return True
        except ImportError:
            return False

    def speak(self, request: TTSRequest) -> Optional[str]:
        try:
            from gtts import gTTS
            import io

            tts = gTTS(text=request.text, lang=request.language, slow=(request.speed < 0.8))
            out_file = tempfile.mktemp(suffix=".mp3")
            tts.save(out_file)
            return out_file
        except Exception as e:
            logger.error(f"[TTS-gTTS] Erro: {e}")
            return None


class AudioPlayer:
    """Reprodutor de áudio para arquivos TTS gerados."""

    def play_file(self, filepath: str, on_complete: Callable = None):
        """Reproduz arquivo de áudio (wav ou mp3)."""
        def _play():
            try:
                ext = os.path.splitext(filepath)[1].lower()
                if ext == '.mp3':
                    subprocess.run(["mpg123", "-q", filepath], timeout=60)
                elif ext == '.wav':
                    subprocess.run(["aplay", "-q", filepath], timeout=60)
                else:
                    subprocess.run(["ffplay", "-nodisp", "-autoexit", filepath], timeout=60)
            except Exception as e:
                logger.error(f"[AudioPlayer] Erro ao reproduzir: {e}")
            finally:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
                if on_complete:
                    on_complete()

        t = threading.Thread(target=_play, daemon=True)
        t.start()
        return t


class TTSManager:
    """
    Gerenciador principal de Text-to-Speech do Springbonnie.
    Suporta múltiplos engines com fallback automático.
    Inclui fila de fala, lip-sync e efeitos de voz.
    """

    def __init__(self):
        self.logger = logging.getLogger("CyberFun.TTS")

        # Engines disponíveis
        self.espeak  = EspeakEngine()
        self.pyttsx3 = Pyttsx3Engine()
        self.gtts    = GTTSEngine()
        self.player  = AudioPlayer()

        # Detectar engines
        self._available_engines = self._detect_engines()
        self.logger.info(f"[TTS] Engines disponíveis: {self._available_engines}")

        # Fila de fala
        self.speech_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.is_speaking = False
        self.current_request: Optional[TTSRequest] = None

        # Callbacks
        self.on_speaking_start: Optional[Callable] = None
        self.on_speaking_end: Optional[Callable] = None
        self.on_phoneme: Optional[Callable] = None   # Para lip-sync

        # Thread de processamento
        self.running = False
        self.speech_thread = None

        # Estado de lip-sync
        self.lip_sync_active = False
        self.current_phonemes: List[PhonemeData] = []

        # Frases pré-definidas do Springbonnie
        self.preset_phrases = self._load_preset_phrases()

        self.logger.info("[TTS] Motor de síntese de voz inicializado")

    def _detect_engines(self) -> list:
        engines = []
        if self.espeak.is_available():  engines.append(TTSEngine.ESPEAK)
        if self.pyttsx3.is_available(): engines.append(TTSEngine.PYTTSX3)
        if self.gtts.is_available():    engines.append(TTSEngine.GTTS)
        return engines

    def _load_preset_phrases(self) -> dict:
        return {
            "greeting_day":     ["Olá! Bem-vindo à Cyber Fun Pizzaria!", "Ei, que bom te ver aqui!", "Oi! Prepare-se para a diversão!"],
            "greeting_night":   ["Boa noite... você está seguro?", "Hmm... visitante noturno..."],
            "show_intro":       ["É hora do show! Preparem-se para a diversão!", "Senhoras e senhores, crianças de todas as idades!"],
            "show_outro":       ["Obrigado por assistir! Até a próxima!", "Foi incrível! Nos vemos em breve!"],
            "birthday":         ["Feliz aniversário! Que seu dia seja incrível!", "Hip hip, hurra! É aniversário!"],
            "warning":          ["Atenção! Por favor mantenham distância segura.", "Cuidado com o animatrônico em operação!"],
            "malfunction":      ["Epa... algo não está certo...", "Dados corrompidos detectados...", "Initiating... reboot... sequence..."],
            "creepy":           ["Você ainda está aqui?", "Eu sei que você está lá...", "As câmeras estão me vigiando..."],
            "jokes":            ["Por que o robô foi ao médico? Porque tinha vírus!", "O que o computador come? Chips!"],
            "excitement":       ["INCRÍVEL! Que show fantástico!", "UAU! Vocês são os melhores!", "YEAAH! É hora da festa!"],
            "singing":          ["La la la... A música é minha alma!", "♪ Bem-vindos, bem-vindos, à nossa pizzaria! ♪"],
        }

    def start(self):
        """Inicia o motor de TTS."""
        self.running = True
        self.speech_thread = threading.Thread(target=self._speech_loop, daemon=True)
        self.speech_thread.start()
        self.logger.info("[TTS] Motor iniciado")

    def stop(self):
        """Para o motor de TTS."""
        self.running = False
        if self.speech_thread:
            self.speech_thread.join(timeout=2.0)

    def speak(self, text: str,
              voice: TTSVoice = TTSVoice.ROBOT_MALE,
              engine: TTSEngine = TTSEngine.AUTO,
              speed: float = 1.0,
              pitch: float = 1.0,
              volume: float = 1.0,
              priority: int = 5,
              blocking: bool = False,
              on_complete: Callable = None):
        """
        Principal função de fala do Springbonnie.
        Adiciona texto à fila de síntese.
        """
        request = TTSRequest(
            text=text, voice=voice, engine=engine,
            speed=speed, pitch=pitch, volume=volume,
            priority=priority, callback=on_complete
        )
        self.speech_queue.put((priority, time.time(), request))
        self.logger.info(f"[TTS] Enfileirando: \"{text[:50]}...\"")

        if blocking:
            while self.is_speaking or not self.speech_queue.empty():
                time.sleep(0.1)

    def speak_now(self, text: str, voice: TTSVoice = TTSVoice.ROBOT_MALE):
        """Fala imediatamente, interrompendo qualquer fala em andamento."""
        # Limpar fila
        while not self.speech_queue.empty():
            try:
                self.speech_queue.get_nowait()
            except queue.Empty:
                break

        # Falar com espeak direto (mais rápido)
        if TTSEngine.ESPEAK in self._available_engines:
            request = TTSRequest(text=text, voice=voice)
            self.espeak.speak_immediate(request)
        else:
            self.speak(text, voice=voice, priority=0)

    def speak_preset(self, preset_name: str, voice: TTSVoice = None, **kwargs):
        """Fala uma frase pré-definida aleatória."""
        import random
        phrases = self.preset_phrases.get(preset_name, ["..."])
        text = random.choice(phrases)

        if voice is None:
            # Escolher voz baseada no preset
            if preset_name in ["creepy", "malfunction", "warning"]:
                voice = TTSVoice.CREEPY
            elif preset_name in ["excitement", "show_intro", "birthday"]:
                voice = TTSVoice.CHEERFUL
            elif preset_name in ["singing"]:
                voice = TTSVoice.ROBOT_FEMALE
            else:
                voice = TTSVoice.ROBOT_MALE

        self.speak(text, voice=voice, **kwargs)

    def _speech_loop(self):
        """Loop de processamento da fila de fala."""
        while self.running:
            try:
                priority, timestamp, request = self.speech_queue.get(timeout=0.1)
                self._process_speech(request)
            except queue.Empty:
                pass
            except Exception as e:
                self.logger.error(f"[TTS] Erro no loop: {e}")

    def _process_speech(self, request: TTSRequest):
        """Processa uma requisição de fala."""
        self.is_speaking = True
        self.current_request = request

        if self.on_speaking_start:
            self.on_speaking_start(request.text)

        # Escolher engine
        engine = self._select_engine(request.engine)

        # Gerar áudio
        audio_file = None
        if engine == TTSEngine.ESPEAK and TTSEngine.ESPEAK in self._available_engines:
            # Obter fonemas para lip-sync antes de falar
            if self.on_phoneme:
                self.current_phonemes = self.espeak.get_phonemes(request.text, request.voice)
                threading.Thread(target=self._dispatch_phonemes, daemon=True).start()

            audio_file = self.espeak.speak(request)

        elif engine == TTSEngine.PYTTSX3 and TTSEngine.PYTTSX3 in self._available_engines:
            audio_file = self.pyttsx3.speak(request)

        elif engine == TTSEngine.GTTS and TTSEngine.GTTS in self._available_engines:
            audio_file = self.gtts.speak(request)

        # Reproduzir
        if audio_file:
            done_event = threading.Event()

            def on_done():
                done_event.set()
                self.is_speaking = False
                if self.on_speaking_end:
                    self.on_speaking_end(request.text)
                if request.callback:
                    request.callback()

            self.player.play_file(audio_file, on_complete=on_done)
            done_event.wait(timeout=60)
        else:
            self.is_speaking = False
            if self.on_speaking_end:
                self.on_speaking_end(request.text)

    def _dispatch_phonemes(self):
        """Despacha fonemas em tempo real para lip-sync."""
        start = time.time()
        for phoneme in self.current_phonemes:
            # Aguardar o tempo correto
            target_time = start + phoneme.timestamp_ms / 1000.0
            sleep_time = target_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

            if self.on_phoneme:
                self.on_phoneme(phoneme)

    def _select_engine(self, requested: TTSEngine) -> TTSEngine:
        """Seleciona o engine disponível mais adequado."""
        if requested != TTSEngine.AUTO and requested in self._available_engines:
            return requested
        # Auto: prioridade espeak > pyttsx3 > gtts
        for eng in [TTSEngine.ESPEAK, TTSEngine.PYTTSX3, TTSEngine.GTTS]:
            if eng in self._available_engines:
                return eng
        return TTSEngine.ESPEAK  # Último recurso

    def get_status(self) -> dict:
        return {
            "available_engines": [e.value for e in self._available_engines],
            "is_speaking": self.is_speaking,
            "queue_size": self.speech_queue.qsize(),
            "current_text": self.current_request.text[:50] if self.current_request else None,
        }
