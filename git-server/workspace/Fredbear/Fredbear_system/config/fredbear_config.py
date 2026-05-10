"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Configuração Principal
================================================================================
Arquivo de configuração central para todo o sistema animatrônico.
Define parâmetros de hardware, comportamento, e personalidade do Fredbear.
================================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
import json
import os


# ==================== CONFIGURAÇÃO GERAL ====================

@dataclass
class GeneralConfig:
    """Configurações gerais do sistema"""
    # Identificação
    robot_name: str = "Fredbear"
    robot_version: str = "1.0.0"
    establishment_name: str = "Fredbear's Show Pizzaria"
    establishment_year: int = 1989
    
    # Operação
    operating_hours_start: int = 10  # 10:00
    operating_hours_end: int = 22    # 22:00
    maintenance_mode: bool = False
    
    # Debug
    debug_mode: bool = False
    log_level: str = "INFO"
    log_file: str = "/var/log/fredbear.log"


# ==================== CONFIGURAÇÃO DE HARDWARE ====================

@dataclass
class SerialConfig:
    """Configuração de comunicação serial"""
    port: str = "/dev/ttyUSB0"
    baudrate: int = 115200
    timeout: float = 0.1
    retry_count: int = 3
    retry_delay: float = 0.5


@dataclass
class ServoHardwareConfig:
    """Configuração de hardware de servo"""
    servo_id: int
    name: str
    min_pulse: int = 500
    max_pulse: int = 2500
    neutral_pulse: int = 1500
    min_angle: float = 0.0
    max_angle: float = 180.0
    speed: float = 60.0  # graus/segundo
    inverted: bool = False
    enabled: bool = True


@dataclass
class MotorHardwareConfig:
    """Configuração de hardware de motor"""
    motor_id: str
    name: str
    max_speed: int = 255
    max_current_ma: int = 3000
    pwm_pin: int = 0
    dir_pin1: int = 0
    dir_pin2: int = 0
    inverted: bool = False


@dataclass
class LEDHardwareConfig:
    """Configuração de hardware de LED"""
    led_id: str
    name: str
    type: str = "rgb"  # rgb ou single
    pins: Tuple[int, ...] = (0, 0, 0)
    default_color: Tuple[int, int, int] = (0, 100, 255)  # Azul Fredbear


@dataclass
class HardwareConfig:
    """Configuração completa de hardware"""
    serial: SerialConfig = field(default_factory=SerialConfig)
    
    # Servos faciais
    facial_servos: Dict[int, ServoHardwareConfig] = field(default_factory=lambda: {
        0: ServoHardwareConfig(0, "Jaw", min_angle=0, max_angle=45, speed=120),
        1: ServoHardwareConfig(1, "LeftEyelid", min_angle=0, max_angle=100, speed=400),
        2: ServoHardwareConfig(2, "RightEyelid", min_angle=0, max_angle=100, speed=400),
        3: ServoHardwareConfig(3, "EyeX", min_angle=-45, max_angle=45, neutral_pulse=1500),
        4: ServoHardwareConfig(4, "EyeY", min_angle=-30, max_angle=30, neutral_pulse=1500),
        5: ServoHardwareConfig(5, "LeftEar", min_angle=-20, max_angle=20, neutral_pulse=1500),
        6: ServoHardwareConfig(6, "RightEar", min_angle=-20, max_angle=20, neutral_pulse=1500),
    })
    
    # Motores de locomoção
    motors: Dict[str, MotorHardwareConfig] = field(default_factory=lambda: {
        "left": MotorHardwareConfig("left", "LeftDrive", max_speed=200),
        "right": MotorHardwareConfig("right", "RightDrive", max_speed=200),
    })
    
    # LEDs
    leds: Dict[str, LEDHardwareConfig] = field(default_factory=lambda: {
        "left_eye": LEDHardwareConfig("left_eye", "LeftEyeLED", default_color=(0, 100, 255)),
        "right_eye": LEDHardwareConfig("right_eye", "RightEyeLED", default_color=(0, 100, 255)),
    })
    
    # Física do robô
    wheelbase_cm: float = 60.0
    wheel_radius_cm: float = 15.0
    robot_height_cm: float = 180.0
    robot_weight_kg: float = 120.0


