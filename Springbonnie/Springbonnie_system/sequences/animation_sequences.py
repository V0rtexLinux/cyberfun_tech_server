"""
================================================================================
  CYBER FUN ENDOSKELETON - Sequências de Animação Avançadas
  Coreografias procedurais: dança, cumprimento, susto, risada, etc.
================================================================================
"""

import time
import threading
import random
import math
import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Dict
from enum import Enum

logger = logging.getLogger("CyberFun.Sequences")


class SequenceType(Enum):
    GREETING    = "greeting"
    DANCE       = "dance"
    SCARE       = "scare"
    LAUGH       = "laugh"
    THINKING    = "thinking"
    WAVE        = "wave"
    HEADBANG    = "headbang"
    EYE_ROLL    = "eye_roll"
    CREEPY_LOOK = "creepy_look"
    BOOT_UP     = "boot_up"
    SHUTDOWN    = "shutdown"
    MALFUNCTION = "malfunction"
    EXCITED     = "excited"
    SAD         = "sad"
    ROAR        = "roar"
    SNEEZE      = "sneeze"


@dataclass
class Keyframe:
    """Frame de animação com posições de todos os servos faciais."""
    time_offset: float   # Segundos desde início da sequência
    jaw:         float   # 0-45
    left_eye:    float   # 0-100
    right_eye:   float   # 0-100
    eye_x:       float   # -45 a 45
    eye_y:       float   # -30 a 30
    left_ear:    float   # -20 a 20
    right_ear:   float   # -20 a 20
    easing:      str     = "ease_in_out"


@dataclass  
class BodyKeyframe:
    """Frame de animação para servos de corpo."""
    time_offset:   float
    head_pan:      float = 0    # -45 a 45
    head_tilt:     float = 0    # -30 a 30
    left_shoulder: float = 90   # 0-180
    right_shoulder:float = 90
    left_elbow:    float = 90
    right_elbow:   float = 90
    left_wrist:    float = 90
    right_wrist:   float = 90
    torso_twist:   float = 0    # -30 a 30


