"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Sistema de Expressão Facial Multi-Eixo
Módulo: Controle de Servos para Articulação Facial
================================================================================
Sistema de controle independente de mandíbula (jaw), pálpebras (eyelids),
movimento ocular X/Y e orelhas. Inclui presets de emoção e sincronia labial.
================================================================================
"""

import numpy as np
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Callable
from enum import Enum
import logging
import json
import queue


class EmotionPreset(Enum):
    """Presets de emoção pré-definidos"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    SURPRISED = "surprised"
    SAD = "sad"
    ANGRY = "angry"
    WINK = "wink"
    BLINK = "blink"
    TALKING = "talking"
    SINGING = "singing"
    LAUGHING = "laughing"
    SLEEPY = "sleepy"


@dataclass
class ServoConfig:
    """Configuração de um servo motor"""
    servo_id: int
    name: str
    min_angle: float = 0.0          # Graus
    max_angle: float = 180.0        # Graus
    min_pulse: int = 500            # Microseconds
    max_pulse: int = 2500           # Microseconds
    neutral_angle: float = 90.0     # Posição neutra
    speed: float = 100.0            # Graus/segundo
    smoothing: float = 0.3          # Fator de suavização (0-1)
    inverted: bool = False          # Inverter direção


@dataclass
class ServoState:
    """Estado atual de um servo"""
    current_angle: float
    target_angle: float
    current_pulse: int
    is_moving: bool = False
    last_update: float = field(default_factory=time.time)


@dataclass
class FacialPosition:
    """Posição completa de todos os servos faciais"""
    # Mandíbula (Jaw)
    jaw_angle: float = 0.0          # 0 = fechado, 45 = aberto máximo
    
    # Pálpebras (Eyelids)
    left_eyelid: float = 100.0      # 0 = fechado, 100 = aberto
    right_eyelid: float = 100.0
    
    # Movimento ocular X/Y
    eye_x: float = 0.0              # -45 = esquerda, 0 = centro, 45 = direita
    eye_y: float = 0.0              # -30 = baixo, 0 = centro, 30 = cima
    
    # Orelhas (Ears)
    left_ear: float = 0.0           # -20 = baixo, 0 = neutro, 20 = levantado
    right_ear: float = 0.0


@dataclass
class ExpressionTransition:
    """Transição de expressão animada"""
    start_expression: FacialPosition
    end_expression: FacialPosition
    duration: float                 # Segundos
    easing: str = "ease_in_out"     # linear, ease_in, ease_out, ease_in_out
    elapsed: float = 0.0
    is_complete: bool = False


class EasingFunctions:
    """Funções de easing para animações suaves"""
    
    @staticmethod
    def linear(t: float) -> float:
        return t
    
    @staticmethod
    def ease_in(t: float) -> float:
        return t * t
    
    @staticmethod
    def ease_out(t: float) -> float:
        return t * (2 - t)
    
    @staticmethod
    def ease_in_out(t: float) -> float:
        return t * t * (3 - 2 * t)
    
    @staticmethod
    def ease_bounce(t: float) -> float:
        """Efeito de bounce para expressões animadas"""
        if t < 0.5:
            return 8 * t * t * t * t
        else:
            return 1 - 8 * (1 - t) ** 4
    
    @staticmethod
    def ease_elastic(t: float) -> float:
        """Efeito elástico para surpresa"""
        if t == 0 or t == 1:
            return t
        return np.sin(-13 * np.pi * (t + 1) / 4) * (2 ** (10 * (t - 1))) + 1