# ==================== CONFIGURAÇÃO DE VISÃO ====================

@dataclass
class VisionConfig:
    """Configuração do sistema de visão"""
    # Câmera
    camera_id: int = 0
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    
    # Detecção facial
    model_path: str = "models/face_detection.tflite"
    confidence_threshold: float = 0.7
    iou_threshold: float = 0.5
    input_size: Tuple[int, int] = (320, 320)
    
    # Tracking
    stability_threshold: int = 5  # frames
    tracking_timeout: float = 2.0  # segundos
    max_tracking_distance: int = 300  # cm
    
    # LEDs de feedback
    led_feedback_enabled: bool = True
    led_idle_color: Tuple[int, int, int] = (0, 100, 255)    # Azul
    led_tracking_color: Tuple[int, int, int] = (0, 255, 200)  # Cyan
    led_locked_color: Tuple[int, int, int] = (0, 255, 100)   # Verde


# ==================== CONFIGURAÇÃO DE LOCOMOÇÃO ====================

@dataclass
class NavigationConfig:
    """Configuração de navegação e UWB"""
    # Dimensões do espaço
    room_width_cm: float = 1500.0
    room_height_cm: float = 1000.0
    grid_resolution_cm: float = 10.0
    
    # Âncoras UWB (posições em cm)
    uwb_anchors: List[Tuple[int, float, float]] = field(default_factory=lambda: [
        (0, 0.0, 0.0),
        (1, 1500.0, 0.0),
        (2, 1500.0, 1000.0),
        (3, 0.0, 1000.0),
    ])
    
    # Navegação
    pathfinding_smoothing: int = 3
    robot_radius_cm: float = 40.0
    arrival_radius_cm: float = 20.0
    
    # Velocidades
    max_linear_speed_cm_s: float = 30.0
    max_angular_speed_rad_s: float = 0.5
    max_acceleration_cm_s2: float = 10.0


@dataclass
class WanderingConfig:
    """Configuração do modo roaming"""
    enabled: bool = True
    interval_min_seconds: float = 20.0
    interval_max_seconds: float = 60.0
    visit_tables: bool = True
    return_to_stage_after: int = 3  # visitas
    avoid_crowded_areas: bool = True


@dataclass
class LocomotionConfig:
    """Configuração completa de locomoção"""
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    wandering: WanderingConfig = field(default_factory=WanderingConfig)
    
    # PID do controlador diferencial
    linear_kp: float = 2.0
    linear_ki: float = 0.1
    linear_kd: float = 0.5
    angular_kp: float = 3.0
    angular_ki: float = 0.1
    angular_kd: float = 0.8


# ==================== CONFIGURAÇÃO DE EXPRESSÃO ====================

@dataclass
class ExpressionConfig:
    """Configuração do sistema de expressão facial"""
    # Taxa de atualização
    update_rate_hz: int = 60
    
    # Auto-blink
    auto_blink_enabled: bool = True
    blink_interval_min_seconds: float = 2.0
    blink_interval_max_seconds: float = 6.0
    blink_duration_seconds: float = 0.15
    
    # Lip-sync
    lip_sync_enabled: bool = True
    lip_sync_amplitude_degrees: float = 20.0
    lip_sync_frequency_hz: float = 4.0
    
    # Transições de expressão
    default_transition_duration: float = 0.3
    default_easing: str = "ease_in_out"
    
    # Ranges de movimento
    jaw_max_angle: float = 45.0
    eyelid_max_openness: float = 100.0
    eye_x_max_degrees: float = 45.0
    eye_y_max_degrees: float = 30.0
    ear_max_angle: float = 20.0


# ==================== CONFIGURAÇÃO DE ÁUDIO ====================