class SequencePlayer:
    """Executa sequências de animação nos servos do animatrônico."""

    def __init__(self):
        self.expression_ref = None   # FacialExpressionController
        self.kernel_ref = None       # SpringbonnieKernel
        self.tts_ref = None          # TTSManager

        self.is_playing = False
        self.current_sequence = None
        self._stop_flag = threading.Event()

        # Biblioteca de sequências
        self.sequences: Dict[SequenceType, List[Keyframe]] = self._build_sequence_library()

        logger.info("[SEQ] Player de sequências inicializado")

    def inject_systems(self, expression=None, kernel=None, tts=None):
        self.expression_ref = expression
        self.kernel_ref = kernel
        self.tts_ref = tts

    def play(self, sequence_type: SequenceType, blocking: bool = False,
             on_complete: Callable = None):
        """Executa uma sequência de animação."""
        if self.is_playing:
            self.stop()

        self._stop_flag.clear()
        self.current_sequence = sequence_type

        def _run():
            self.is_playing = True
            try:
                frames = self.sequences.get(sequence_type, [])
                self._execute_frames(frames)
            except Exception as e:
                logger.error(f"[SEQ] Erro na sequência {sequence_type.value}: {e}")
            finally:
                self.is_playing = False
                self.current_sequence = None
                if on_complete:
                    on_complete()

        if blocking:
            _run()
        else:
            t = threading.Thread(target=_run, daemon=True)
            t.start()

    def stop(self):
        """Para a sequência em andamento."""
        self._stop_flag.set()
        self.is_playing = False

    def _execute_frames(self, frames: List[Keyframe]):
        """Interpola e aplica keyframes."""
        if not frames or not self.expression_ref:
            return

        start_time = time.time()

        for i, frame in enumerate(frames):
            if self._stop_flag.is_set():
                break

            # Aguardar até o tempo do frame
            elapsed = time.time() - start_time
            wait_time = frame.time_offset - elapsed
            if wait_time > 0:
                time.sleep(wait_time)

            # Aplicar frame
            self._apply_keyframe(frame)

    def _apply_keyframe(self, frame: Keyframe):
        """Aplica um keyframe ao sistema de expressão."""
        if not self.expression_ref:
            return

        from springbonnie_system.expression.facial_controller import FacialPosition
        pos = FacialPosition(
            jaw_angle=frame.jaw,
            left_eyelid=frame.left_eye,
            right_eyelid=frame.right_eye,
            eye_x=frame.eye_x,
            eye_y=frame.eye_y,
            left_ear=frame.left_ear,
            right_ear=frame.right_ear,
        )
        self.expression_ref.set_expression(pos, duration=0.15, easing=frame.easing)

    def _build_sequence_library(self) -> Dict[SequenceType, List[Keyframe]]:
        """Constrói biblioteca de sequências pré-programadas."""
        lib = {}

        # ---- CUMPRIMENTO ----
        lib[SequenceType.GREETING] = [
            Keyframe(0.0,  0,  100, 100,  0,   0,  0,  0),
            Keyframe(0.3,  5,   85,  85,  0,   5, 10, 10, "ease_out"),
            Keyframe(0.6, 10,  100, 100, 15,  10, 15, 15, "ease_in_out"),
            Keyframe(0.9,  5,   90,  90, -15, 10, 10, 10),
            Keyframe(1.2, 10,  100, 100,  0,   5, 15, 15),
            Keyframe(1.5,  0,  100, 100,  0,   0,  0,  0, "ease_out"),
        ]

        # ---- DANÇA (cabeça bate no ritmo) ----
        dance_frames = []
        for i in range(8):
            t = i * 0.25
            side = 15 if i % 2 == 0 else -15
            ear  = 15 if i % 2 == 0 else -15
            dance_frames.append(Keyframe(t, 8, 100, 100, side, 0, ear, -ear, "ease_in_out"))
        lib[SequenceType.DANCE] = dance_frames

        # ---- HEADBANG ----
        hb = []
        for i in range(6):
            t = i * 0.18
            tilt = 20 if i % 2 == 0 else -10
            hb.append(Keyframe(t, 5, 100, 100, 0, tilt, 5, 5))
        lib[SequenceType.HEADBANG] = hb

        # ---- SUSTO ----
        lib[SequenceType.SCARE] = [
            Keyframe(0.0,  0,  100, 100,  0,   0,   0,  0),
            Keyframe(0.1, 40,  100, 100,  0,  15,  20, 20, "ease_out"),  # Boca abre RÁPIDO
            Keyframe(0.3,  0,   20,  20,  0, -10, -10,-10, "linear"),    # Pálpebras caem
            Keyframe(0.5, 30,  100, 100, 30,  15,  20, 20, "ease_in_out"),
            Keyframe(0.7,  0,    0,   0,  0,   0,   0,  0, "ease_in"),
            Keyframe(1.0,  5,  100, 100,  0,   5,   0,  0, "ease_out"),
        ]

        # ---- RISADA ----
        laugh = []
        for i in range(10):
            t = i * 0.12
            jaw  = 25 if i % 2 == 0 else 5
            eyes = 80 if i % 2 == 0 else 100
            ear  = 15 if i % 2 == 0 else 5
            laugh.append(Keyframe(t, jaw, eyes, eyes, 0, 5, ear, ear))
        lib[SequenceType.LAUGH] = laugh

        # ---- PENSANDO ----
        lib[SequenceType.THINKING] = [
            Keyframe(0.0,  0, 100, 100,  0,   0,   0,  0),
            Keyframe(0.3,  0,  80,  80, -20,  5, -10,-10, "ease_in_out"),
            Keyframe(1.0,  0,  60,  60, -30,  8, -15,-15),
            Keyframe(1.5,  0,  60,  60, -30, 10, -15,-15),
            Keyframe(2.0,  0,  60,  60,  30,  8,  10, 10, "ease_in_out"),
            Keyframe(2.5,  0, 100, 100,  0,   0,   0,  0, "ease_out"),
        ]

        # ---- ACENO (WAVE) ----
        lib[SequenceType.WAVE] = [
            Keyframe(0.0,  3, 100, 100,  20, 5,  10,  5),
            Keyframe(0.3,  5, 100, 100,  35, 8,  15,  5, "ease_in_out"),
            Keyframe(0.6,  3, 100, 100,  20, 5,  10,  5),
            Keyframe(0.9,  5, 100, 100,  35, 8,  15,  5),
            Keyframe(1.2,  3, 100, 100,  20, 5,  10,  5),
            Keyframe(1.5,  0, 100, 100,   0, 0,   0,  0, "ease_out"),
        ]

        # ---- EYE ROLL ----
        lib[SequenceType.EYE_ROLL] = [
            Keyframe(0.0,  0, 100, 100,  0,   0,  0,  0),
            Keyframe(0.2,  0, 100, 100,  0,  30,  0,  0, "ease_in"),   # Olha pra cima
            Keyframe(0.4,  0, 100, 100, 30,  30,  0,  0),               # Direita-cima
            Keyframe(0.6,  0, 100, 100, 30, -30,  0,  0),               # Direita-baixo
            Keyframe(0.8,  0, 100, 100, -30,-30,  0,  0),               # Esquerda-baixo
            Keyframe(1.0,  0, 100, 100, -30, 30,  0,  0),               # Esquerda-cima
            Keyframe(1.2,  0, 100, 100,  0,   0,  0,  0, "ease_out"),
        ]

        # ---- CREEPY LOOK ----
        lib[SequenceType.CREEPY_LOOK] = [
            Keyframe(0.0,  0,  60,  60,  0,  -5,  0,  0),
            Keyframe(0.5,  0,  30,  30, 35, -10, -15,-15, "ease_in"),  # Olha de lado devagar
            Keyframe(1.5,  0,  30,  30, 35, -10, -15,-15),              # Segura
            Keyframe(2.5,  0,  30,  30,-35, -10,  10, 10, "ease_in"),  # Outro lado
            Keyframe(3.5,  0,  30,  30,-35, -10,  10, 10),
            Keyframe(4.0,  0, 100, 100,  0,   0,   0,  0, "ease_out"),
        ]

        # ---- BOOT UP ----
        lib[SequenceType.BOOT_UP] = [
            Keyframe(0.0,  0,   0,   0,  0,  0,  0,  0),   # Tudo fechado
            Keyframe(0.5,  0,   0,   0,  0,  0,  0,  0),
            Keyframe(0.8,  0,  50,  50,  0,  0,  0,  0, "ease_out"),  # Olhos abrem devagar
            Keyframe(1.2,  0, 100, 100,  0,  0,  0,  0, "ease_out"),
            Keyframe(1.5,  0, 100, 100, 35,  0,  0,  0, "linear"),    # Olha direita
            Keyframe(1.8,  0, 100, 100,-35,  0,  0,  0, "linear"),    # Olha esquerda
            Keyframe(2.1,  0, 100, 100,  0,  0,  0,  0, "ease_out"),  # Centro
            Keyframe(2.4,  5, 100, 100,  0,  5, 10, 10, "ease_in_out"), # Expressão normal
            Keyframe(2.8, 10, 100, 100,  0,  8, 15, 15),               # Abrir boca
            Keyframe(3.2,  0, 100, 100,  0,  0,  0,  0, "ease_out"),
        ]

        # ---- SHUTDOWN ----
        lib[SequenceType.SHUTDOWN] = [
            Keyframe(0.0,  0, 100, 100,  0,  0,  0,  0),
            Keyframe(0.5,  3,  80,  80,  0, -5, -5, -5, "ease_in"),
            Keyframe(1.0,  0,  50,  50,  0,-10,-10,-10),
            Keyframe(1.5,  0,  20,  20,  0,-15,-15,-15),
            Keyframe(2.0,  0,   0,   0,  0,  0,  0,  0, "linear"),   # Fecha tudo
        ]

        # ---- MALFUNCTION ----
        mal = [Keyframe(0.0, 0, 100, 100, 0, 0, 0, 0)]
        for i in range(12):
            t = 0.1 + i * 0.08
            jaw   = random.randint(0, 40)
            leye  = random.randint(0, 100)
            reye  = random.randint(0, 100)
            ex    = random.uniform(-45, 45)
            ey    = random.uniform(-30, 30)
            lear  = random.uniform(-20, 20)
            rear  = random.uniform(-20, 20)
            mal.append(Keyframe(t, jaw, leye, reye, ex, ey, lear, rear, "linear"))
        mal.append(Keyframe(1.1, 0, 100, 100, 0, 0, 0, 0, "ease_out"))
        lib[SequenceType.MALFUNCTION] = mal

        # ---- EMPOLGADO ----
        lib[SequenceType.EXCITED] = [
            Keyframe(0.0,  0, 100, 100,  0,   0,  0,  0),
            Keyframe(0.2, 15, 100, 100,  0,  15, 20, 20, "ease_out"),
            Keyframe(0.4, 20, 100, 100, 15,  15, 20, 20),
            Keyframe(0.6, 15, 100, 100,-15,  15, 20, 20),
            Keyframe(0.8, 20, 100, 100,  0,  15, 20, 20),
            Keyframe(1.0, 10,  90,  90,  0,  10, 15, 15, "ease_in_out"),
            Keyframe(1.3,  0, 100, 100,  0,   5,  5,  5, "ease_out"),
        ]

        # ---- TRISTE ----
        lib[SequenceType.SAD] = [
            Keyframe(0.0,  0, 100, 100,  0,  0,  0,  0),
            Keyframe(0.5,  0,  60,  60,  0, -5,-10,-10, "ease_in"),
            Keyframe(1.0,  0,  50,  50,  0,-10,-15,-15),
            Keyframe(2.0,  0,  50,  50,  0,-10,-15,-15),  # Segura expressão
            Keyframe(2.5,  0, 100, 100,  0,  0,  0,  0, "ease_out"),
        ]

        # ---- ROAR ----
        lib[SequenceType.ROAR] = [
            Keyframe(0.0,  0,  100, 100, 0,   0,  0,  0),
            Keyframe(0.1, 45,  100, 100, 0,  15, 20, 20, "ease_out"),  # Boca abre max RÁPIDO
            Keyframe(0.3, 45,  100, 100, 0,  15, 20, 20),               # Segura
            Keyframe(0.6, 30,  100, 100, 0,   5,  5,  5),
            Keyframe(0.8,  0,  100, 100, 0,   0,  0,  0, "ease_in_out"),
        ]

        # ---- ESPIRRO ----
        lib[SequenceType.SNEEZE] = [
            Keyframe(0.0,  0, 100, 100,  0,  0,  0,  0),
            Keyframe(0.3,  0,  70,  70,  0, 15, 10, 10, "ease_in"),  # Nariz levanta (Y cima)
            Keyframe(0.8,  0,  50,  50,  0, 20, 15, 15),             # Segura
            Keyframe(0.9, 45,  100, 100, 0, -10,-20,-20, "linear"),  # ATCHIM!
            Keyframe(1.1,  0, 100, 100,  0, -5,  5,  5, "ease_out"),
            Keyframe(1.4,  0, 100, 100,  0,  0,  0,  0),
        ]

        return lib

    def play_random_idle(self):
        """Executa uma animação idle aleatória."""
        idle_sequences = [
            SequenceType.EYE_ROLL,
            SequenceType.THINKING,
            SequenceType.WAVE,
        ]
        seq = random.choice(idle_sequences)
        self.play(seq)

    def get_status(self) -> dict:
        return {
            "is_playing": self.is_playing,
            "current_sequence": self.current_sequence.value if self.current_sequence else None,
            "available_sequences": [s.value for s in SequenceType],
        }
