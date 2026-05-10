"""
================================================================================
Configuração Centralizada - Sistema YAML-based
================================================================================
Gerencia todas as configurações dos animatrônicos via arquivos YAML,
eliminando hardcoded values.
================================================================================
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path


@dataclass
class ServoConfig:
    """Configuração de servo motor"""
    id: int
    name: str
    min_angle: float = 0.0
    max_angle: float = 180.0
    min_pulse: int = 500
    max_pulse: int = 2500
    neutral_pulse: int = 1500
    max_speed: float = 100.0
    inverted: bool = False


@dataclass
class MotorConfig:
    """Configuração de motor DC"""
    id: str
    name: str
    pwm_pin: int
    dir_pins: List[int]
    max_speed: int = 255
    encoder_pins: Optional[List[int]] = None


@dataclass
class SensorConfig:
    """Configuração de sensores"""
    pir_pin: int = 17
    ultrasonic_trigger: int = 23
    ultrasonic_echo: int = 24
    imu_i2c_addr: int = 0x68
    mic_device: int = 0


@dataclass
class AIConfig:
    """Configuração de IA"""
    backend_priority: List[str] = field(default_factory=lambda: ["openai", "ollama", "fallback"])
    openai_model: str = "gpt-4o-mini"
    ollama_model: str = "llama3.2:3b"
    ollama_host: str = "http://localhost:11434"
    max_tokens: int = 100
    temperature: float = 0.8
    conversation_history_size: int = 10


@dataclass
class VisionConfig:
    """Configuração de visão computacional"""
    enabled: bool = True
    camera_index: int = 0
    resolution: tuple = (640, 480)
    fps: int = 30
    face_detection_model: str = "haarcascade"
    tflite_model_path: Optional[str] = None
    detection_threshold: float = 0.5
    track_faces: bool = True
    max_tracking_distance: int = 100


@dataclass
class NetworkConfig:
    """Configuração de rede"""
    websocket_port: int = 8765
    web_interface_port: int = 8080
    enable_remote_control: bool = True
    max_clients: int = 5


@dataclass
class PersonalityConfig:
    """Configuração de personalidade do animatrônico"""
    name: str = "Animatronic"
    character_type: str = "friendly"
    default_voice: str = "robot_male"
    system_prompt: str = ""
    available_modes: List[str] = field(default_factory=lambda: ["friendly", "excited", "guardian"])
    greetings: List[str] = field(default_factory=list)
    jokes: List[str] = field(default_factory=list)


@dataclass
class LocomotionConfig:
    """Configuração de locomoção avançada"""
    enabled: bool = True
    wheel_base: float = 0.3  # metros
    wheel_diameter: float = 0.08  # metros
    max_linear_speed: float = 0.5  # m/s
    max_angular_speed: float = 1.0  # rad/s
    enable_slam: bool = False
    enable_pathfinding: bool = False
    obstacle_detection_range: float = 1.0  # metros
    safety_stop_distance: float = 0.2  # metros
    map_resolution: float = 0.05  # metros/célula
    map_size: tuple = (10, 10)  # metros x metros


@dataclass
class AnimatronicConfig:
    """Configuração completa do animatrônico"""
    name: str
    version: str = "3.1.0"
    
    # Subsistemas
    hardware: Dict[str, ServoConfig] = field(default_factory=dict)
    motors: Dict[str, MotorConfig] = field(default_factory=dict)
    sensors: SensorConfig = field(default_factory=SensorConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    locomotion: LocomotionConfig = field(default_factory=LocomotionConfig)
    
    # Logging
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: str = "logs"
    
    # Debug
    debug_mode: bool = False
    simulate_hardware: bool = False


def load_config(config_path: str) -> AnimatronicConfig:
    """
    Carrega configuração de arquivo YAML.
    
    Args:
        config_path: Caminho para o arquivo YAML
        
    Returns:
        AnimatronicConfig: Objeto de configuração
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    return _dict_to_config(data)


def _dict_to_config(data: Dict[str, Any]) -> AnimatronicConfig:
    """Converte dicionário para dataclass"""
    
    config = AnimatronicConfig(
        name=data.get("name", "Unknown"),
        version=data.get("version", "3.1.0"),
        log_level=data.get("logging", {}).get("level", "INFO"),
        log_to_file=data.get("logging", {}).get("to_file", True),
        log_dir=data.get("logging", {}).get("directory", "logs"),
        debug_mode=data.get("debug", {}).get("enabled", False),
        simulate_hardware=data.get("debug", {}).get("simulate_hardware", False),
    )
    
    # Hardware / Servos
    if "hardware" in data and "servos" in data["hardware"]:
        for servo_data in data["hardware"]["servos"]:
            servo = ServoConfig(**servo_data)
            config.hardware[servo.name] = servo
    
    # Motores
    if "motors" in data:
        for motor_data in data["motors"]:
            motor = MotorConfig(**motor_data)
            config.motors[motor.id] = motor
    
    # Sensores
    if "sensors" in data:
        config.sensors = SensorConfig(**data["sensors"])
    
    # IA
    if "ai" in data:
        config.ai = AIConfig(**data["ai"])
    
    # Visão
    if "vision" in data:
        vision_data = data["vision"].copy()
        if "resolution" in vision_data:
            vision_data["resolution"] = tuple(vision_data["resolution"])
        config.vision = VisionConfig(**vision_data)
    
    # Rede
    if "network" in data:
        config.network = NetworkConfig(**data["network"])
    
    # Personalidade
    if "personality" in data:
        config.personality = PersonalityConfig(**data["personality"])
    
    # Locomoção
    if "locomotion" in data:
        config.locomotion = LocomotionConfig(**data["locomotion"])
    
    return config