@dataclass
class AudioConfig:
    """Configuração do sistema de áudio"""
    # Parâmetros de áudio
    sample_rate: int = 44100
    channels: int = 2
    buffer_size: int = 512
    
    # Volume padrão
    default_volume: float = 0.8
    max_volume: float = 1.0
    
    # Diretório de mídia
    media_directory: str = "/opt/fredbear/media/"
    
    # Shows padrão
    default_show: str = "run_rabbit_run"
    shows: Dict[str, str] = field(default_factory=lambda: {
        "run_rabbit_run": "Run,_Rabbit,_Run_-_Alan_Foster_-_Mack_Triplets.mp3",
        "happy_birthday": "happy_birthday.mp3",
        "celebration": "celebration.mp3",
    })


@dataclass
class ShowConfig:
    """Configuração de shows"""
    # BPM padrão
    default_bpm: int = 120
    
    # Coreografia
    auto_generate_timeline: bool = True
    timeline_directory: str = "/opt/fredbear/timelines/"
    
    # Sincronização
    sync_tolerance_ms: int = 50
    lip_sync_during_singing: bool = True


# ==================== CONFIGURAÇÃO DE SEGURANÇA ====================

@dataclass
class SafetyThresholdsConfig:
    """Limites de segurança"""
    # Bateria
    battery_warning_percent: float = 30.0
    battery_low_percent: float = 20.0
    battery_critical_percent: float = 10.0
    
    # Temperatura
    temperature_warning_c: float = 50.0
    temperature_high_c: float = 60.0
    temperature_critical_c: float = 70.0
    
    # Corrente
    servo_overcurrent_ma: int = 500
    motor_overcurrent_ma: int = 3000
    
    # Comunicação
    watchdog_timeout_ms: int = 5000
    heartbeat_timeout_ms: int = 2000
    serial_retry_count: int = 3


@dataclass
class EmergencyConfig:
    """Configuração de emergência"""
    # Botões de emergência (GPIO pins se disponível)
    estop_buttons: Dict[str, int] = field(default_factory=lambda: {
        "main": 17,
        "stage_left": 18,
        "stage_right": 19,
    })
    
    estop_led_pin: int = 27
    
    # Ações de emergência
    auto_stop_on_serial_loss: bool = True
    auto_stop_on_collision: bool = True
    auto_home_on_startup: bool = True


@dataclass
class SafetyConfig:
    """Configuração completa de segurança"""
    thresholds: SafetyThresholdsConfig = field(default_factory=SafetyThresholdsConfig)
    emergency: EmergencyConfig = field(default_factory=EmergencyConfig)
    
    # Monitoramento
    monitor_rate_hz: int = 50
    log_all_events: bool = True
    event_history_size: int = 1000


# ==================== CONFIGURAÇÃO DE PERSONALIDADE ====================

@dataclass
class PersonalityConfig:
    """Configuração de personalidade do Fredbear"""
    # Nome e backstory
    character_name: str = "Fredbear"
    character_description: str = "O animatrônico original da Fredbear's Family Diner"
    
    # Comportamento
    greeting_phrases: List[str] = field(default_factory=lambda: [
        "Olá, bem-vindo à Fredbear's Show Pizzaria!",
        "Hey! Que bom ver você por aqui!",
        "Bem-vindo, amigo! Pronto para se divertir?",
        "Oi! Espero que você esteja com fome de pizza!",
    ])
    
    farewell_phrases: List[str] = field(default_factory=lambda: [
        "Tchau! Volte sempre!",
        "Até a próxima! Foi ótimo ter você aqui!",
        "Adeus, amigo! Divirta-se!",
    ])
    
    happy_phrases: List[str] = field(default_factory=lambda: [
        "Isto é incrível!",
        "Que divertido!",
        "Eu amo minha pizzaria!",
        "Ha ha ha! Isso é muito engraçado!",
    ])
    
    # Expressões padrão
    default_emotion: str = "happy"
    idle_emotion: str = "neutral"
    greeting_emotion: str = "excited"
    
    # Timing de interação
    greeting_cooldown_seconds: float = 5.0
    min_interaction_time_seconds: float = 2.0
    max_interaction_distance_cm: float = 300.0


# ==================== CONFIGURAÇÃO DE WAYPOINTS ====================