class ServoController:
    """
    Controlador de servo motor individual.
    Gerencia comunicação com hardware e suavização de movimento.
    """
    
    def __init__(self, config: ServoConfig):
        self.config = config
        self.logger = logging.getLogger(f"Fredbear.Servo.{config.name}")
        
        # Estado
        self.state = ServoState(
            current_angle=config.neutral_angle,
            target_angle=config.neutral_angle,
            current_pulse=self._angle_to_pulse(config.neutral_angle)
        )
        
        # Thread de controle
        self.running = False
        self.update_thread = None
        self.update_rate = 50  # Hz
        
        # Callback para enviar comando ao hardware
        self.pwm_callback: Optional[Callable[[int, int], None]] = None
        
        self.logger.info(f"[SERVO] {config.name} inicializado")
    
    def _angle_to_pulse(self, angle: float) -> int:
        """Converte ângulo para largura de pulso PWM"""
        # Clamp angle
        angle = np.clip(angle, self.config.min_angle, self.config.max_angle)
        
        # Interpolação linear
        ratio = (angle - self.config.min_angle) / (self.config.max_angle - self.config.min_angle)
        
        if self.config.inverted:
            ratio = 1 - ratio
        
        pulse = int(self.config.min_pulse + ratio * (self.config.max_pulse - self.config.min_pulse))
        
        return pulse
    
    def set_angle(self, angle: float, immediate: bool = False):
        """Define ângulo alvo do servo"""
        angle = np.clip(angle, self.config.min_angle, self.config.max_angle)
        self.state.target_angle = angle
        
        if immediate:
            self.state.current_angle = angle
            self.state.current_pulse = self._angle_to_pulse(angle)
            self._send_pwm()
    
    def update(self, dt: float):
        """Atualiza posição do servo com suavização"""
        if abs(self.state.current_angle - self.state.target_angle) < 0.1:
            self.state.is_moving = False
            return
        
        self.state.is_moving = True
        
        # Calcular movimento máximo
        max_delta = self.config.speed * dt
        
        # Aplicar smoothing
        diff = self.state.target_angle - self.state.current_angle
        move = diff * (1 - self.config.smoothing) * dt * 10
        
        # Limitar à velocidade máxima
        move = np.clip(move, -max_delta, max_delta)
        
        # Atualizar posição
        self.state.current_angle += move
        self.state.current_angle = np.clip(
            self.state.current_angle,
            self.config.min_angle,
            self.config.max_angle
        )
        
        # Atualizar pulso
        self.state.current_pulse = self._angle_to_pulse(self.state.current_angle)
        self.state.last_update = time.time()
        
        # Enviar comando
        self._send_pwm()
    
    def _send_pwm(self):
        """Envia comando PWM para o hardware"""
        if self.pwm_callback:
            self.pwm_callback(self.config.servo_id, self.state.current_pulse)
    
    def get_angle(self) -> float:
        return self.state.current_angle
    
    def get_pulse(self) -> int:
        return self.state.current_pulse
    
    def is_moving(self) -> bool:
        return self.state.is_moving


