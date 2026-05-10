"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Utilitários e Funções Auxiliares
================================================================================
Funções helper e utilitários para o sistema animatrônico.
================================================================================
"""

import time
import math
import numpy as np
from typing import Tuple, List, Dict, Any, Optional, Callable
from dataclasses import dataclass
import threading
import logging


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Limita um valor entre mínimo e máximo."""
    return max(min_val, min(max_val, value))


def lerp(a: float, b: float, t: float) -> float:
    """Interpolação linear entre a e b."""
    return a + (b - a) * t


def smooth_step(t: float) -> float:
    """Função de smooth step (0-1)."""
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_in_quad(t: float) -> float:
    """Easing quadrático de entrada."""
    return t * t


def ease_out_quad(t: float) -> float:
    """Easing quadrático de saída."""
    return t * (2 - t)


def ease_in_out_quad(t: float) -> float:
    """Easing quadrático de entrada e saída."""
    if t < 0.5:
        return 2 * t * t
    return -1 + (4 - 2 * t) * t


def ease_in_cubic(t: float) -> float:
    """Easing cúbico de entrada."""
    return t * t * t


def ease_out_cubic(t: float) -> float:
    """Easing cúbico de saída."""
    t -= 1
    return t * t * t + 1


def ease_in_out_cubic(t: float) -> float:
    """Easing cúbico de entrada e saída."""
    if t < 0.5:
        return 4 * t * t * t
    t -= 0.5
    return 4 * t * t * t + 1


def ease_in_sine(t: float) -> float:
    """Easing senoidal de entrada."""
    return 1 - math.cos(t * math.pi / 2)


def ease_out_sine(t: float) -> float:
    """Easing senoidal de saída."""
    return math.sin(t * math.pi / 2)


def ease_in_out_sine(t: float) -> float:
    """Easing senoidal de entrada e saída."""
    return -(math.cos(math.pi * t) - 1) / 2


def angle_to_pwm(angle: float, min_angle: float, max_angle: float,
                 min_pulse: int, max_pulse: int) -> int:
    """Converte ângulo para largura de pulso PWM."""
    ratio = (angle - min_angle) / (max_angle - min_angle)
    ratio = clamp(ratio, 0.0, 1.0)
    return int(min_pulse + ratio * (max_pulse - min_pulse))


def pwm_to_angle(pulse: int, min_pulse: int, max_pulse: int,
                 min_angle: float, max_angle: float) -> float:
    """Converte largura de pulso PWM para ângulo."""
    ratio = (pulse - min_pulse) / (max_pulse - min_pulse)
    ratio = clamp(ratio, 0.0, 1.0)
    return min_angle + ratio * (max_angle - min_angle)


def normalize_angle(angle: float, min_angle: float, max_angle: float) -> float:
    """Normaliza ângulo para o range especificado."""
    range_size = max_angle - min_angle
    angle = (angle - min_angle) % range_size + min_angle
    return angle


def degrees_to_radians(degrees: float) -> float:
    """Converte graus para radianos."""
    return degrees * math.pi / 180.0


def radians_to_degrees(radians: float) -> float:
    """Converte radianos para graus."""
    return radians * 180.0 / math.pi


def distance_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    """Calcula distância Euclidiana 2D."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def distance_3d(x1: float, y1: float, z1: float,
                x2: float, y2: float, z2: float) -> float:
    """Calcula distância Euclidiana 3D."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def angle_between_points(x1: float, y1: float, x2: float, y2: float) -> float:
    """Calcula ângulo entre dois pontos (em radianos)."""
    return math.atan2(y2 - y1, x2 - x1)