def save_config(config: AnimatronicConfig, config_path: str):
    """Salva configuração para arquivo YAML"""
    data = _config_to_dict(config)
    
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _config_to_dict(config: AnimatronicConfig) -> Dict[str, Any]:
    """Converte dataclass para dicionário"""
    return {
        "name": config.name,
        "version": config.version,
        "hardware": {
            "servos": [
                {
                    "id": s.id,
                    "name": s.name,
                    "min_angle": s.min_angle,
                    "max_angle": s.max_angle,
                    "min_pulse": s.min_pulse,
                    "max_pulse": s.max_pulse,
                    "neutral_pulse": s.neutral_pulse,
                    "max_speed": s.max_speed,
                    "inverted": s.inverted,
                }
                for s in config.hardware.values()
            ]
        },
        "motors": [
            {
                "id": m.id,
                "name": m.name,
                "pwm_pin": m.pwm_pin,
                "dir_pins": m.dir_pins,
                "max_speed": m.max_speed,
                "encoder_pins": m.encoder_pins,
            }
            for m in config.motors.values()
        ],
        "sensors": config.sensors.__dict__,
        "ai": config.ai.__dict__,
        "vision": {
            **config.vision.__dict__,
            "resolution": list(config.vision.resolution),
        },
        "network": config.network.__dict__,
        "personality": config.personality.__dict__,
        "locomotion": config.locomotion.__dict__,
        "logging": {
            "level": config.log_level,
            "to_file": config.log_to_file,
            "directory": config.log_dir,
        },
        "debug": {
            "enabled": config.debug_mode,
            "simulate_hardware": config.simulate_hardware,
        },
    }


# Configurações padrão para Fredbear
def get_fredbear_default_config() -> AnimatronicConfig:
    """Retorna configuração padrão do Fredbear"""
    return AnimatronicConfig(
        name="Fredbear",
        personality=PersonalityConfig(
            name="Fredbear",
            character_type="golden_bear",
            default_voice="robot_male",
            system_prompt="""Você é o Fredbear, o animatrônico principal da Pizzaria Fredbear's Family Diner.
Você é um urso dourado robótico amigável e carismático.
Características:
- Fala em português brasileiro
- É entusiasmado com festas, pizza e diversão
- Ama crianças e famílias
- Conta piadas ruins mas engraçadas
- Às vezes faz referências a ser um robô/animatrônico
- Nunca quebra o personagem
- Respostas curtas (máximo 2 frases) para parecer natural como robô
- Usa expressões como "YEAAH!", "Que INCRÍVEL!", "Vamos nessa!""",
            greetings=[
                "Olá olá! Bem-vindo à melhor pizzaria do universo!",
                "Ei você! Sim, você mesmo! Bem-vindo!",
                "Ooooh! Temos um visitante! TODOS APLAUDAM!",
            ],
            jokes=[
                "Por que o robô foi ao médico? Porque tinha vírus! HA HA HA!",
                "O que o computador come? Chips de batata e bytes!",
                "Por que a pizza vai ao psicólogo? Porque está se sentindo em pedaços!",
            ],
        ),
        vision=VisionConfig(
            face_detection_model="haarcascade_frontalface_default.xml",
            track_faces=True,
        ),
    )


# Configurações padrão para Springbonnie
def get_springbonnie_default_config() -> AnimatronicConfig:
    """Retorna configuração padrão do Springbonnie"""
    return AnimatronicConfig(
        name="Springbonnie",
        personality=PersonalityConfig(
            name="Springbonnie",
            character_type="rabbit",
            default_voice="cheerful",
            system_prompt="""Você é o Springbonnie, o coelho animatrônico da Pizzaria Fredbear's Family Diner.
Você é energético, brincalhão e adora saltitar!
Características:
- Fala em português brasileiro
- Muito energético e sempre em movimento
- Adora brincadeiras e surpresas
- Faz muitas referências a cenouras
- Dá pulinhos de empolgação
- Respostas curtas e animadas
- Usa expressões como "Hop hop!", "Vamos pular!", "Cenoura!""",
            greetings=[
                "Hop hop! Olá pessoal!",
                "Springbonnie chegou para animar!",
                "Quem quer brincar comigo?",
            ],
            jokes=[
                "Por que o coelho foi ao barbeiro? Para cortar as orelhas!",
                "O que o coelho disse para a cenoura? Vou te pegar!",
                "Como o coelho viaja? De pulo-em-pulo!",
            ],
        ),
        vision=VisionConfig(
            face_detection_model="haarcascade_frontalface_default.xml",
            track_faces=True,
        ),
    )
