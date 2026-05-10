"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Kernel e Sistema de Segurança
Módulo: FSM (Finite State Machine) e HAL (Hardware Abstraction Layer)
================================================================================
Sistema central de controle que gerencia estados do robô (Ocupado, Vagando,
Showtime, Falha) e protege o hardware através de uma camada de abstração.
Garante que ações conflitantes nunca sejam executadas simultaneamente.
================================================================================
"""

import numpy as np
import threading
import time
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Callable, Any, Set
from enum import Enum
import logging
from queue import Queue, Empty
import signal
import atexit


# ==================== ENUMS DE ESTADO ====================

class SystemState(Enum):
    """Estados principais do sistema animatrônico"""
    OFFLINE = "offline"                 # Sistema desligado
    INITIALIZING = "initializing"       # Inicializando componentes
    IDLE = "idle"                       # Aguardando comando
    WANDERING = "wandering"             # Modo roaming pela pizzaria
    INTERACTING = "interacting"         # Interagindo com cliente
    SHOWTIME = "showtime"               # Executando show
    PERFORMING = "performing"           # Performance no palco
    MAINTENANCE = "maintenance"         # Modo de manutenção
    EMERGENCY = "emergency"             # Estado de emergência
    ERROR = "error"                     # Erro crítico
    SHUTDOWN = "shutdown"               # Desligando


class SubsystemState(Enum):
    """Estados de cada subsistema"""
    OFFLINE = "offline"
    READY = "ready"
    ACTIVE = "active"
    BUSY = "busy"
    ERROR = "error"
    DISABLED = "disabled"


class Priority(Enum):
    """Níveis de prioridade para comandos"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3
    EMERGENCY = 4


class ErrorCode(Enum):
    """Códigos de erro do sistema"""
    NONE = 0
    SERIAL_CONNECTION_LOST = 100
    SERVO_OVERCURRENT = 101
    SERVO_OVERHEAT = 102
    SERVO_POSITION_ERROR = 103
    MOTOR_STALL = 200
    MOTOR_OVERCURRENT = 201
    BATTERY_LOW = 300
    BATTERY_CRITICAL = 301
    VISION_ERROR = 400
    UWB_SIGNAL_LOST = 500
    AUDIO_ERROR = 600
    TIMELINE_ERROR = 601
    UNKNOWN_ERROR = 999


# ==================== ESTRUTURAS DE DADOS ====================

@dataclass
class SystemCommand:
    """Comando do sistema"""
    command_id: int
    command_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    requires_ack: bool = True
    timeout_ms: int = 5000


@dataclass
class SystemEvent:
    """Evento do sistema"""
    event_id: int
    event_type: str
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class SubsystemStatus:
    """Status de um subsistema"""
    name: str
    state: SubsystemState
    last_update: float
    error_code: ErrorCode = ErrorCode.NONE
    error_message: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class SafetyState:
    """Estado de segurança do sistema"""
    emergency_stop_active: bool = False
    serial_connection_healthy: bool = True
    battery_level: float = 100.0
    temperature_ok: bool = True
    motors_enabled: bool = True
    servos_enabled: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    watchdog_timeout_ms: int = 5000


# ==================== HAL (HARDWARE ABSTRACTION LAYER) ====================