class FacialExpressionController:
    """
    Sistema de Expressão Facial Multi-Eixo.
    Controle independente de mandíbula, pálpebras, movimento ocular e orelhas.
    """
    
    # IDs dos servos
    SERVO_JAW = 0
    SERVO_LEFT_EYELID = 1
    SERVO_RIGHT_EYELID = 2
    SERVO_EYE_X = 3
    SERVO_EYE_Y = 4
    SERVO_LEFT_EAR = 5
    SERVO_RIGHT_EAR = 6
    
    def __init__(self):
        self.logger = logging.getLogger("Fredbear.Expression")
        
        # Configuração dos servos
        self.servo_configs = self._create_servo_configs()
        self.servos: Dict[int, ServoController] = {}
        
        # Inicializar servos
        for servo_id, config in self.servo_configs.items():
            self.servos[servo_id] = ServoController(config)
        
        # Estado facial atual
        self.current_expression = FacialPosition()
        self.target_expression = FacialPosition()
        
        # Transição atual
        self.transition: Optional[ExpressionTransition] = None
        
        # Presets de emoção
        self.emotion_presets = self._create_emotion_presets()
        
        # Sincronia labial
        self.lip_sync_enabled = False
        self.lip_sync_queue = queue.Queue()
        self.lip_sync_amplitude = 20.0  # Graus de abertura máxima
        self.lip_sync_frequency = 4.0   # Hz típico de fala
        
        # Auto-blink
        self.auto_blink_enabled = True
        self.blink_interval_min = 2.0    # Segundos
        self.blink_interval_max = 6.0
        self.next_blink_time = time.time() + np.random.uniform(
            self.blink_interval_min, self.blink_interval_max
        )
        self.blink_duration = 0.15       # Segundos
        self.is_blinking = False
        self.blink_start_time = 0.0
        
        # Threading
        self.running = False
        self.expression_thread = None
        self.update_rate = 60  # Hz (60 fps para animações suaves)
        
        # PWM callback para hardware
        self.pwm_callback: Optional[Callable[[int, int], None]] = None
        
        self.logger.info("[EXPRESSION] Sistema de expressão facial inicializado")
    
    def _create_servo_configs(self) -> Dict[int, ServoConfig]:
        """Cria configurações padrão para cada servo facial"""
        return {
            self.SERVO_JAW: ServoConfig(
                servo_id=self.SERVO_JAW,
                name="Jaw",
                min_angle=0.0,
                max_angle=45.0,
                neutral_angle=0.0,
                speed=120.0,
                smoothing=0.3
            ),
            self.SERVO_LEFT_EYELID: ServoConfig(
                servo_id=self.SERVO_LEFT_EYELID,
                name="LeftEyelid",
                min_angle=0.0,
                max_angle=100.0,
                neutral_angle=100.0,
                speed=400.0,  # Rápido para blink
                smoothing=0.1
            ),
            self.SERVO_RIGHT_EYELID: ServoConfig(
                servo_id=self.SERVO_RIGHT_EYELID,
                name="RightEyelid",
                min_angle=0.0,
                max_angle=100.0,
                neutral_angle=100.0,
                speed=400.0,
                smoothing=0.1
            ),
            self.SERVO_EYE_X: ServoConfig(
                servo_id=self.SERVO_EYE_X,
                name="EyeX",
                min_angle=-45.0,
                max_angle=45.0,
                neutral_angle=0.0,
                speed=180.0,
                smoothing=0.2
            ),
            self.SERVO_EYE_Y: ServoConfig(
                servo_id=self.SERVO_EYE_Y,
                name="EyeY",
                min_angle=-30.0,
                max_angle=30.0,
                neutral_angle=0.0,
                speed=180.0,
                smoothing=0.2
            ),
            self.SERVO_LEFT_EAR: ServoConfig(
                servo_id=self.SERVO_LEFT_EAR,
                name="LeftEar",
                min_angle=-20.0,
                max_angle=20.0,
                neutral_angle=0.0,
                speed=90.0,
                smoothing=0.4
            ),
            self.SERVO_RIGHT_EAR: ServoConfig(
                servo_id=self.SERVO_RIGHT_EAR,
                name="RightEar",
                min_angle=-20.0,
                max_angle=20.0,
                neutral_angle=0.0,
                speed=90.0,
                smoothing=0.4
            ),
        }
    
    def _create_emotion_presets(self) -> Dict[EmotionPreset, FacialPosition]:
        """Cria presets de emoção pré-definidos"""
        return {
            EmotionPreset.NEUTRAL: FacialPosition(
                jaw_angle=0.0,
                left_eyelid=100.0, right_eyelid=100.0,
                eye_x=0.0, eye_y=0.0,
                left_ear=0.0, right_ear=0.0
            ),
            EmotionPreset.HAPPY: FacialPosition(
                jaw_angle=5.0,
                left_eyelid=85.0, right_eyelid=85.0,  # Ligeiramente fechado (sorriso)
                eye_x=0.0, eye_y=5.0,
                left_ear=10.0, right_ear=10.0
            ),
            EmotionPreset.EXCITED: FacialPosition(
                jaw_angle=15.0,
                left_eyelid=100.0, right_eyelid=100.0,
                eye_x=0.0, eye_y=10.0,
                left_ear=20.0, right_ear=20.0
            ),
            EmotionPreset.SURPRISED: FacialPosition(
                jaw_angle=25.0,
                left_eyelid=100.0, right_eyelid=100.0,
                eye_x=0.0, eye_y=15.0,
                left_ear=15.0, right_ear=15.0
            ),
            EmotionPreset.SAD: FacialPosition(
                jaw_angle=0.0,
                left_eyelid=60.0, right_eyelid=60.0,
                eye_x=0.0, eye_y=-10.0,
                left_ear=-15.0, right_ear=-15.0
            ),
            EmotionPreset.ANGRY: FacialPosition(
                jaw_angle=5.0,
                left_eyelid=70.0, right_eyelid=70.0,
                eye_x=0.0, eye_y=-5.0,
                left_ear=-10.0, right_ear=-10.0
            ),
            EmotionPreset.WINK: FacialPosition(
                jaw_angle=3.0,
                left_eyelid=100.0, right_eyelid=0.0,  # Piscada direita
                eye_x=5.0, eye_y=0.0,
                left_ear=5.0, right_ear=5.0
            ),
            EmotionPreset.BLINK: FacialPosition(
                jaw_angle=0.0,
                left_eyelid=0.0, right_eyelid=0.0,
                eye_x=0.0, eye_y=0.0,
                left_ear=0.0, right_ear=0.0
            ),
            EmotionPreset.TALKING: FacialPosition(
                jaw_angle=10.0,
                left_eyelid=100.0, right_eyelid=100.0,
                eye_x=0.0, eye_y=0.0,
                left_ear=0.0, right_ear=0.0
            ),
            EmotionPreset.SINGING: FacialPosition(
                jaw_angle=20.0,
                left_eyelid=90.0, right_eyelid=90.0,
                eye_x=0.0, eye_y=5.0,
                left_ear=5.0, right_ear=5.0
            ),
            EmotionPreset.LAUGHING: FacialPosition(
                jaw_angle=25.0,
                left_eyelid=80.0, right_eyelid=80.0,
                eye_x=0.0, eye_y=5.0,
                left_ear=15.0, right_ear=15.0
            ),
            EmotionPreset.SLEEPY: FacialPosition(
                jaw_angle=0.0,
                left_eyelid=30.0, right_eyelid=30.0,
                eye_x=0.0, eye_y=-5.0,
                left_ear=-10.0, right_ear=-10.0
            ),
        }
    
    def set_pwm_callback(self, callback: Callable[[int, int], None]):
        """Define callback para enviar comandos PWM ao hardware"""
        self.pwm_callback = callback
        for servo in self.servos.values():
            servo.pwm_callback = callback
    
    def set_expression(self, expression: FacialPosition, duration: float = 0.3,
                       easing: str = "ease_in_out"):
        """Define expressão facial com transição animada"""
        self.transition = ExpressionTransition(
            start_expression=self._get_current_position(),
            end_expression=expression,
            duration=duration,
            easing=easing
        )
        self.target_expression = expression
    
    def set_emotion(self, emotion: EmotionPreset, duration: float = 0.3):
        """Aplica preset de emoção com transição"""
        if emotion in self.emotion_presets:
            self.set_expression(self.emotion_presets[emotion], duration)
            self.logger.info(f"[EXPRESSION] Aplicando emoção: {emotion.value}")
    
    def _get_current_position(self) -> FacialPosition:
        """Obtém posição atual de todos os servos"""
        return FacialPosition(
            jaw_angle=self.servos[self.SERVO_JAW].get_angle(),
            left_eyelid=self.servos[self.SERVO_LEFT_EYELID].get_angle(),
            right_eyelid=self.servos[self.SERVO_RIGHT_EYELID].get_angle(),
            eye_x=self.servos[self.SERVO_EYE_X].get_angle(),
            eye_y=self.servos[self.SERVO_EYE_Y].get_angle(),
            left_ear=self.servos[self.SERVO_LEFT_EAR].get_angle(),
            right_ear=self.servos[self.SERVO_RIGHT_EAR].get_angle()
        )
    
    def update_transition(self, dt: float):
        """Atualiza transição de expressão em andamento"""
        if self.transition is None or self.transition.is_complete:
            return
        
        self.transition.elapsed += dt
        
        # Calcular progresso (0 a 1)
        t = min(self.transition.elapsed / self.transition.duration, 1.0)
        
        # Aplicar easing
        easing_func = getattr(EasingFunctions, self.transition.easing.replace("-", "_"), 
                             EasingFunctions.ease_in_out)
        progress = easing_func(t)
        
        # Interpolar valores
        start = self.transition.start_expression
        end = self.transition.end_expression
        
        self.current_expression = FacialPosition(
            jaw_angle=self._lerp(start.jaw_angle, end.jaw_angle, progress),
            left_eyelid=self._lerp(start.left_eyelid, end.left_eyelid, progress),
            right_eyelid=self._lerp(start.right_eyelid, end.right_eyelid, progress),
            eye_x=self._lerp(start.eye_x, end.eye_x, progress),
            eye_y=self._lerp(start.eye_y, end.eye_y, progress),
            left_ear=self._lerp(start.left_ear, end.left_ear, progress),
            right_ear=self._lerp(start.right_ear, end.right_ear, progress)
        )
        
        # Verificar conclusão
        if t >= 1.0:
            self.transition.is_complete = True
            self.current_expression = end
    
    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        """Interpolação linear"""
        return a + (b - a) * t
    
    def apply_expression_to_servos(self):
        """Aplica expressão atual aos servos"""
        exp = self.current_expression
        
        # Mandíbula
        self.servos[self.SERVO_JAW].set_angle(exp.jaw_angle)
        
        # Pálpebras
        self.servos[self.SERVO_LEFT_EYELID].set_angle(exp.left_eyelid)
        self.servos[self.SERVO_RIGHT_EYELID].set_angle(exp.right_eyelid)
        
        # Olhos X/Y
        self.servos[self.SERVO_EYE_X].set_angle(exp.eye_x)
        self.servos[self.SERVO_EYE_Y].set_angle(exp.eye_y)
        
        # Orelhas
        self.servos[self.SERVO_LEFT_EAR].set_angle(exp.left_ear)
        self.servos[self.SERVO_RIGHT_EAR].set_angle(exp.right_ear)
    
    def update_servos(self, dt: float):
        """Atualiza todos os servos"""
        for servo in self.servos.values():
            servo.update(dt)
    
    def update_auto_blink(self):
        """Atualiza sistema de auto-blink"""
        if not self.auto_blink_enabled:
            return
        
        current_time = time.time()
        
        if self.is_blinking:
            # Verificar se blink terminou
            if current_time - self.blink_start_time >= self.blink_duration:
                # Retornar pálpebras ao estado anterior
                self.is_blinking = False
                
                # Agendar próximo blink
                self.next_blink_time = current_time + np.random.uniform(
                    self.blink_interval_min, self.blink_interval_max
                )
        else:
            # Verificar se é hora de blink
            if current_time >= self.next_blink_time:
                # Iniciar blink
                self.is_blinking = True
                self.blink_start_time = current_time
                
                # Fechar pálpebras rapidamente
                self.servos[self.SERVO_LEFT_EYELID].set_angle(0, immediate=True)
                self.servos[self.SERVO_RIGHT_EYELID].set_angle(0, immediate=True)
    
    def look_at(self, x: float, y: float):
        """
        Move os olhos para olhar em uma direção.
        x: -45 (esquerda) a 45 (direita)
        y: -30 (baixo) a 30 (cima)
        """
        self.current_expression.eye_x = np.clip(x, -45, 45)
        self.current_expression.eye_y = np.clip(y, -30, 30)
        
        self.servos[self.SERVO_EYE_X].set_angle(self.current_expression.eye_x)
        self.servos[self.SERVO_EYE_Y].set_angle(self.current_expression.eye_y)
    
    def look_at_point(self, target_x: float, target_y: float, target_z: float,
                      head_x: float = 0, head_y: float = 0, head_z: float = 0):
        """
        Calcula ângulos oculares para olhar para um ponto 3D.
        Coordenadas em cm relativas à cabeça do animatrônico.
        """
        # Vetor do ponto de visão
        dx = target_x - head_x
        dy = target_y - head_y
        dz = target_z - head_z
        
        # Calcular ângulos
        eye_x = np.degrees(np.arctan2(dx, dz))  # Ângulo horizontal
        eye_y = np.degrees(np.arctan2(-dy, np.sqrt(dx**2 + dz**2)))  # Ângulo vertical
        
        self.look_at(eye_x, eye_y)
    
    def do_wink(self, side: str = "right", duration: float = 0.2):
        """Executa uma piscadela (wink) em um lado"""
        if side == "right":
            self.set_expression(
                FacialPosition(
                    jaw_angle=self.current_expression.jaw_angle,
                    left_eyelid=100.0,
                    right_eyelid=0.0,
                    eye_x=self.current_expression.eye_x,
                    eye_y=self.current_expression.eye_y,
                    left_ear=self.current_expression.left_ear,
                    right_ear=self.current_expression.right_ear
                ),
                duration=duration / 2
            )
        else:
            self.set_expression(
                FacialPosition(
                    jaw_angle=self.current_expression.jaw_angle,
                    left_eyelid=0.0,
                    right_eyelid=100.0,
                    eye_x=self.current_expression.eye_x,
                    eye_y=self.current_expression.eye_y,
                    left_ear=self.current_expression.left_ear,
                    right_ear=self.current_expression.right_ear
                ),
                duration=duration / 2
            )
    
    def open_jaw(self, angle: float):
        """Abre mandíbula para ângulo específico"""
        self.current_expression.jaw_angle = np.clip(angle, 0, 45)
        self.servos[self.SERVO_JAW].set_angle(self.current_expression.jaw_angle)
    
    def close_jaw(self):
        """Fecha mandíbula completamente"""
        self.open_jaw(0)
    
    def set_eyelids(self, openness: float):
        """
        Define abertura das pálpebras.
        openness: 0 (fechado) a 100 (completamente aberto)
        """
        self.current_expression.left_eyelid = openness
        self.current_expression.right_eyelid = openness
        
        self.servos[self.SERVO_LEFT_EYELID].set_angle(openness)
        self.servos[self.SERVO_RIGHT_EYELID].set_angle(openness)
    
    def set_ears(self, angle: float):
        """
        Define posição das orelhas.
        angle: -20 (abaixadas) a 20 (levantadas)
        """
        self.current_expression.left_ear = angle
        self.current_expression.right_ear = angle
        
        self.servos[self.SERVO_LEFT_EAR].set_angle(angle)
        self.servos[self.SERVO_RIGHT_EAR].set_angle(angle)
    
    # ==================== SINCRONIA LABIAL (LIP-SYNC) ====================
    
    def start_lip_sync(self):
        """Inicia modo de sincronia labial"""
        self.lip_sync_enabled = True
        self.set_emotion(EmotionPreset.TALKING)
        self.logger.info("[EXPRESSION] Lip-sync iniciado")
    
    def stop_lip_sync(self):
        """Para modo de sincronia labial"""
        self.lip_sync_enabled = False
        self.close_jaw()
        self.set_emotion(EmotionPreset.NEUTRAL)
        self.logger.info("[EXPRESSION] Lip-sync parado")
    
    def process_audio_for_lip_sync(self, audio_data: np.ndarray, sample_rate: int = 16000):
        """
        Processa dados de áudio para sincronia labial.
        Analisa picos de frequência para abrir/fechar mandíbula.
        """
        if not self.lip_sync_enabled:
            return
        
        # Calcular RMS do áudio (energia)
        rms = np.sqrt(np.mean(audio_data ** 2))
        
        # Normalizar para amplitude de mandíbula
        normalized = min(rms * 10, 1.0)  # Fator de escala
        jaw_angle = normalized * self.lip_sync_amplitude
        
        # Aplicar com suavização
        current_jaw = self.current_expression.jaw_angle
        new_jaw = current_jaw * 0.7 + jaw_angle * 0.3
        
        self.open_jaw(new_jaw)
    
    def set_lip_sync_params(self, amplitude: float = None, frequency: float = None):
        """Configura parâmetros de lip-sync"""
        if amplitude is not None:
            self.lip_sync_amplitude = amplitude
        if frequency is not None:
            self.lip_sync_frequency = frequency
    
    # ==================== LOOP PRINCIPAL ====================
    
    def start_expression_loop(self):
        """Inicia loop de atualização de expressão em thread separada"""
        self.running = True
        self.expression_thread = threading.Thread(target=self._expression_loop, daemon=True)
        self.expression_thread.start()
        self.logger.info("[EXPRESSION] Loop de expressão iniciado")
    
    def _expression_loop(self):
        """Loop principal de atualização de expressão"""
        last_time = time.time()
        
        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            # Atualizar transição
            self.update_transition(dt)
            
            # Atualizar auto-blink
            self.update_auto_blink()
            
            # Aplicar expressão aos servos
            self.apply_expression_to_servos()
            
            # Atualizar servos
            self.update_servos(dt)
            
            # Aguardar próximo ciclo
            time.sleep(1.0 / self.update_rate)
    
    def stop_expression_loop(self):
        """Para loop de expressão"""
        self.running = False
        if self.expression_thread:
            self.expression_thread.join(timeout=1.0)
        self.logger.info("[EXPRESSION] Loop de expressão parado")
    
    def get_status(self) -> dict:
        """Retorna status do sistema de expressão"""
        return {
            "current_expression": {
                "jaw_angle": round(self.current_expression.jaw_angle, 1),
                "left_eyelid": round(self.current_expression.left_eyelid, 1),
                "right_eyelid": round(self.current_expression.right_eyelid, 1),
                "eye_x": round(self.current_expression.eye_x, 1),
                "eye_y": round(self.current_expression.eye_y, 1),
                "left_ear": round(self.current_expression.left_ear, 1),
                "right_ear": round(self.current_expression.right_ear, 1)
            },
            "transition_active": self.transition is not None and not self.transition.is_complete,
            "auto_blink_enabled": self.auto_blink_enabled,
            "lip_sync_enabled": self.lip_sync_enabled,
            "is_blinking": self.is_blinking,
            "servo_angles": {
                name: round(servo.get_angle(), 1) 
                for name, servo in [(config.name, self.servos[sid]) 
                                    for sid, config in self.servo_configs.items()]
            }
        }


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar controlador
    expression = FacialExpressionController()
    
    # Testar presets de emoção
    print("\n[FREDBEAR EXPRESSION] Testando presets de emoção:")
    
    for emotion in [EmotionPreset.NEUTRAL, EmotionPreset.HAPPY, EmotionPreset.SURPRISED, 
                    EmotionPreset.WINK]:
        expression.set_emotion(emotion, duration=0.5)
        print(f"  - {emotion.value}: {expression.get_status()['current_expression']}")
    
    # Testar look_at
    print("\n[FREDBEAR EXPRESSION] Testando look_at:")
    expression.look_at(30, 10)  # Olhar para direita e cima
    print(f"  - Olhos: X={expression.current_expression.eye_x}, Y={expression.current_expression.eye_y}")
    
    # Testar mandíbula
    print("\n[FREDBEAR EXPRESSION] Testando mandíbula:")
    expression.open_jaw(30)
    print(f"  - Mandíbula: {expression.current_expression.jaw_angle} graus")