def rotate_point(x: float, y: float, angle_rad: float,
                cx: float = 0, cy: float = 0) -> Tuple[float, float]:
    """Rotaciona um ponto ao redor de um centro."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    
    dx = x - cx
    dy = y - cy
    
    rx = dx * cos_a - dy * sin_a + cx
    ry = dx * sin_a + dy * cos_a + cy
    
    return rx, ry


def low_pass_filter(current: float, previous: float, alpha: float = 0.3) -> float:
    """Filtro passa-baixa para suavização."""
    return previous + alpha * (current - previous)


def moving_average(values: List[float], window: int) -> List[float]:
    """Calcula média móvel de uma lista de valores."""
    if len(values) < window:
        return values
    
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        avg = sum(values[start:i + 1]) / (i - start + 1)
        result.append(avg)
    
    return result


def rms(values: List[float]) -> float:
    """Calcula RMS (Root Mean Square) de uma lista."""
    if not values:
        return 0.0
    return math.sqrt(sum(v ** 2 for v in values) / len(values))


def normalize_rms(audio_data: np.ndarray, target_rms: float = 0.1) -> np.ndarray:
    """Normaliza RMS de dados de áudio."""
    current_rms = np.sqrt(np.mean(audio_data ** 2))
    if current_rms > 0:
        return audio_data * (target_rms / current_rms)
    return audio_data


def format_time_ms(ms: int) -> str:
    """Formata milissegundos em MM:SS.mmm."""
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    millis = ms % 1000
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def format_time_s(seconds: float) -> str:
    """Formata segundos em MM:SS."""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"


class RateLimiter:
    """Limitador de taxa de execução."""
    
    def __init__(self, rate_hz: float):
        self.rate = rate_hz
        self.min_interval = 1.0 / rate_hz
        self.last_time = 0.0
    
    def can_execute(self) -> bool:
        """Verifica se pode executar baseado na taxa."""
        current = time.time()
        if current - self.last_time >= self.min_interval:
            self.last_time = current
            return True
        return False
    
    def wait(self):
        """Aguarda até poder executar."""
        current = time.time()
        elapsed = current - self.last_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_time = time.time()


class Debouncer:
    """Debouncer para eventos."""
    
    def __init__(self, delay: float):
        self.delay = delay
        self.last_call = 0.0
        self.pending = False
        self.pending_args = None
    
    def call(self, func: Callable, *args, **kwargs):
        """Chama função com debounce."""
        current = time.time()
        
        if current - self.last_call >= self.delay:
            self.last_call = current
            func(*args, **kwargs)
            self.pending = False
        else:
            self.pending = True
            self.pending_args = (func, args, kwargs)
    
    def flush(self):
        """Executa chamada pendente."""
        if self.pending and self.pending_args:
            func, args, kwargs = self.pending_args
            func(*args, **kwargs)
            self.pending = False


class ThreadPool:
    """Pool simples de threads."""
    
    def __init__(self, num_threads: int = 4):
        self.num_threads = num_threads
        self.tasks = []
        self.lock = threading.Lock()
        self.workers = []
        self.running = True
        
        for _ in range(num_threads):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def _worker_loop(self):
        while self.running:
            task = None
            with self.lock:
                if self.tasks:
                    task = self.tasks.pop(0)
            
            if task:
                func, args, kwargs = task
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    logging.error(f"Thread error: {e}")
            else:
                time.sleep(0.01)
    
    def submit(self, func: Callable, *args, **kwargs):
        with self.lock:
            self.tasks.append((func, args, kwargs))
    
    def shutdown(self):
        self.running = False
        for worker in self.workers:
            worker.join(timeout=1.0)


class Singleton(type):
    """Metaclass para implementar Singleton."""
    
    _instances = {}
    _lock = threading.Lock()
    
    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Cria logger configurado."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def validate_range(value: float, min_val: float, max_val: float,
                  name: str = "value") -> float:
    """Valida e limita um valor a um range."""
    if value < min_val:
        logging.warning(f"{name} {value} below minimum {min_val}, clamping")
        return min_val
    if value > max_val:
        logging.warning(f"{name} {value} above maximum {max_val}, clamping")
        return max_val
    return value


# Módulo de teste
if __name__ == "__main__":
    print("=== FREDBEAR UTILITIES TEST ===")
    
    # Teste de easing
    print("\nEasing functions:")
    for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
        print(f"  t={t:.2f}: ease_in_out_cubic={ease_in_out_cubic(t):.3f}")
    
    # Teste de conversão
    print("\nAngle to PWM:")
    for angle in [0, 45, 90, 135, 180]:
        pwm = angle_to_pwm(angle, 0, 180, 500, 2500)
        print(f"  {angle}° -> {pwm}µs")
    
    # Teste de distância
    print("\nDistância 2D:")
    print(f"  (0,0) to (3,4) = {distance_2d(0, 0, 3, 4):.2f}")
    
    # Teste de formatadores
    print("\nFormatadores de tempo:")
    print(f"  123456ms -> {format_time_ms(123456)}")
    print(f"  125.5s -> {format_time_s(125.5)}")