class HardwareAbstractionLayer:
    """
    Camada de Abstração de Hardware (HAL).
    Protege o hardware de comandos simultâneos ou conflitantes.
    Gerencia comunicação serial, PWM de servos, e GPIO.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Fredbear.HAL")
        
        # Estado dos servos
        self.servo_positions: Dict[int, int] = {}  # servo_id -> pulse_width
        self.servo_limits: Dict[int, Tuple[int, int]] = {}  # servo_id -> (min_pulse, max_pulse)
        self.servo_enabled: Dict[int, bool] = {}
        
        # Estado dos motores
        self.motor_speeds: Dict[str, int] = {"left": 0, "right": 0}
        self.motors_enabled = True
        
        # Estado dos LEDs
        self.led_states: Dict[str, Tuple[int, int, int]] = {}  # led_name -> (r, g, b)
        
        # Comunicação serial
        self.serial_port: Optional[str] = None
        self.serial_baudrate: int = 115200
        self.serial_connected = False
        self.serial_lock = threading.Lock()
        self.serial_write_queue: Queue = Queue()
        
        # Thread de comunicação
        self.running = False
        self.serial_thread = None
        
        # Buffer de comandos
        self.command_buffer: List[bytes] = []
        self.max_buffer_size = 100
        
        # Controle de taxa de atualização
        self.update_rate = 60  # Hz
        self.min_pulse_interval = 1.0 / self.update_rate
        
        # Failsafe
        self.failsafe_active = False
        self.last_command_time = time.time()
        self.command_timeout = 0.1  # 100ms sem comando = IDLE
        
        # Inicializar
        self._init_default_hardware()
        
        self.logger.info("[HAL] Hardware Abstraction Layer inicializado")
    
    def _init_default_hardware(self):
        """Inicializa configuração padrão de hardware"""
        # Configurar servos padrão (faciais)
        servo_configs = [
            (0, 500, 2500),   # Jaw
            (1, 500, 2500),   # Left Eyelid
            (2, 500, 2500),   # Right Eyelid
            (3, 500, 2500),   # Eye X
            (4, 500, 2500),   # Eye Y
            (5, 500, 2500),   # Left Ear
            (6, 500, 2500),   # Right Ear
        ]
        
        for servo_id, min_pulse, max_pulse in servo_configs:
            self.servo_positions[servo_id] = 1500  # Posição neutra
            self.servo_limits[servo_id] = (min_pulse, max_pulse)
            self.servo_enabled[servo_id] = True
        
        # LEDs padrão
        self.led_states["left_eye"] = (0, 100, 255)  # Azul
        self.led_states["right_eye"] = (0, 100, 255)
    
    def connect_serial(self, port: str, baudrate: int = 115200) -> bool:
        """
        Conecta à porta serial do controlador de hardware.
        Em produção, usaria pyserial para comunicação real.
        """
        self.serial_port = port
        self.serial_baudrate = baudrate
        
        try:
            # Simulação de conexão
            self.serial_connected = True
            self.running = True
            
            # Iniciar thread de comunicação
            self.serial_thread = threading.Thread(target=self._serial_loop, daemon=True)
            self.serial_thread.start()
            
            self.logger.info(f"[HAL] Conectado à porta serial: {port} @ {baudrate} baud")
            return True
            
        except Exception as e:
            self.logger.error(f"[HAL] Erro ao conectar serial: {e}")
            self.serial_connected = False
            return False
    
    def disconnect_serial(self):
        """Desconecta da porta serial"""
        self.running = False
        self.serial_connected = False
        
        if self.serial_thread:
            self.serial_thread.join(timeout=1.0)
        
        # Colocar hardware em estado seguro
        self._emergency_shutdown()
        
        self.logger.info("[HAL] Serial desconectado")
    
    def _serial_loop(self):
        """Loop de comunicação serial"""
        while self.running:
            try:
                # Processar fila de comandos
                self._process_serial_queue()
                
                # Verificar heartbeat
                self._check_connection()
                
                time.sleep(1.0 / self.update_rate)
                
            except Exception as e:
                self.logger.error(f"[HAL] Erro no loop serial: {e}")
    
    def _process_serial_queue(self):
        """Processa fila de comandos seriais"""
        commands_to_send = []
        
        while not self.serial_write_queue.empty():
            try:
                cmd = self.serial_write_queue.get_nowait()
                commands_to_send.append(cmd)
            except Empty:
                break
        
        # Em produção, enviaria via serial real
        if commands_to_send:
            self.last_command_time = time.time()
            self.logger.debug(f"[HAL] {len(commands_to_send)} comandos processados")
    
    def _check_connection(self):
        """Verifica saúde da conexão serial"""
        # Se não houver heartbeat por muito tempo, ativar failsafe
        if time.time() - self.last_command_time > self.command_timeout:
            if not self.failsafe_active:
                self._activate_failsafe()
    
    def _activate_failsafe(self):
        """Ativa modo de segurança automático"""
        self.failsafe_active = True
        self.logger.warning("[HAL] FAILSAFE ativado - sem comunicação")
        
        # Parar motores
        self.motor_speeds["left"] = 0
        self.motor_speeds["right"] = 0
        
        # Servos para posição neutra
        for servo_id in self.servo_positions:
            self.servo_positions[servo_id] = 1500
    
    def _emergency_shutdown(self):
        """Desligamento de emergência de todo hardware"""
        self.failsafe_active = True
        self.motors_enabled = False
        
        for servo_id in self.servo_enabled:
            self.servo_enabled[servo_id] = False
        
        self.motor_speeds = {"left": 0, "right": 0}
        
        self.logger.warning("[HAL] EMERGÊNCIA - Hardware desligado")
    
    # ==================== CONTROLE DE SERVOS ====================
    
    def set_servo_pulse(self, servo_id: int, pulse_width: int) -> bool:
        """
        Define largura de pulso PWM para um servo.
        Valida limites e evita comandos conflitantes.
        """
        if not self.serial_connected and not self.failsafe_active:
            self.logger.warning("[HAL] Serial não conectado")
            return False
        
        if servo_id not in self.servo_limits:
            self.logger.error(f"[HAL] Servo desconhecido: {servo_id}")
            return False
        
        if not self.servo_enabled.get(servo_id, True):
            self.logger.warning(f"[HAL] Servo {servo_id} desabilitado")
            return False
        
        min_pulse, max_pulse = self.servo_limits[servo_id]
        
        # Validar limites
        pulse_width = int(np.clip(pulse_width, min_pulse, max_pulse))
        
        # Verificar se mudou significativamente (evitar spam)
        current_pulse = self.servo_positions.get(servo_id, 1500)
        if abs(pulse_width - current_pulse) < 5:  # Menos de 5µs de diferença
            return True  # Ignorar comando redundante
        
        # Atualizar estado
        self.servo_positions[servo_id] = pulse_width
        
        # Enviar comando
        cmd = self._build_servo_command(servo_id, pulse_width)
        self.serial_write_queue.put(cmd)
        
        return True
    
    def _build_servo_command(self, servo_id: int, pulse_width: int) -> bytes:
        """Constrói comando serial para servo"""
        # Protocolo simples: #<servo_id>P<pulse_width>\n
        cmd_str = f"#{servo_id}P{pulse_width}\n"
        return cmd_str.encode('ascii')
    
    def set_servo_angle(self, servo_id: int, angle: float, 
                        min_angle: float = 0, max_angle: float = 180) -> bool:
        """Define ângulo do servo (converte para pulse width)"""
        if servo_id not in self.servo_limits:
            return False
        
        min_pulse, max_pulse = self.servo_limits[servo_id]
        
        # Mapear ângulo para pulse width
        ratio = (angle - min_angle) / (max_angle - min_angle)
        ratio = np.clip(ratio, 0, 1)
        
        pulse_width = int(min_pulse + ratio * (max_pulse - min_pulse))
        
        return self.set_servo_pulse(servo_id, pulse_width)
    
    def set_multiple_servos(self, positions: Dict[int, int]) -> bool:
        """Define múltiplos servos simultaneamente (comando em lote)"""
        # Construir comando de múltiplos servos
        cmd_parts = []
        
        for servo_id, pulse_width in positions.items():
            if servo_id in self.servo_limits:
                min_pulse, max_pulse = self.servo_limits[servo_id]
                pulse_width = int(np.clip(pulse_width, min_pulse, max_pulse))
                self.servo_positions[servo_id] = pulse_width
                cmd_parts.append(f"#{servo_id}P{pulse_width}")
        
        if cmd_parts:
            cmd_str = " ".join(cmd_parts) + "\n"
            self.serial_write_queue.put(cmd_str.encode('ascii'))
        
        return True
    
    def enable_servo(self, servo_id: int, enabled: bool):
        """Habilita/desabilita um servo específico"""
        self.servo_enabled[servo_id] = enabled
        
        if not enabled:
            # Enviar comando de desabilitar
            cmd = f"#{servo_id}L0\n".encode('ascii')
            self.serial_write_queue.put(cmd)
    
    def get_servo_position(self, servo_id: int) -> int:
        """Retorna posição atual do servo"""
        return self.servo_positions.get(servo_id, 1500)
    
    # ==================== CONTROLE DE MOTORES ====================
    
    def set_motor_speed(self, motor: str, speed: int) -> bool:
        """
        Define velocidade do motor.
        speed: -255 a 255 (negativo = ré)
        """
        if not self.motors_enabled:
            self.logger.warning("[HAL] Motores desabilitados")
            return False
        
        speed = int(np.clip(speed, -255, 255))
        self.motor_speeds[motor] = speed
        
        # Enviar comando
        cmd = f"#M{motor[0].upper()}{speed}\n".encode('ascii')
        self.serial_write_queue.put(cmd)
        
        return True
    
    def set_both_motors(self, left_speed: int, right_speed: int) -> bool:
        """Define velocidade de ambos os motores"""
        left_speed = int(np.clip(left_speed, -255, 255))
        right_speed = int(np.clip(right_speed, -255, 255))
        
        self.motor_speeds["left"] = left_speed
        self.motor_speeds["right"] = right_speed
        
        cmd = f"#ML{left_speed} MR{right_speed}\n".encode('ascii')
        self.serial_write_queue.put(cmd)
        
        return True
    
    def stop_motors(self):
        """Para ambos os motores"""
        self.set_both_motors(0, 0)
    
    def enable_motors(self, enabled: bool):
        """Habilita/desabilita todos os motores"""
        self.motors_enabled = enabled
        
        if not enabled:
            self.stop_motors()
    
    # ==================== CONTROLE DE LEDs ====================
    
    def set_led(self, led_name: str, r: int, g: int, b: int):
        """Define cor de um LED RGB"""
        r = int(np.clip(r, 0, 255))
        g = int(np.clip(g, 0, 255))
        b = int(np.clip(b, 0, 255))
        
        self.led_states[led_name] = (r, g, b)
        
        # Enviar comando
        cmd = f"#LED{led_name[0].upper()}{r:03d}{g:03d}{b:03d}\n".encode('ascii')
        self.serial_write_queue.put(cmd)
    
    def set_led_brightness(self, led_name: str, brightness: float):
        """Define brilho do LED (0.0 a 1.0) preservando cor"""
        if led_name not in self.led_states:
            return
        
        r, g, b = self.led_states[led_name]
        
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)
        
        self.set_led(led_name, r, g, b)
    
    # ==================== LEITURA DE SENSORES ====================
    
    def read_battery_level(self) -> float:
        """Lê nível da bateria (0-100%)"""
        # Em produção, leria via serial/ADC
        return 85.0  # Simulado
    
    def read_temperature(self) -> float:
        """Lê temperatura do sistema"""
        # Em produção, leria via sensor
        return 35.0  # Simulado
    
    def get_status(self) -> dict:
        """Retorna status do HAL"""
        return {
            "serial_connected": self.serial_connected,
            "failsafe_active": self.failsafe_active,
            "motors_enabled": self.motors_enabled,
            "motor_speeds": self.motor_speeds,
            "servos_enabled": self.servo_enabled,
            "servo_positions": self.servo_positions,
            "led_states": self.led_states,
            "buffer_size": self.serial_write_queue.qsize()
        }


# ==================== FSM (FINITE STATE MACHINE) ====================

class FiniteStateMachine:
    """
    Máquina de Estados Finita para o sistema animatrônico.
    Gerencia transições de estado e garante operações seguras.
    """
    
    def __init__(self, hal: HardwareAbstractionLayer):
        self.logger = logging.getLogger("Fredbear.FSM")
        
        # HAL para controle de hardware
        self.hal = hal
        
        # Estado atual
        self.state = SystemState.OFFLINE
        self.previous_state = SystemState.OFFLINE
        
        # Transições permitidas
        self.valid_transitions: Dict[SystemState, Set[SystemState]] = {
            SystemState.OFFLINE: {SystemState.INITIALIZING},
            SystemState.INITIALIZING: {SystemState.IDLE, SystemState.ERROR, SystemState.OFFLINE},
            SystemState.IDLE: {SystemState.WANDERING, SystemState.INTERACTING, 
                              SystemState.SHOWTIME, SystemState.MAINTENANCE,
                              SystemState.EMERGENCY, SystemState.SHUTDOWN},
            SystemState.WANDERING: {SystemState.IDLE, SystemState.INTERACTING,
                                   SystemState.SHOWTIME, SystemState.EMERGENCY},
            SystemState.INTERACTING: {SystemState.IDLE, SystemState.WANDERING,
                                     SystemState.SHOWTIME, SystemState.EMERGENCY},
            SystemState.SHOWTIME: {SystemState.IDLE, SystemState.PERFORMING,
                                  SystemState.EMERGENCY},
            SystemState.PERFORMING: {SystemState.IDLE, SystemState.SHOWTIME,
                                    SystemState.EMERGENCY},
            SystemState.MAINTENANCE: {SystemState.IDLE, SystemState.OFFLINE},
            SystemState.EMERGENCY: {SystemState.IDLE, SystemState.MAINTENANCE,
                                   SystemState.OFFLINE},
            SystemState.ERROR: {SystemState.IDLE, SystemState.MAINTENANCE,
                                SystemState.OFFLINE, SystemState.EMERGENCY},
            SystemState.SHUTDOWN: {SystemState.OFFLINE}
        }
        
        # Callbacks de transição
        self.state_callbacks: Dict[SystemState, List[Callable]] = {
            state: [] for state in SystemState
        }
        
        # Histórico de estados
        self.state_history: List[Tuple[SystemState, float]] = []
        self.max_history = 100
        
        # Condições de transição
        self.transition_conditions: Dict[Tuple[SystemState, SystemState], Callable] = {}
        
        self.logger.info("[FSM] Máquina de Estados inicializada")
    
    def can_transition_to(self, target_state: SystemState) -> bool:
        """Verifica se transição é válida"""
        return target_state in self.valid_transitions.get(self.state, set())
    
    def transition_to(self, target_state: SystemState, force: bool = False) -> bool:
        """
        Tenta transicionar para novo estado.
        Retorna True se sucesso.
        """
        if not force and not self.can_transition_to(target_state):
            self.logger.warning(f"[FSM] Transição inválida: {self.state.value} -> {target_state.value}")
            return False
        
        # Executar condição de transição se existir
        transition_key = (self.state, target_state)
        if transition_key in self.transition_conditions:
            condition = self.transition_conditions[transition_key]
            if not condition():
                self.logger.warning(f"[FSM] Condição de transição não atendida")
                return False
        
        # Registrar histórico
        self.state_history.append((self.state, time.time()))
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)
        
        # Atualizar estado
        self.previous_state = self.state
        self.state = target_state
        
        # Executar callbacks
        self._execute_state_callbacks(target_state)
        
        # Executar ação de hardware se necessário
        self._handle_state_hardware(target_state)
        
        self.logger.info(f"[FSM] Transição: {self.previous_state.value} -> {self.state.value}")
        return True
    
    def _execute_state_callbacks(self, state: SystemState):
        """Executa callbacks registrados para o estado"""
        for callback in self.state_callbacks[state]:
            try:
                callback(self.previous_state, state)
            except Exception as e:
                self.logger.error(f"[FSM] Erro em callback: {e}")
    
    def _handle_state_hardware(self, state: SystemState):
        """Executa ações de hardware baseadas no estado"""
        if state == SystemState.EMERGENCY:
            # Parada de emergência de hardware
            self.hal._emergency_shutdown()
            
        elif state == SystemState.OFFLINE:
            # Desligar hardware
            self.hal.stop_motors()
            self.hal.disconnect_serial()
            
        elif state == SystemState.IDLE:
            # Modo idle - tudo parado mas pronto
            self.hal.stop_motors()
            
        elif state == SystemState.MAINTENANCE:
            # Modo manutenção - hardware acessível
            pass
    
    def register_callback(self, state: SystemState, callback: Callable):
        """Registra callback para quando entrar em um estado"""
        self.state_callbacks[state].append(callback)
    
    def register_transition_condition(self, from_state: SystemState, 
                                      to_state: SystemState, 
                                      condition: Callable[[], bool]):
        """Registra condição que deve ser verdadeira para transição"""
        self.transition_conditions[(from_state, to_state)] = condition
    
    def emergency_transition(self):
        """Força transição para estado de emergência"""
        self.transition_to(SystemState.EMERGENCY, force=True)
    
    def get_state(self) -> SystemState:
        return self.state
    
    def get_state_duration(self) -> float:
        """Retorna tempo no estado atual (segundos)"""
        if self.state_history:
            _, entry_time = self.state_history[-1]
            return time.time() - entry_time
        return 0.0
    
    def get_history(self, n: int = 10) -> List[Tuple[SystemState, float]]:
        """Retorna últimos N estados do histórico"""
        return self.state_history[-n:]


# ==================== KERNEL PRINCIPAL ====================

class FredbearKernel:
    """
    Kernel principal do sistema Fredbear.
    Gerencia FSM, HAL, e coordena todos os subsistemas.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("Fredbear.Kernel")
        
        # Componentes principais
        self.hal = HardwareAbstractionLayer()
        self.fsm = FiniteStateMachine(self.hal)
        
        # Status dos subsistemas
        self.subsystems: Dict[str, SubsystemStatus] = {
            "vision": SubsystemStatus("vision", SubsystemState.OFFLINE, 0),
            "locomotion": SubsystemStatus("locomotion", SubsystemState.OFFLINE, 0),
            "expression": SubsystemStatus("expression", SubsystemState.OFFLINE, 0),
            "audio": SubsystemStatus("audio", SubsystemState.OFFLINE, 0),
            "safety": SubsystemStatus("safety", SubsystemState.OFFLINE, 0),
        }
        
        # Fila de comandos
        self.command_queue: Queue = Queue()
        self.event_queue: Queue = Queue()
        
        # Contador de IDs
        self.command_counter = 0
        self.event_counter = 0
        
        # Thread principal
        self.running = False
        self.kernel_thread = None
        self.update_rate = 100  # Hz
        
        # Estado de segurança
        self.safety = SafetyState()
        
        # Callbacks de evento
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Referências a subsistemas (serão injetadas)
        self.vision_system = None
        self.locomotion_system = None
        self.expression_system = None
        self.audio_system = None
        
        # Configurar handlers de shutdown
        self._setup_shutdown_handlers()
        
        self.logger.info("[KERNEL] Kernel Fredbear inicializado")
    
    def _setup_shutdown_handlers(self):
        """Configura handlers para shutdown gracioso"""
        atexit.register(self.shutdown)
        
        # Handler de sinal para SIGINT/SIGTERM
        def signal_handler(signum, frame):
            self.logger.warning(f"[KERNEL] Sinal recebido: {signum}")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def initialize(self) -> bool:
        """
        Inicializa todos os subsistemas do robô.
        Orquestra a sequência de inicialização segura.
        """
        self.logger.info("[KERNEL] Iniciando inicialização...")
        
        if not self.fsm.transition_to(SystemState.INITIALIZING):
            return False
        
        # Inicializar HAL
        if not self.hal.connect_serial("/dev/ttyUSB0"):
            self.logger.warning("[KERNEL] HAL não conectou - modo simulação")
        
        # Inicializar subsistemas em sequência
        init_sequence = [
            ("safety", self._init_safety),
            ("expression", self._init_expression),
            ("locomotion", self._init_locomotion),
            ("vision", self._init_vision),
            ("audio", self._init_audio),
        ]
        
        for name, init_func in init_sequence:
            try:
                if init_func():
                    self.subsystems[name].state = SubsystemState.READY
                    self.subsystems[name].last_update = time.time()
                    self.logger.info(f"[KERNEL] Subsistema {name} inicializado")
                else:
                    self.subsystems[name].state = SubsystemState.ERROR
                    self.logger.error(f"[KERNEL] Falha ao inicializar {name}")
            except Exception as e:
                self.logger.error(f"[KERNEL] Erro em {name}: {e}")
                self.subsystems[name].state = SubsystemState.ERROR
        
        # Verificar se subsistemas críticos estão OK
        critical_ok = all(
            self.subsystems[name].state != SubsystemState.ERROR
            for name in ["safety", "expression"]
        )
        
        if critical_ok:
            # Iniciar thread principal
            self.running = True
            self.kernel_thread = threading.Thread(target=self._kernel_loop, daemon=True)
            self.kernel_thread.start()
            
            self.fsm.transition_to(SystemState.IDLE)
            self.logger.info("[KERNEL] Inicialização completa!")
            return True
        else:
            self.fsm.transition_to(SystemState.ERROR)
            return False
    
    def _init_safety(self) -> bool:
        """Inicializa subsistema de segurança"""
        self.safety = SafetyState()
        self.safety.last_heartbeat = time.time()
        return True
    
    def _init_expression(self) -> bool:
        """Inicializa subsistema de expressão facial"""
        # Colocar servos em posição neutra
        for servo_id in self.hal.servo_positions:
            self.hal.set_servo_pulse(servo_id, 1500)
        return True
    
    def _init_locomotion(self) -> bool:
        """Inicializa subsistema de locomoção"""
        self.hal.stop_motors()
        return True
    
    def _init_vision(self) -> bool:
        """Inicializa subsistema de visão"""
        return True  # Depende de câmera/TFLite
    
    def _init_audio(self) -> bool:
        """Inicializa subsistema de áudio"""
        return True
    
    def _kernel_loop(self):
        """Loop principal do kernel"""
        last_time = time.time()
        
        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            # Processar comandos
            self._process_commands()
            
            # Atualizar watchdog de segurança
            self._update_safety_watchdog()
            
            # Processar eventos
            self._process_events()
            
            # Atualizar métricas
            self._update_metrics()
            
            # Verificar condições de erro
            self._check_error_conditions()
            
            # Aguardar próximo ciclo
            time.sleep(1.0 / self.update_rate)
    
    def _process_commands(self):
        """Processa comandos pendentes na fila"""
        while not self.command_queue.empty():
            try:
                cmd = self.command_queue.get_nowait()
                self._execute_command(cmd)
            except Empty:
                break
    
    def _execute_command(self, cmd: SystemCommand):
        """Executa um comando do sistema"""
        self.logger.debug(f"[KERNEL] Executando comando: {cmd.command_type}")
        
        # Verificar prioridade vs estado
        if self.fsm.state == SystemState.EMERGENCY:
            if cmd.priority != Priority.EMERGENCY:
                self.logger.warning("[KERNEL] Comando ignorado em emergência")
                return
        
        # Roteamento de comandos
        command_handlers = {
            "set_state": self._cmd_set_state,
            "stop": self._cmd_stop,
            "emergency_stop": self._cmd_emergency_stop,
            "start_show": self._cmd_start_show,
            "stop_show": self._cmd_stop_show,
            "wander": self._cmd_wander,
            "interact": self._cmd_interact,
            "go_home": self._cmd_go_home,
            "set_expression": self._cmd_set_expression,
            "look_at": self._cmd_look_at,
            "speak": self._cmd_speak,
            "play_audio": self._cmd_play_audio,
        }
        
        handler = command_handlers.get(cmd.command_type)
        if handler:
            handler(cmd.params)
        else:
            self.logger.warning(f"[KERNEL] Comando desconhecido: {cmd.command_type}")
    
    def _cmd_set_state(self, params: dict):
        """Comando para mudar estado"""
        state_name = params.get("state")
        try:
            target_state = SystemState(state_name)
            self.fsm.transition_to(target_state)
        except ValueError:
            self.logger.error(f"[KERNEL] Estado inválido: {state_name}")
    
    def _cmd_stop(self, params: dict):
        """Comando de parada"""
        self.fsm.transition_to(SystemState.IDLE)
        self.hal.stop_motors()
    
    def _cmd_emergency_stop(self, params: dict):
        """Comando de emergência"""
        self.fsm.emergency_transition()
        self.safety.emergency_stop_active = True
    
    def _cmd_start_show(self, params: dict):
        """Inicia show"""
        self.fsm.transition_to(SystemState.SHOWTIME)
    
    def _cmd_stop_show(self, params: dict):
        """Para show"""
        self.fsm.transition_to(SystemState.IDLE)
    
    def _cmd_wander(self, params: dict):
        """Inicia modo wandering"""
        self.fsm.transition_to(SystemState.WANDERING)
    
    def _cmd_interact(self, params: dict):
        """Inicia modo de interação"""
        self.fsm.transition_to(SystemState.INTERACTING)
    
    def _cmd_go_home(self, params: dict):
        """Retorna ao palco"""
        self.fsm.transition_to(SystemState.IDLE)
    
    def _cmd_set_expression(self, params: dict):
        """Define expressão facial"""
        # Será conectado ao sistema de expressão
        pass
    
    def _cmd_look_at(self, params: dict):
        """Move olhos para posição"""
        x = params.get("x", 0)
        y = params.get("y", 0)
        # Será conectado ao sistema de expressão
        pass
    
    def _cmd_speak(self, params: dict):
        """Comando de fala"""
        text = params.get("text", "")
        # Será conectado ao sistema de áudio
        pass
    
    def _cmd_play_audio(self, params: dict):
        """Reproduz áudio"""
        file_path = params.get("file", "")
        # Será conectado ao sistema de áudio
        pass
    
    def _update_safety_watchdog(self):
        """Atualiza watchdog de segurança"""
        current_time = time.time()
        
        # Verificar heartbeat
        if current_time - self.safety.last_heartbeat > self.safety.watchdog_timeout_ms / 1000:
            self.logger.error("[KERNEL] Watchdog timeout - sem heartbeat")
            self._trigger_emergency(ErrorCode.SERIAL_CONNECTION_LOST)
        
        # Verificar bateria
        battery = self.hal.read_battery_level()
        self.safety.battery_level = battery
        
        if battery < 10:
            self._trigger_emergency(ErrorCode.BATTERY_CRITICAL)
        elif battery < 20:
            self.logger.warning(f"[KERNEL] Bateria baixa: {battery}%")
        
        # Verificar temperatura
        temp = self.hal.read_temperature()
        if temp > 60:
            self._trigger_emergency(ErrorCode.SERVO_OVERHEAT)
    
    def _trigger_emergency(self, error_code: ErrorCode):
        """Dispara estado de emergência"""
        self.fsm.emergency_transition()
        self.safety.emergency_stop_active = True
        
        # Publicar evento
        self.publish_event("emergency", {
            "error_code": error_code.value,
            "timestamp": time.time()
        })
    
    def _process_events(self):
        """Processa eventos pendentes"""
        while not self.event_queue.empty():
            try:
                event = self.event_queue.get_nowait()
                self._dispatch_event(event)
            except Empty:
                break
    
    def _dispatch_event(self, event: SystemEvent):
        """Despacha evento para handlers"""
        handlers = self.event_handlers.get(event.event_type, [])
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"[KERNEL] Erro em handler de evento: {e}")
    
    def _update_metrics(self):
        """Atualiza métricas de subsistemas"""
        for name, status in self.subsystems.items():
            status.last_update = time.time()
    
    def _check_error_conditions(self):
        """Verifica condições de erro do sistema"""
        # Verificar HAL
        if self.hal.failsafe_active and self.fsm.state != SystemState.EMERGENCY:
            self._trigger_emergency(ErrorCode.SERIAL_CONNECTION_LOST)
    
    # ==================== API PÚBLICA ====================
    
    def send_command(self, command_type: str, params: dict = None,
                    priority: Priority = Priority.NORMAL,
                    source: str = "external") -> int:
        """
        Envia comando para o sistema.
        Retorna ID do comando para tracking.
        """
        self.command_counter += 1
        
        cmd = SystemCommand(
            command_id=self.command_counter,
            command_type=command_type,
            params=params or {},
            priority=priority,
            source=source
        )
        
        self.command_queue.put(cmd)
        return cmd.command_id
    
    def publish_event(self, event_type: str, data: dict = None, source: str = "kernel"):
        """Publica evento no sistema"""
        self.event_counter += 1
        
        event = SystemEvent(
            event_id=self.event_counter,
            event_type=event_type,
            source=source,
            data=data or {}
        )
        
        self.event_queue.put(event)
    
    def register_event_handler(self, event_type: str, handler: Callable):
        """Registra handler para tipo de evento"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def inject_subsystem(self, name: str, subsystem: Any):
        """Injeta referência a subsistema externo"""
        if name == "vision":
            self.vision_system = subsystem
        elif name == "locomotion":
            self.locomotion_system = subsystem
        elif name == "expression":
            self.expression_system = subsystem
        elif name == "audio":
            self.audio_system = subsystem
    
    def heartbeat(self):
        """Recebe heartbeat externo (para watchdog)"""
        self.safety.last_heartbeat = time.time()
    
    def shutdown(self):
        """Desliga o sistema de forma graciosa"""
        self.logger.info("[KERNEL] Iniciando shutdown...")
        
        self.running = False
        
        # Parar subsistemas
        for name in self.subsystems:
            self.subsystems[name].state = SubsystemState.OFFLINE
        
        # Parar hardware
        self.hal.stop_motors()
        self.hal.disconnect_serial()
        
        # Aguardar thread
        if self.kernel_thread:
            self.kernel_thread.join(timeout=2.0)
        
        self.fsm.transition_to(SystemState.SHUTDOWN)
        self.fsm.transition_to(SystemState.OFFLINE)
        
        self.logger.info("[KERNEL] Shutdown completo")
    
    def get_status(self) -> dict:
        """Retorna status completo do sistema"""
        return {
            "state": self.fsm.state.value,
            "previous_state": self.fsm.previous_state.value,
            "state_duration_s": round(self.fsm.get_state_duration(), 2),
            "subsystems": {
                name: {
                    "state": status.state.value,
                    "error_code": status.error_code.value,
                    "error_message": status.error_message
                }
                for name, status in self.subsystems.items()
            },
            "safety": {
                "emergency_stop": self.safety.emergency_stop_active,
                "battery_level": self.safety.battery_level,
                "serial_healthy": self.safety.serial_connection_healthy
            },
            "hal": self.hal.get_status(),
            "queues": {
                "commands_pending": self.command_queue.qsize(),
                "events_pending": self.event_queue.qsize()
            }
        }


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar kernel
    kernel = FredbearKernel()
    
    # Inicializar
    print("\n[FREDBEAR KERNEL] Inicializando...")
    success = kernel.initialize()
    
    print(f"\n[FREDBEAR KERNEL] Status após inicialização:")
    print(json.dumps(kernel.get_status(), indent=2))
    
    # Testar transições de estado
    print("\n[FREDBEAR KERNEL] Testando transições:")
    
    # Ir para modo wandering
    kernel.send_command("wander", priority=Priority.NORMAL)
    time.sleep(0.1)
    print(f"  - Estado: {kernel.fsm.state.value}")
    
    # Comando de emergência
    kernel.send_command("emergency_stop", priority=Priority.EMERGENCY)
    time.sleep(0.1)
    print(f"  - Estado após emergência: {kernel.fsm.state.value}")
    
    # Status final
    print("\n[FREDBEAR KERNEL] Status final:")
    print(json.dumps(kernel.get_status(), indent=2))
    
    # Shutdown
    kernel.shutdown()