@dataclass
class WaypointConfig:
    """Configuração de waypoints da pizzaria"""
    waypoint_id: int
    name: str
    x_cm: float
    y_cm: float
    is_stage: bool = False
    is_table: bool = False
    is_restricted: bool = False


@dataclass
class PizzariaLayout:
    """Layout da pizzaria"""
    waypoints: List[WaypointConfig] = field(default_factory=lambda: [
        # Palco principal
        WaypointConfig(0, "Palco Principal", 750.0, 100.0, is_stage=True),
        
        # Mesas dos clientes
        WaypointConfig(1, "Mesa 1", 400.0, 400.0, is_table=True),
        WaypointConfig(2, "Mesa 2", 750.0, 400.0, is_table=True),
        WaypointConfig(3, "Mesa 3", 1100.0, 400.0, is_table=True),
        WaypointConfig(4, "Mesa 4", 400.0, 700.0, is_table=True),
        WaypointConfig(5, "Mesa 5", 750.0, 700.0, is_table=True),
        WaypointConfig(6, "Mesa 6", 1100.0, 700.0, is_table=True),
        
        # Área de espera
        WaypointConfig(7, "Entrada", 750.0, 950.0),
        
        # Backstage (restrito)
        WaypointConfig(8, "Backstage", 100.0, 900.0, is_restricted=True),
    ])
    
    # Obstáculos fixos
    obstacles: List[Tuple[float, float, float]] = field(default_factory=lambda: [
        # (x, y, radius_cm)
        (750.0, 50.0, 60.0),   # Área do palco
        (200.0, 200.0, 30.0),  # Pilar
        (1300.0, 200.0, 30.0), # Pilar
        (200.0, 800.0, 30.0),  # Pilar
        (1300.0, 800.0, 30.0), # Pilar
    ])


# ==================== CONFIGURAÇÃO PRINCIPAL ====================

@dataclass
class FredbearConfig:
    """Configuração principal do sistema Fredbear"""
    general: GeneralConfig = field(default_factory=GeneralConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    locomotion: LocomotionConfig = field(default_factory=LocomotionConfig)
    expression: ExpressionConfig = field(default_factory=ExpressionConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    show: ShowConfig = field(default_factory=ShowConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    layout: PizzariaLayout = field(default_factory=PizzariaLayout)
    
    def to_dict(self) -> dict:
        """Converte configuração para dicionário"""
        def asdict_recursive(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return {k: asdict_recursive(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, list):
                return [asdict_recursive(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: asdict_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, tuple):
                return tuple(asdict_recursive(item) for item in obj)
            else:
                return obj
        
        return asdict_recursive(self)
    
    def save_to_file(self, filepath: str):
        """Salva configuração em arquivo JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'FredbearConfig':
        """Carrega configuração de arquivo JSON"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # TODO: Implementar parsing completo do JSON
        return cls()


# Configuração global padrão
DEFAULT_CONFIG = FredbearConfig()


def get_config() -> FredbearConfig:
    """Retorna a configuração atual do sistema"""
    return DEFAULT_CONFIG


def reload_config(config_path: str = None) -> FredbearConfig:
    """Recarrega configuração de arquivo"""
    global DEFAULT_CONFIG
    
    if config_path and os.path.exists(config_path):
        DEFAULT_CONFIG = FredbearConfig.load_from_file(config_path)
    else:
        DEFAULT_CONFIG = FredbearConfig()
    
    return DEFAULT_CONFIG


# Módulo de Teste
if __name__ == "__main__":
    config = FredbearConfig()
    
    print("\n[FREDBEAR CONFIG] Configuração padrão:")
    print(f"  - Robô: {config.general.robot_name}")
    print(f"  - Estabelecimento: {config.general.establishment_name}")
    print(f"  - Servos faciais: {len(config.hardware.facial_servos)}")
    print(f"  - Waypoints: {len(config.layout.waypoints)}")
    print(f"  - Waypoints: {config.layout.waypoints}")
    
    # Salvar exemplo
    config.save_to_file("fredbear_config_example.json")
    print("\n[FREDBEAR CONFIG] Exemplo salvo em fredbear_config_example.json")