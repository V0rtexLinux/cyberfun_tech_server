"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Hardware Abstraction Layer
Módulo: Controle Direto de Hardware (Servos, Motores, LEDs, Sensores)
================================================================================
Camada de abstração que protege o hardware de comandos conflitantes.
Implementa comunicação serial, controle PWM, e interfaces GPIO.
================================================================================
"""

import numpy as np
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List, Callable, Any
from enum import Enum
import logging
from queue import Queue, Empty

# Importar serial para comunicação real (obrigatório)
import serial
import serial.tools.list_ports
SERIAL_AVAILABLE = True


class HardwareType(Enum):
    """Tipos de hardware controlado"""
    SERVO_PWM = "servo_pwm"
    DC_MOTOR = "dc_motor"
    STEPPER_MOTOR = "stepper_motor"
    LED_RGB = "led_rgb"
    LED_SINGLE = "led_single"
    SENSOR_ANALOG = "sensor_analog"
    SENSOR_DIGITAL = "sensor_digital"
    RELAY = "relay"
    BUZZER = "buzzer"


class ServoProfile(Enum):
    """Perfis de servo pré-configurados"""
    STANDARD_180 = "standard_180"      # 0-180°, 500-2500µs
    STANDARD_270 = "standard_270"      # 0-270°, 500-2500µs
    CONTINUOUS = "continuous"           # Rotação contínua
    MICRO = "micro"                     # Micro servo
    HIGH_TORQUE = "high_torque"         # Alto torque
    LINEAR = "linear"                   # Linear actuator


@dataclass
class ServoConfig:
    """Configuração completa de um servo"""
    servo_id: int
    name: str
    profile: ServoProfile = ServoProfile.STANDARD_180
    min_pulse: int = 500
    max_pulse: int = 2500
    min_angle: float = 0.0
    max_angle: float = 180.0
    neutral_pulse: int = 1500
    max_speed_deg_per_sec: float = 60.0
    torque_kg_cm: float = 1.5
    inverted: bool = False
    enabled: bool = True
    
    # Limites de segurança
    soft_min_pulse: int = 500
    soft_max_pulse: int = 2500
    overcurrent_threshold_ma: int = 500
    max_temperature_c: float = 70.0


@dataclass
class MotorConfig:
    """Configuração de motor DC"""
    motor_id: str
    name: str
    pwm_pin: int
    dir_pin1: int
    dir_pin2: int
    encoder_pin_a: Optional[int] = None
    encoder_pin_b: Optional[int] = None
    max_speed: int = 255
    max_current_ma: int = 3000
    inverted: bool = False


@dataclass
class LEDConfig:
    """Configuração de LED"""
    led_id: str
    name: str
    type: HardwareType
    pins: Tuple[int, ...]  # (r, g, b) ou (single)
    max_brightness: int = 255


@dataclass
class HardwareState:
    """Estado atual de todo o hardware"""
    timestamp: float = field(default_factory=time.time)
    servo_positions: Dict[int, int] = field(default_factory=dict)
    servo_currents: Dict[int, int] = field(default_factory=dict)
    servo_temperatures: Dict[int, float] = field(default_factory=dict)
    motor_speeds: Dict[str, int] = field(default_factory=dict)
    motor_currents: Dict[str, int] = field(default_factory=dict)
    led_states: Dict[str, Tuple[int, int, int]] = field(default_factory=dict)
    analog_sensors: Dict[int, int] = field(default_factory=dict)
    digital_sensors: Dict[int, bool] = field(default_factory=dict)


class SerialProtocol:
    """
    Protocolo de comunicação serial com o controlador de hardware.
    Define comandos e respostas para o microcontrolador.
    """
    
    # Marcadores de protocolo
    START_BYTE = 0xAA
    END_BYTE = 0x55
    ESCAPE_BYTE = 0xBB
    
    # Códigos de comando
    CMD_SERVO_MOVE = 0x01
    CMD_SERVO_SET_SPEED = 0x02
    CMD_SERVO_ENABLE = 0x03
    CMD_SERVO_GET_POS = 0x04
    
    CMD_MOTOR_SET = 0x10
    CMD_MOTOR_STOP = 0x11
    CMD_MOTOR_ENABLE = 0x12
    
    CMD_LED_SET = 0x20
    CMD_LED_BLINK = 0x21
    
    CMD_READ_ANALOG = 0x30
    CMD_READ_DIGITAL = 0x31
    
    CMD_SET_HOME = 0x40
    CMD_ESTOP = 0xFE
    CMD_HEARTBEAT = 0xFF
    
    @staticmethod
    def build_servo_command(servo_id: int, pulse: int, speed: int = 0) -> bytes:
        """Constrói comando de movimento de servo"""
        # Formato: START CMD ID PULSE_HIGH PULSE_LOW SPEED END
        pulse_high = (pulse >> 8) & 0xFF
        pulse_low = pulse & 0xFF
        
        return bytes([
            SerialProtocol.START_BYTE,
            SerialProtocol.CMD_SERVO_MOVE,
            servo_id & 0xFF,
            pulse_high,
            pulse_low,
            speed & 0xFF,
            SerialProtocol.END_BYTE
        ])
    
    @staticmethod
    def build_motor_command(motor_id: int, speed: int, direction: int) -> bytes:
        """Constrói comando de motor"""
        # direction: 0 = forward, 1 = backward
        return bytes([
            SerialProtocol.START_BYTE,
            SerialProtocol.CMD_MOTOR_SET,
            motor_id & 0xFF,
            abs(speed) & 0xFF,
            direction & 0xFF,
            SerialProtocol.END_BYTE
        ])
    
    @staticmethod
    def build_led_command(led_id: int, r: int, g: int, b: int) -> bytes:
        """Constrói comando de LED RGB"""
        return bytes([
            SerialProtocol.START_BYTE,
            SerialProtocol.CMD_LED_SET,
            led_id & 0xFF,
            r & 0xFF,
            g & 0xFF,
            b & 0xFF,
            SerialProtocol.END_BYTE
        ])
    
    @staticmethod
    def build_estop_command() -> bytes:
        """Constrói comando de parada de emergência"""
        return bytes([
            SerialProtocol.START_BYTE,
            SerialProtocol.CMD_ESTOP,
            SerialProtocol.END_BYTE
        ])
    
    @staticmethod
    def build_heartbeat_command() -> bytes:
        """Constrói comando de heartbeat"""
        return bytes([
            SerialProtocol.START_BYTE,
            SerialProtocol.CMD_HEARTBEAT,
            SerialProtocol.END_BYTE
        ])
    
    @staticmethod
    def parse_response(data: bytes) -> Optional[Dict[str, Any]]:
        """Parseia resposta do controlador"""
        if len(data) < 4:
            return None
        
        if data[0] != SerialProtocol.START_BYTE or data[-1] != SerialProtocol.END_BYTE:
            return None
        
        response = {
            'command': data[1],
            'success': data[2] == 0x00,
            'data': list(data[3:-1]) if len(data) > 4 else []
        }
        
        return response


class HardwareController:
    """
    Controlador principal de hardware.
    Gerencia todos os dispositivos conectados ao animatrônico.
    """
    
    def __init__(self, serial_port: str = None, baudrate: int = 115200):
        self.logger = logging.getLogger("Fredbear.Hardware")
        
        # Configuração de hardware
        self.servo_configs: Dict[int, ServoConfig] = {}
        self.motor_configs: Dict[str, MotorConfig] = {}
        self.led_configs: Dict[str, LEDConfig] = {}
        
        # Estado atual
        self.state = HardwareState()
        
        # Comunicação serial
        self.serial_port_name = serial_port
        self.baudrate = baudrate
        self.serial_connection = None
        self.serial_connected = False
        self.serial_lock = threading.RLock()
        
        # Filas de comando
        self.command_queue: Queue = Queue(maxsize=1000)
        self.response_queue: Queue = Queue(maxsize=100)
        
        # Thread de comunicação
        self.running = False
        self.serial_thread = None
        self.reader_thread = None
        
        # Taxa de atualização
        self.update_rate = 60  # Hz
        self.heartbeat_interval = 0.5  # segundos
        self.last_heartbeat = 0.0
        
        # Failsafe
        self.failsafe_active = False
        self.command_timeout = 0.1  # 100ms sem comando = failsafe
        self.last_command_time = 0.0
        
        # Callbacks
        self.on_emergency_callback: Optional[Callable] = None
        self.on_sensor_update_callback: Optional[Callable] = None
        
        # Inicializar com configuração padrão
        self._init_default_config()
        
        self.logger.info("[HARDWARE] Controlador de hardware inicializado")
    
    def _init_default_config(self):
        """Inicializa configuração padrão de hardware do Fredbear"""
        # Servos faciais (CyberFun Endoskeleton)
        facial_servos = [
            ServoConfig(0, "Jaw", ServoProfile.STANDARD_180, min_angle=0, max_angle=45, max_speed_deg_per_sec=120),
            ServoConfig(1, "LeftEyelid", ServoProfile.STANDARD_180, min_angle=0, max_angle=100, max_speed_deg_per_sec=400),
            ServoConfig(2, "RightEyelid", ServoProfile.STANDARD_180, min_angle=0, max_angle=100, max_speed_deg_per_sec=400),
            ServoConfig(3, "EyeX", ServoProfile.STANDARD_180, min_angle=-45, max_angle=45, neutral_pulse=1500),
            ServoConfig(4, "EyeY", ServoProfile.STANDARD_180, min_angle=-30, max_angle=30, neutral_pulse=1500),
            ServoConfig(5, "LeftEar", ServoProfile.STANDARD_180, min_angle=-20, max_angle=20, neutral_pulse=1500),
            ServoConfig(6, "RightEar", ServoProfile.STANDARD_180, min_angle=-20, max_angle=20, neutral_pulse=1500),
        ]
        
        for config in facial_servos:
            self.servo_configs[config.servo_id] = config
            self.state.servo_positions[config.servo_id] = config.neutral_pulse
        
        # Motores de locomoção (tração diferencial)
        self.motor_configs["left"] = MotorConfig("left", "LeftDrive", pwm_pin=10, dir_pin1=11, dir_pin2=12)
        self.motor_configs["right"] = MotorConfig("right", "RightDrive", pwm_pin=13, dir_pin1=14, dir_pin2=15)
        
        self.state.motor_speeds["left"] = 0
        self.state.motor_speeds["right"] = 0
        
        # LEDs dos olhos
        self.led_configs["left_eye"] = LEDConfig("left_eye", "LeftEyeLED", HardwareType.LED_RGB, (5, 6, 7))
        self.led_configs["right_eye"] = LEDConfig("right_eye", "RightEyeLED", HardwareType.LED_RGB, (8, 9, 10))
        
        self.state.led_states["left_eye"] = (0, 100, 255)   # Azul Fredbear
        self.state.led_states["right_eye"] = (0, 100, 255)
    
    def connect(self, port: str = None, baudrate: int = None) -> bool:
        """Conecta ao controlador de hardware via serial"""
        if port:
            self.serial_port_name = port
        if baudrate:
            self.baudrate = baudrate
        
        try:
            # Listar portas disponíveis
            available_ports = [p.device for p in serial.tools.list_ports.comports()]
            self.logger.info(f"[HARDWARE] Portas disponíveis: {available_ports}")
            
            if not available_ports:
                raise Exception("Nenhuma porta serial encontrada. Verifique a conexão do hardware.")
            
            # Conectar
            self.serial_connection = serial.Serial(
                port=self.serial_port_name or available_ports[0],
                baudrate=self.baudrate,
                timeout=0.1,
                write_timeout=0.1
            )
            
            self.serial_connected = True
            self._start_communication_threads()
            
            self.logger.info(f"[HARDWARE] Conectado: {self.serial_connection.port} @ {self.baudrate} baud")
            return True
            
        except Exception as e:
            self.logger.error(f"[HARDWARE] Erro ao conectar: {e}")
            self.serial_connected = False
            raise Exception(f"Falha crítica na conexão serial: {e}. Hardware requerido.")
    
    def _start_communication_threads(self):
        """Inicia threads de comunicação"""
        self.running = True
        
        # Thread de escrita
        self.serial_thread = threading.Thread(target=self._write_loop, daemon=True)
        self.serial_thread.start()
        
        # Thread de leitura
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.reader_thread.start()
    
    def _write_loop(self):
        """Loop de escrita serial"""
        while self.running:
            try:
                # Processar fila de comandos
                if not self.command_queue.empty():
                    cmd = self.command_queue.get_nowait()
                    self._send_command(cmd)
                
                # Enviar heartbeat periódico
                current_time = time.time()
                if current_time - self.last_heartbeat >= self.heartbeat_interval:
                    self._send_heartbeat()
                    self.last_heartbeat = current_time
                
                time.sleep(1.0 / self.update_rate)
                
            except Exception as e:
                self.logger.error(f"[HARDWARE] Erro no loop de escrita: {e}")
    
    def _read_loop(self):
        """Loop de leitura serial"""
        while self.running:
            try:
                if self.serial_connection and self.serial_connection.is_open:
                    if self.serial_connection.in_waiting > 0:
                        data = self.serial_connection.read_all()
                        self._process_response(data)
                
                time.sleep(0.01)  # 10ms polling
                
            except Exception as e:
                self.logger.error(f"[HARDWARE] Erro no loop de leitura: {e}")
    
    def _send_command(self, command: bytes):
        """Envia comando via serial"""
        with self.serial_lock:
            if self.serial_connection and self.serial_connection.is_open:
                try:
                    self.serial_connection.write(command)
                    self.serial_connection.flush()
                    self.last_command_time = time.time()
                except Exception as e:
                    self.logger.error(f"[HARDWARE] Erro ao enviar comando: {e}")
                    self._check_failsafe()
            else:
                raise Exception("Conexão serial não estabelecida. Hardware desconectado.")
    
    def _send_heartbeat(self):
        """Envia heartbeat para controlador"""
        cmd = SerialProtocol.build_heartbeat_command()
        self._send_command(cmd)
    
    def _process_response(self, data: bytes):
        """Processa resposta do controlador"""
        response = SerialProtocol.parse_response(data)
        
        if response:
            self.response_queue.put(response)
            
            # Processar dados de sensores
            if response['command'] in [SerialProtocol.CMD_READ_ANALOG, SerialProtocol.CMD_READ_DIGITAL]:
                self._handle_sensor_data(response)
    
    def _handle_sensor_data(self, response: dict):
        """Processa dados de sensores"""
        if response['command'] == SerialProtocol.CMD_READ_ANALOG:
            # Atualizar sensores analógicos
            pass
        elif response['command'] == SerialProtocol.CMD_READ_DIGITAL:
            # Atualizar sensores digitais
            pass
        
        if self.on_sensor_update_callback:
            self.on_sensor_update_callback(response)
    
    def _check_failsafe(self):
        """Verifica e ativa failsafe se necessário"""
        if time.time() - self.last_command_time > self.command_timeout:
            if not self.failsafe_active:
                self.activate_failsafe()
    
    def activate_failsafe(self):
        """Ativa modo de segurança failsafe"""
        self.failsafe_active = True
        self.logger.warning("[HARDWARE] FAILSAFE ativado")
        
        # Parar todos os motores
        for motor_id in self.motor_configs:
            self.set_motor_speed(motor_id, 0)
        
        # Servos para posição neutra
        for servo_id, config in self.servo_configs.items():
            self._set_servo_pulse_internal(servo_id, config.neutral_pulse)
        
        if self.on_emergency_callback:
            self.on_emergency_callback("failsafe")
    
    def disconnect(self):
        """Desconecta do controlador"""
        self.running = False
        
        # Aguardar threads
        if self.serial_thread:
            self.serial_thread.join(timeout=1.0)
        if self.reader_thread:
            self.reader_thread.join(timeout=1.0)
        
        # Fechar conexão
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        
        self.serial_connected = False
        self.logger.info("[HARDWARE] Desconectado")
    
    # ==================== CONTROLE DE SERVOS ====================
    
    def set_servo_pulse(self, servo_id: int, pulse: int, speed: int = 0) -> bool:
        """
        Define posição de servo via largura de pulso.
        pulse: 500-2500µs
        speed: 0-255 (0 = máxima velocidade)
        """
        if servo_id not in self.servo_configs:
            self.logger.error(f"[HARDWARE] Servo desconhecido: {servo_id}")
            return False
        
        config = self.servo_configs[servo_id]
        
        if not config.enabled:
            return False
        
        # Limitar aos valores seguros
        pulse = int(np.clip(pulse, config.soft_min_pulse, config.soft_max_pulse))
        
        # Inverter se necessário
        if config.inverted:
            pulse = config.max_pulse - (pulse - config.min_pulse)
        
        return self._set_servo_pulse_internal(servo_id, pulse, speed)
    
    def _set_servo_pulse_internal(self, servo_id: int, pulse: int, speed: int = 0) -> bool:
        """Implementação interna de comando de servo"""
        # Atualizar estado
        self.state.servo_positions[servo_id] = pulse
        
        # Construir e enviar comando
        cmd = SerialProtocol.build_servo_command(servo_id, pulse, speed)
        self.command_queue.put(cmd)
        
        return True
    
    def set_servo_angle(self, servo_id: int, angle: float, speed: int = 0) -> bool:
        """
        Define ângulo do servo.
        angle: valor em graus (respeitando min_angle e max_angle)
        """
        if servo_id not in self.servo_configs:
            return False
        
        config = self.servo_configs[servo_id]
        
        # Mapear ângulo para pulso
        angle = np.clip(angle, config.min_angle, config.max_angle)
        ratio = (angle - config.min_angle) / (config.max_angle - config.min_angle)
        
        pulse = int(config.min_pulse + ratio * (config.max_pulse - config.min_pulse))
        
        return self.set_servo_pulse(servo_id, pulse, speed)
    
    def set_multiple_servos(self, positions: Dict[int, int]) -> bool:
        """Define múltiplos servos de uma vez"""
        for servo_id, pulse in positions.items():
            self.set_servo_pulse(servo_id, pulse)
        return True
    
    def get_servo_position(self, servo_id: int) -> int:
        """Retorna posição atual do servo"""
        return self.state.servo_positions.get(servo_id, 1500)
    
    def enable_servo(self, servo_id: int, enabled: bool):
        """Habilita/desabilita servo"""
        if servo_id in self.servo_configs:
            self.servo_configs[servo_id].enabled = enabled
    
    def home_all_servos(self):
        """Move todos os servos para posição neutra"""
        self.logger.info("[HARDWARE] Homing todos os servos")
        
        for servo_id, config in self.servo_configs.items():
            self.set_servo_pulse(servo_id, config.neutral_pulse, speed=50)
    
    # ==================== CONTROLE DE MOTORES ====================
    
    def set_motor_speed(self, motor_id: str, speed: int) -> bool:
        """
        Define velocidade do motor.
        speed: -255 a 255 (negativo = ré)
        """
        if motor_id not in self.motor_configs:
            self.logger.error(f"[HARDWARE] Motor desconhecido: {motor_id}")
            return False
        
        config = self.motor_configs[motor_id]
        
        if self.failsafe_active:
            speed = 0
        
        # Inverter se necessário
        if config.inverted:
            speed = -speed
        
        # Limitar velocidade
        speed = int(np.clip(speed, -config.max_speed, config.max_speed))
        
        # Determinar direção
        direction = 1 if speed < 0 else 0
        abs_speed = abs(speed)
        
        # Atualizar estado
        self.state.motor_speeds[motor_id] = speed if not config.inverted else -speed
        
        # Construir e enviar comando
        motor_index = 0 if motor_id == "left" else 1
        cmd = SerialProtocol.build_motor_command(motor_index, abs_speed, direction)
        self.command_queue.put(cmd)
        
        return True
    
    def set_both_motors(self, left_speed: int, right_speed: int) -> bool:
        """Define velocidade de ambos os motores"""
        self.set_motor_speed("left", left_speed)
        self.set_motor_speed("right", right_speed)
        return True
    
    def stop_all_motors(self):
        """Para todos os motores"""
        self.set_both_motors(0, 0)
    
    # ==================== CONTROLE DE LEDs ====================
    
    def set_led_rgb(self, led_id: str, r: int, g: int, b: int) -> bool:
        """Define cor de LED RGB"""
        if led_id not in self.led_configs:
            return False
        
        config = self.led_configs[led_id]
        
        if config.type != HardwareType.LED_RGB:
            return False
        
        # Limitar valores
        r = int(np.clip(r, 0, config.max_brightness))
        g = int(np.clip(g, 0, config.max_brightness))
        b = int(np.clip(b, 0, config.max_brightness))
        
        # Atualizar estado
        self.state.led_states[led_id] = (r, g, b)
        
        # Enviar comando
        led_index = 0 if led_id == "left_eye" else 1
        cmd = SerialProtocol.build_led_command(led_index, r, g, b)
        self.command_queue.put(cmd)
        
        return True
    
    def set_led_brightness(self, led_id: str, brightness: float):
        """Define brilho do LED (0.0 a 1.0) mantendo cor"""
        if led_id not in self.state.led_states:
            return
        
        r, g, b = self.state.led_states[led_id]
        
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)
        
        self.set_led_rgb(led_id, r, g, b)
    
    # ==================== EMERGÊNCIA ====================
    
    def emergency_stop(self):
        """Parada de emergência imediata"""
        self.logger.warning("[HARDWARE] EMERGÊNCIA - Parando tudo")
        
        # Enviar comando de emergência
        cmd = SerialProtocol.build_estop_command()
        self.command_queue.put(cmd)
        
        # Parar motores localmente
        self.stop_all_motors()
        
        # Ativar failsafe
        self.failsafe_active = True
        
        if self.on_emergency_callback:
            self.on_emergency_callback("emergency_stop")
    
    # ==================== STATUS ====================
    
    def get_status(self) -> dict:
        """Retorna status completo do hardware"""
        return {
            "connected": self.serial_connected,
            "failsafe_active": self.failsafe_active,
            "last_command_time": self.last_command_time,
            "servos": {
                str(sid): {
                    "position": self.state.servo_positions.get(sid, 1500),
                    "enabled": config.enabled,
                    "name": config.name
                }
                for sid, config in self.servo_configs.items()
            },
            "motors": {
                mid: {
                    "speed": self.state.motor_speeds.get(mid, 0),
                    "name": config.name
                }
                for mid, config in self.motor_configs.items()
            },
            "leds": {
                led_id: {
                    "rgb": self.state.led_states.get(led_id, (0, 0, 0)),
                    "name": config.name
                }
                for led_id, config in self.led_configs.items()
            },
            "queues": {
                "commands": self.command_queue.qsize(),
                "responses": self.response_queue.qsize()
            }
        }


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar controlador
    hw = HardwareController()
    
    # Conectar (simulado)
    hw.connect()
    
    # Testar servos
    print("\n[FREDBEAR HARDWARE] Testando servos:")
    hw.set_servo_angle(0, 30)   # Mandíbula
    hw.set_servo_angle(3, 20)   # Olho X
    
    # Testar motores
    print("\n[FREDBEAR HARDWARE] Testando motores:")
    hw.set_motor_speed("left", 100)
    hw.set_motor_speed("right", 100)
    
    # Testar LEDs
    print("\n[FREDBEAR HARDWARE] Testando LEDs:")
    hw.set_led_rgb("left_eye", 0, 255, 0)  # Verde
    
    # Status
    print("\n[FREDBEAR HARDWARE] Status:")
    import json
    print(json.dumps(hw.get_status(), indent=2))