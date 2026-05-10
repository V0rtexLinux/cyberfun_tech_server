"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Sistema de Orquestração de Show e Áudio
Módulo: Mixagem de Áudio e Coreografia em Tempo Real
================================================================================
Sistema de orquestração para shows do animatrônico. Suporta arquivos MP3 e WAV
com processamento em thread dedicada. Lê timeline de eventos para disparar
movimentos de servos em milissegundos exatos em relação à música.
================================================================================
"""

import numpy as np
import threading
import time
import json
import wave
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Callable, Any
from enum import Enum
import logging
from queue import Queue, Empty
import struct

# Importar pygame para reprodução de áudio (obrigatório)
import pygame
pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
PYGAME_AVAILABLE = True

# Importar pydub para processamento de MP3 (obrigatório)
from pydub import AudioSegment
PYDUB_AVAILABLE = True


class ShowState(Enum):
    """Estados do sistema de show"""
    IDLE = "idle"                   # Nenhum show ativo
    LOADING = "loading"             # Carregando arquivos
    READY = "ready"                 # Pronto para iniciar
    PLAYING = "playing"             # Show em execução
    PAUSED = "paused"               # Show pausado
    STOPPING = "stopping"           # Parando show
    ERROR = "error"                 # Erro no sistema


class EventType(Enum):
    """Tipos de eventos na timeline"""
    EXPRESSION = "expression"       # Mudança de expressão
    EMOTION = "emotion"             # Preset de emoção
    JAW = "jaw"                     # Movimento de mandíbula
    EYES = "eyes"                   # Movimento ocular
    EYELIDS = "eyelids"             # Pálpebras
    EARS = "ears"                   # Orelhas
    SERVO = "servo"                 # Comando direto de servo
    MOVE = "move"                   # Movimento do robô
    LOOK_AT = "look_at"             # Olhar para posição
    BLINK = "blink"                 # Piscar
    WINK = "wink"                   # Piscadela
    TALKING_START = "talking_start" # Iniciar lip-sync
    TALKING_STOP = "talking_stop"   # Parar lip-sync
    MARKER = "marker"               # Marcador de referência
    AUDIO_CUE = "audio_cue"         # Ponto de áudio
    LIGHTING = "lighting"           # Controle de iluminação
    WAIT = "wait"                   # Esperar


@dataclass
class TimelineEvent:
    """Evento individual na timeline do show"""
    event_id: int
    event_type: EventType
    timestamp_ms: int               # Tempo em milissegundos desde início
    duration_ms: int = 0            # Duração do evento (para transições)
    params: Dict[str, Any] = field(default_factory=dict)
    executed: bool = False
    
    def __lt__(self, other):
        """Comparação para ordenação por timestamp"""
        return self.timestamp_ms < other.timestamp_ms


@dataclass
class ShowTrack:
    """Trilha de show com áudio e eventos"""
    track_id: str
    name: str
    audio_file: str
    duration_ms: int
    events: List[TimelineEvent] = field(default_factory=list)
    bpm: int = 120                  # Beats per minute para coreografia
    artist: str = ""
    album: str = ""


@dataclass
class AudioData:
    """Dados de áudio para processamento"""
    samples: np.ndarray
    sample_rate: int
    channels: int
    duration_ms: int
    is_loaded: bool = False


class AudioProcessor:
    """
    Processador de áudio para análise e reprodução.
    Suporta MP3 e WAV com mixagem de alta fidelidade.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Fredbear.Audio")
        
        # Estado
        self.current_audio: Optional[AudioData] = None
        self.is_playing = False
        self.is_paused = False
        self.playback_position_ms = 0
        self.playback_start_time = 0.0
        
        # Configuração
        self.sample_rate = 44100
        self.channels = 2
        self.buffer_size = 2048
        
        # Thread de reprodução
        self.playback_thread = None
        self.running = False
        
        # Callback para dados de áudio (para lip-sync)
        self.audio_data_callback: Optional[Callable[[np.ndarray], None]] = None
        
        # Volume
        self.volume = 1.0
        
        self.logger.info("[AUDIO] Processador de áudio inicializado")
    
    def load_audio_file(self, file_path: str) -> Optional[AudioData]:
        """Carrega arquivo de áudio (MP3 ou WAV)"""
        if not os.path.exists(file_path):
            self.logger.error(f"[AUDIO] Arquivo não encontrado: {file_path}")
            return None
        
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        try:
            if ext == '.wav':
                return self._load_wav(file_path)
            elif ext == '.mp3':
                return self._load_mp3(file_path)
            else:
                self.logger.error(f"[AUDIO] Formato não suportado: {ext}")
                return None
        except Exception as e:
            self.logger.error(f"[AUDIO] Erro ao carregar {file_path}: {e}")
            return None
    
    def _load_wav(self, file_path: str) -> Optional[AudioData]:
        """Carrega arquivo WAV"""
        with wave.open(file_path, 'rb') as wav_file:
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            n_frames = wav_file.getnframes()
            
            # Ler todos os frames
            raw_data = wav_file.readframes(n_frames)
            
            # Converter para numpy array
            if sample_width == 2:
                samples = np.frombuffer(raw_data, dtype=np.int16)
            elif sample_width == 4:
                samples = np.frombuffer(raw_data, dtype=np.int32)
            else:
                samples = np.frombuffer(raw_data, dtype=np.uint8)
            
            # Normalizar para float
            samples = samples.astype(np.float32) / np.iinfo(samples.dtype).max
            
            # Reshape para canais
            if n_channels > 1:
                samples = samples.reshape(-1, n_channels)
            
            duration_ms = int((n_frames / sample_rate) * 1000)
            
            audio_data = AudioData(
                samples=samples,
                sample_rate=sample_rate,
                channels=n_channels,
                duration_ms=duration_ms,
                is_loaded=True
            )
            
            self.logger.info(f"[AUDIO] WAV carregado: {file_path} ({duration_ms}ms, {sample_rate}Hz)")
            return audio_data
    
    def _load_mp3(self, file_path: str) -> Optional[AudioData]:
        """Carrega arquivo MP3 (requer pydub ou conversão)"""
        if PYDUB_AVAILABLE:
            try:
                audio = AudioSegment.from_mp3(file_path)
                
                # Converter para numpy array
                samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
                samples = samples / (2 ** (audio.sample_width * 8 - 1))
                
                if audio.channels > 1:
                    samples = samples.reshape(-1, audio.channels)
                
                audio_data = AudioData(
                    samples=samples,
                    sample_rate=audio.frame_rate,
                    channels=audio.channels,
                    duration_ms=len(audio),
                    is_loaded=True
                )
                
                self.logger.info(f"[AUDIO] MP3 carregado: {file_path} ({len(audio)}ms)")
                return audio_data
            except Exception as e:
                self.logger.error(f"[AUDIO] Erro ao carregar MP3: {e}")
                return None
        else:
            # Fallback: tentar carregar como WAV convertido
            self.logger.warning("[AUDIO] pydub não disponível, tentando método alternativo")
            return self._load_wav(file_path.replace('.mp3', '.wav'))
    
    def play(self, audio_data: AudioData = None):
        """Inicia reprodução de áudio"""
        if audio_data:
            self.current_audio = audio_data
        
        if self.current_audio is None:
            self.logger.warning("[AUDIO] Nenhum áudio carregado para reprodução")
            return
        
        if not self.current_audio.is_loaded:
            raise Exception("Áudio não carregado corretamente. Verifique o arquivo de áudio.")
        
        self._play_with_pygame()
        
        self.is_playing = True
        self.is_paused = False
        self.playback_start_time = time.time()
        
        self.logger.info("[AUDIO] Reprodução iniciada")
    
    def _play_with_pygame(self):
        """Reproduz áudio usando pygame"""
        # Salvar áudio temporariamente para pygame
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()
        
        try:
            if self.current_audio.samples is not None:
                # Converter para int16
                samples_int = (self.current_audio.samples * 32767).astype(np.int16)
                
                with wave.open(temp_file.name, 'wb') as wav:
                    wav.setnchannels(self.current_audio.channels)
                    wav.setsampwidth(2)
                    wav.setframerate(self.current_audio.sample_rate)
                    wav.writeframes(samples_int.tobytes())
                
                pygame.mixer.music.load(temp_file.name)
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play()
        finally:
            # Limpar arquivo temporário
            try:
                os.unlink(temp_file.name)
            except:
                pass
    
    def _update_playback_position(self):
        """Atualiza posição de reprodução para lip-sync"""
        if self.current_audio and self.audio_data_callback and self.is_playing:
            # Obter posição atual em samples
            current_time_ms = self.get_position_ms()
            sample_rate = self.current_audio.sample_rate
            current_sample = int((current_time_ms / 1000.0) * sample_rate)
            
            # Enviar chunk atual para callback de lip-sync
            chunk_size = int(sample_rate * 0.02)  # 20ms chunks
            start = max(0, current_sample - chunk_size // 2)
            end = min(start + chunk_size, len(self.current_audio.samples))
            
            if end > start and start < len(self.current_audio.samples):
                chunk = self.current_audio.samples[start:end]
                self.audio_data_callback(chunk)
    
    def pause(self):
        """Pausa reprodução"""
        if self.is_playing:
            self.is_paused = True
            pygame.mixer.music.pause()
            self.logger.info("[AUDIO] Reprodução pausada")
    
    def resume(self):
        """Retoma reprodução pausada"""
        if self.is_paused:
            self.is_paused = False
            pygame.mixer.music.unpause()
            self.logger.info("[AUDIO] Reprodução retomada")
    
    def stop(self):
        """Para reprodução completamente"""
        self.is_playing = False
        self.is_paused = False
        self.running = False
        
        pygame.mixer.music.stop()
        
        self.playback_position_ms = 0
        self.logger.info("[AUDIO] Reprodução parada")
    
    def set_volume(self, volume: float):
        """Define volume (0.0 a 1.0)"""
        self.volume = np.clip(volume, 0.0, 1.0)
        pygame.mixer.music.set_volume(self.volume)
    
    def get_position_ms(self) -> int:
        """Retorna posição atual de reprodução em milissegundos"""
        if self.is_playing and not self.is_paused:
            # Pygame não fornece posição direta, calcular pelo tempo
            elapsed = time.time() - self.playback_start_time
            return int(elapsed * 1000)
        return self.playback_position_ms
    
    def set_position_ms(self, position_ms: int):
        """Define posição de reprodução"""
        self.playback_position_ms = position_ms
        
        # Calcular posição em segundos
        pos_sec = position_ms / 1000.0
        pygame.mixer.music.set_pos(pos_sec)
    
    def get_rms_at_position(self, window_ms: int = 50) -> float:
        """Calcula RMS do áudio na posição atual (para lip-sync)"""
        if not self.current_audio or not self.current_audio.is_loaded:
            return 0.0
        
        position_ms = self.get_position_ms()
        samples = self.current_audio.samples
        sample_rate = self.current_audio.sample_rate
        
        # Calcular índices
        center_sample = int((position_ms / 1000.0) * sample_rate)
        window_samples = int((window_ms / 1000.0) * sample_rate)
        
        start = max(0, center_sample - window_samples // 2)
        end = min(len(samples), center_sample + window_samples // 2)
        
        if end <= start:
            return 0.0
        
        chunk = samples[start:end]
        
        # Calcular RMS
        if len(chunk.shape) > 1:
            rms = np.sqrt(np.mean(chunk ** 2, axis=0))
            return float(np.mean(rms))
        else:
            return float(np.sqrt(np.mean(chunk ** 2)))
    
    def set_audio_data_callback(self, callback: Callable[[np.ndarray], None]):
        """Define callback para receber dados de áudio em tempo real"""
        self.audio_data_callback = callback


class TimelineParser:
    """
    Parser para arquivos de timeline de show.
    Converte JSON/texto em eventos estruturados.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Fredbear.Timeline")
    
    def parse_from_json(self, json_path: str) -> List[TimelineEvent]:
        """Parseia timeline de arquivo JSON"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            events = []
            event_id = 0
            
            for event_data in data.get('events', []):
                event = TimelineEvent(
                    event_id=event_id,
                    event_type=EventType(event_data['type']),
                    timestamp_ms=event_data['timestamp_ms'],
                    duration_ms=event_data.get('duration_ms', 0),
                    params=event_data.get('params', {}),
                    executed=False
                )
                events.append(event)
                event_id += 1
            
            # Ordenar por timestamp
            events.sort()
            
            self.logger.info(f"[TIMELINE] {len(events)} eventos carregados de {json_path}")
            return events
            
        except Exception as e:
            self.logger.error(f"[TIMELINE] Erro ao carregar timeline: {e}")
            return []
    
    def parse_from_dict(self, data: dict) -> List[TimelineEvent]:
        """Parseia timeline de dicionário Python"""
        events = []
        event_id = 0
        
        for event_data in data.get('events', []):
            try:
                event = TimelineEvent(
                    event_id=event_id,
                    event_type=EventType(event_data['type']),
                    timestamp_ms=event_data['timestamp_ms'],
                    duration_ms=event_data.get('duration_ms', 0),
                    params=event_data.get('params', {}),
                    executed=False
                )
                events.append(event)
                event_id += 1
            except Exception as e:
                self.logger.warning(f"[TIMELINE] Erro ao parsear evento: {e}")
        
        events.sort()
        return events
    
    def generate_auto_timeline(self, audio_data: AudioData, bpm: int = 120) -> List[TimelineEvent]:
        """
        Gera timeline automaticamente baseada no BPM do áudio.
        Útil para criar coreografias básicas.
        """
        events = []
        event_id = 0
        
        duration_ms = audio_data.duration_ms
        beat_interval_ms = int(60000 / bpm)  # ms por beat
        
        # Criar eventos de marcação de beat
        current_time = 0
        while current_time < duration_ms:
            # Marcação de beat
            events.append(TimelineEvent(
                event_id=event_id,
                event_type=EventType.MARKER,
                timestamp_ms=current_time,
                params={'beat': event_id // 2}
            ))
            event_id += 1
            
            # Em beats ímpares, piscar
            if (event_id // 2) % 4 == 0:
                events.append(TimelineEvent(
                    event_id=event_id,
                    event_type=EventType.BLINK,
                    timestamp_ms=current_time,
                    duration_ms=150
                ))
                event_id += 1
            
            current_time += beat_interval_ms
        
        events.sort()
        self.logger.info(f"[TIMELINE] Timeline auto-gerada com {len(events)} eventos")
        return events
    
    def save_to_json(self, events: List[TimelineEvent], output_path: str):
        """Salva timeline em arquivo JSON"""
        data = {
            'version': '1.0',
            'events': [
                {
                    'type': event.event_type.value,
                    'timestamp_ms': event.timestamp_ms,
                    'duration_ms': event.duration_ms,
                    'params': event.params
                }
                for event in events
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"[TIMELINE] Timeline salva em {output_path}")


class ShowOrchestrator:
    """
    Orquestrador principal de shows do Fredbear.
    Coordena áudio, timeline e execução de eventos em tempo real.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Fredbear.Show")
        
        # Componentes
        self.audio_processor = AudioProcessor()
        self.timeline_parser = TimelineParser()
        
        # Estado do show
        self.state = ShowState.IDLE
        self.current_track: Optional[ShowTrack] = None
        self.current_events: List[TimelineEvent] = []
        self.current_event_index = 0
        
        # Controle de tempo
        self.show_start_time = 0.0
        self.current_time_ms = 0
        
        # Callbacks para ações
        self.event_callbacks: Dict[EventType, Callable] = {}
        
        # Thread de orquestração
        self.orchestration_thread = None
        self.running = False
        
        # Controle de lip-sync
        self.lip_sync_active = False
        
        self.logger.info("[SHOW] Orquestrador de show inicializado")
    
    def register_event_callback(self, event_type: EventType, callback: Callable):
        """Registra callback para um tipo de evento"""
        self.event_callbacks[event_type] = callback
        self.logger.debug(f"[SHOW] Callback registrado para {event_type.value}")
    
    def load_show(self, audio_file: str, timeline_file: str = None) -> bool:
        """
        Carrega um show completo com áudio e timeline.
        Se timeline não fornecida, gera automaticamente.
        """
        self.state = ShowState.LOADING
        
        # Carregar áudio
        audio_data = self.audio_processor.load_audio_file(audio_file)
        
        if audio_data is None:
            self.state = ShowState.ERROR
            return False
        
        # Carregar ou gerar timeline
        if timeline_file and os.path.exists(timeline_file):
            events = self.timeline_parser.parse_from_json(timeline_file)
        else:
            events = self.timeline_parser.generate_auto_timeline(audio_data)
        
        # Criar track
        track_name = os.path.splitext(os.path.basename(audio_file))[0]
        
        self.current_track = ShowTrack(
            track_id=track_name.lower().replace(' ', '_'),
            name=track_name,
            audio_file=audio_file,
            duration_ms=audio_data.duration_ms,
            events=events
        )
        
        self.current_events = events
        self.current_audio = audio_data
        
        self.state = ShowState.READY
        self.logger.info(f"[SHOW] Show carregado: {track_name} ({len(events)} eventos)")
        return True
    
    def load_show_from_dict(self, show_config: dict) -> bool:
        """Carrega show a partir de configuração em dicionário"""
        self.state = ShowState.LOADING
        
        audio_file = show_config.get('audio_file')
        if not audio_file:
            self.state = ShowState.ERROR
            return False
        
        # Carregar áudio
        audio_data = self.audio_processor.load_audio_file(audio_file)
        if audio_data is None:
            self.state = ShowState.ERROR
            return False
        
        # Parsear eventos
        events = self.timeline_parser.parse_from_dict(show_config)
        
        # Criar track
        self.current_track = ShowTrack(
            track_id=show_config.get('track_id', 'default'),
            name=show_config.get('name', 'Show'),
            audio_file=audio_file,
            duration_ms=audio_data.duration_ms,
            events=events,
            bpm=show_config.get('bpm', 120)
        )
        
        self.current_events = events
        self.current_audio = audio_data
        self.state = ShowState.READY
        
        return True
    
    def start_show(self):
        """Inicia execução do show"""
        if self.state != ShowState.READY:
            self.logger.warning("[SHOW] Show não está pronto para iniciar")
            return
        
        # Resetar eventos
        for event in self.current_events:
            event.executed = False
        
        self.current_event_index = 0
        self.show_start_time = time.time()
        self.current_time_ms = 0
        
        # Iniciar áudio
        self.audio_processor.play(self.current_audio)
        
        # Iniciar thread de orquestração
        self.running = True
        self.orchestration_thread = threading.Thread(target=self._orchestration_loop, daemon=True)
        self.orchestration_thread.start()
        
        self.state = ShowState.PLAYING
        self.logger.info("[SHOW] Show iniciado!")
    
    def _orchestration_loop(self):
        """Loop principal de orquestração de eventos"""
        last_time = time.time()
        
        while self.running and self.state == ShowState.PLAYING:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            # Atualizar tempo atual
            self.current_time_ms = self.audio_processor.get_position_ms()
            
            # Processar eventos
            self._process_events()
            
            # Atualizar lip-sync se ativo
            if self.lip_sync_active:
                self._update_lip_sync()
            
            # Verificar fim do show
            if self.current_time_ms >= self.current_track.duration_ms:
                self._end_show()
                break
            
            # Aguardar próximo ciclo (60 fps)
            time.sleep(1.0 / 60)
    
    def _process_events(self):
        """Processa eventos que devem ser executados no tempo atual"""
        # Buscar eventos pendentes no tempo atual
        for i in range(self.current_event_index, len(self.current_events)):
            event = self.current_events[i]
            
            # Verificar se já passou do tempo do evento
            if event.timestamp_ms <= self.current_time_ms and not event.executed:
                self._execute_event(event)
                event.executed = True
                self.current_event_index = i + 1
            
            # Se evento está no futuro, parar busca
            elif event.timestamp_ms > self.current_time_ms:
                break
    
    def _execute_event(self, event: TimelineEvent):
        """Executa um evento individual"""
        self.logger.debug(f"[SHOW] Executando evento {event.event_id}: {event.event_type.value} @ {event.timestamp_ms}ms")
        
        # Verificar callback específico
        if event.event_type in self.event_callbacks:
            callback = self.event_callbacks[event.event_type]
            callback(event.params, event.duration_ms)
        else:
            # Execução padrão
            self._default_event_handler(event)
    
    def _default_event_handler(self, event: TimelineEvent):
        """Handler padrão para eventos sem callback registrado"""
        event_type = event.event_type
        params = event.params
        
        # Log de eventos não tratados
        self.logger.debug(f"[SHOW] Evento sem callback: {event_type.value}")
    
    def _update_lip_sync(self):
        """Atualiza lip-sync baseado no áudio atual"""
        rms = self.audio_processor.get_rms_at_position(window_ms=30)
        
        # Enviar para callback de jaw se registrado
        if EventType.JAW in self.event_callbacks:
            # Normalizar RMS para ângulo de mandíbula
            jaw_angle = rms * 40  # Escala
            self.event_callbacks[EventType.JAW]({'angle': min(jaw_angle, 35)}, 0)
    
    def _end_show(self):
        """Finaliza o show atual"""
        self.running = False
        self.audio_processor.stop()
        self.state = ShowState.IDLE
        
        # Resetar eventos
        for event in self.current_events:
            event.executed = False
        
        self.logger.info("[SHOW] Show finalizado!")
    
    def pause_show(self):
        """Pausa o show atual"""
        if self.state == ShowState.PLAYING:
            self.audio_processor.pause()
            self.state = ShowState.PAUSED
            self.logger.info("[SHOW] Show pausado")
    
    def resume_show(self):
        """Retoma show pausado"""
        if self.state == ShowState.PAUSED:
            self.audio_processor.resume()
            self.state = ShowState.PLAYING
            self.logger.info("[SHOW] Show retomado")
    
    def stop_show(self):
        """Para o show imediatamente"""
        self.state = ShowState.STOPPING
        self.running = False
        self.audio_processor.stop()
        
        if self.orchestration_thread:
            self.orchestration_thread.join(timeout=1.0)
        
        self.state = ShowState.IDLE
        self.logger.info("[SHOW] Show parado")
    
    def seek_to(self, position_ms: int):
        """Pula para posição específica do show"""
        if self.state not in [ShowState.PLAYING, ShowState.PAUSED]:
            return
        
        self.audio_processor.set_position_ms(position_ms)
        
        # Recalcular índice de eventos
        self.current_event_index = 0
        for i, event in enumerate(self.current_events):
            if event.timestamp_ms <= position_ms:
                event.executed = True
            else:
                event.executed = False
                self.current_event_index = i
                break
        
        self.current_time_ms = position_ms
    
    def get_show_progress(self) -> float:
        """Retorna progresso do show (0.0 a 1.0)"""
        if not self.current_track:
            return 0.0
        
        return self.current_time_ms / self.current_track.duration_ms
    
    def get_current_time_str(self) -> str:
        """Retorna tempo atual formatado (MM:SS)"""
        seconds = self.current_time_ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def enable_lip_sync(self, enabled: bool = True):
        """Ativa/desativa sincronização labial automática"""
        self.lip_sync_active = enabled
    
    def get_status(self) -> dict:
        """Retorna status completo do orquestrador"""
        return {
            "state": self.state.value,
            "current_track": self.current_track.name if self.current_track else None,
            "current_time_ms": self.current_time_ms,
            "current_time_str": self.get_current_time_str(),
            "duration_ms": self.current_track.duration_ms if self.current_track else 0,
            "progress": round(self.get_show_progress() * 100, 1),
            "events_total": len(self.current_events),
            "events_executed": sum(1 for e in self.current_events if e.executed),
            "lip_sync_active": self.lip_sync_active
        }


class ShowBuilder:
    """
    Builder para criar shows programaticamente.
    Facilita a criação de coreografias complexas.
    """
    
    def __init__(self, name: str, audio_file: str, bpm: int = 120):
        self.name = name
        self.audio_file = audio_file
        self.bpm = bpm
        self.events: List[TimelineEvent] = []
        self.event_id = 0
        
        # Configurações padrão
        self.beat_duration_ms = int(60000 / bpm)
    
    def at_ms(self, timestamp_ms: int):
        """Define tempo atual para adicionar eventos"""
        self._current_time = timestamp_ms
        return self
    
    def at_beat(self, beat: int):
        """Define tempo em beats"""
        self._current_time = beat * self.beat_duration_ms
        return self
    
    def at_second(self, second: float):
        """Define tempo em segundos"""
        self._current_time = int(second * 1000)
        return self
    
    def add_emotion(self, emotion: str, duration_ms: int = 300):
        """Adiciona evento de emoção"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.EMOTION,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={'emotion': emotion}
        ))
        self.event_id += 1
        return self
    
    def add_jaw(self, angle: float, duration_ms: int = 200):
        """Adiciona movimento de mandíbula"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.JAW,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={'angle': angle}
        ))
        self.event_id += 1
        return self
    
    def add_eyes(self, x: float, y: float, duration_ms: int = 200):
        """Adiciona movimento ocular"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.EYES,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={'x': x, 'y': y}
        ))
        self.event_id += 1
        return self
    
    def add_eyelids(self, openness: float, duration_ms: int = 200):
        """Adiciona movimento de pálpebras"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.EYELIDS,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={'openness': openness}
        ))
        self.event_id += 1
        return self
    
    def add_ears(self, angle: float, duration_ms: int = 200):
        """Adiciona movimento de orelhas"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.EARS,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={'angle': angle}
        ))
        self.event_id += 1
        return self
    
    def add_blink(self):
        """Adiciona piscada"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.BLINK,
            timestamp_ms=self._current_time,
            duration_ms=150,
            params={}
        ))
        self.event_id += 1
        return self
    
    def add_wink(self, side: str = "right"):
        """Adiciona piscadela"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.WINK,
            timestamp_ms=self._current_time,
            duration_ms=200,
            params={'side': side}
        ))
        self.event_id += 1
        return self
    
    def add_look_at(self, x: float, y: float, z: float = 0, duration_ms: int = 300):
        """Adiciona olhar para direção"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.LOOK_AT,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={'x': x, 'y': y, 'z': z}
        ))
        self.event_id += 1
        return self
    
    def add_talking_start(self):
        """Inicia modo de fala/lip-sync"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.TALKING_START,
            timestamp_ms=self._current_time,
            params={}
        ))
        self.event_id += 1
        return self
    
    def add_talking_stop(self):
        """Para modo de fala/lip-sync"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.TALKING_STOP,
            timestamp_ms=self._current_time,
            params={}
        ))
        self.event_id += 1
        return self
    
    def add_wait(self, duration_ms: int):
        """Adiciona espera"""
        self.events.append(TimelineEvent(
            event_id=self.event_id,
            event_type=EventType.WAIT,
            timestamp_ms=self._current_time,
            duration_ms=duration_ms,
            params={}
        ))
        self.event_id += 1
        return self
    
    def build(self) -> dict:
        """Constrói configuração do show"""
        # Ordenar eventos
        self.events.sort()
        
        return {
            'track_id': self.name.lower().replace(' ', '_'),
            'name': self.name,
            'audio_file': self.audio_file,
            'bpm': self.bpm,
            'events': [
                {
                    'type': e.event_type.value,
                    'timestamp_ms': e.timestamp_ms,
                    'duration_ms': e.duration_ms,
                    'params': e.params
                }
                for e in self.events
            ]
        }


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar orquestrador
    orchestrator = ShowOrchestrator()
    
    # Testar builder de show
    print("\n[FREDBEAR SHOW] Testando ShowBuilder:")
    
    builder = ShowBuilder("Run Rabbit Run", "Run,_Rabbit,_Run_-_Alan_Foster_-_Mack_Triplets.mp3", bpm=120)
    
    # Criar coreografia simples
    (builder
     .at_second(0).add_emotion("neutral")
     .at_second(1).add_blink()
     .at_second(2).add_emotion("happy")
     .at_second(2.5).add_eyes(30, 0)  # Olhar para direita
     .at_second(3).add_wink("right")
     .at_second(4).add_emotion("excited")
     .at_second(5).add_talking_start()
     .at_second(10).add_talking_stop()
     .at_second(11).add_emotion("neutral"))
    
    show_config = builder.build()
    print(f"  - Eventos criados: {len(show_config['events'])}")
    
    # Status do orquestrador
    print("\n[FREDBEAR SHOW] Status:")
    print(json.dumps(orchestrator.get_status(), indent=2))