"""
================================================================================
FREDBEAR'S SHOW PIZZARIA - Sistema de Segurança
Módulo: Parada de Emergência, Watchdog e Proteção de Hardware
================================================================================
Sistema de segurança para garantir operação segura do animatrônico.
Inclui parada de emergência automática, watchdog de comunicação, e
proteção contra condições perigosas de hardware.
================================================================================
"""

import numpy as np
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable, Tuple, Any
from enum import Enum
import logging
from queue import Queue


class SafetyLevel(Enum):
    """Níveis de segurança/alerta"""
    NORMAL = "normal"
    CAUTION = "caution"
    WARNING = "warning"
    DANGER = "danger"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class SafetyEventType(Enum):
    """Tipos de eventos de segurança"""
    # Hardware
    SERVO_OVERCURRENT = "servo_overcurrent"
    SERVO_OVERHEAT = "servo_overheat"
    SERVO_POSITION_ERROR = "servo_position_error"
    SERVO_DISABLED = "servo_disabled"
    MOTOR_OVERCURRENT = "motor_overcurrent"
    MOTOR_STALL = "motor_stall"
    MOTOR_DISABLED = "motor_disabled"
    
    # Sistema
    BATTERY_LOW = "battery_low"
    BATTERY_CRITICAL = "battery_critical"
    BATTERY_CHARGING = "battery_charging"
    TEMPERATURE_HIGH = "temperature_high"
    TEMPERATURE_CRITICAL = "temperature_critical"
    
    # Comunicação
    SERIAL_DISCONNECTED = "serial_disconnected"
    SERIAL_ERROR = "serial_error"
    WATCHDOG_TIMEOUT = "watchdog_timeout"
    HEARTBEAT_LOST = "heartbeat_lost"
    
    # Sistema
    EMERGENCY_STOP = "emergency_stop"
    EMERGENCY_RELEASE = "emergency_release"
    FAILSAFE_ACTIVATED = "failsafe_activated"
    SYSTEM_FAULT = "system_fault"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class SafetyThresholds:
    """Limites de segurança configuráveis"""
    # Bateria
    battery_low_percent: float = 20.0
    battery_critical_percent: float = 10.0
    battery_warning_percent: float = 30.0
    
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
    
    # Movimento
    max_speed_cm_s: float = 50.0
    max_acceleration_cm_s2: float = 20.0
    collision_distance_cm: float = 30.0


@dataclass
class SafetyEvent:
    """Evento de segurança registrado"""
    event_id: int
    event_type: SafetyEventType
    level: SafetyLevel
    timestamp: float
    source: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False
    resolution_time: Optional[float] = None


@dataclass
class SafetyState:
    """Estado atual de segurança do sistema"""
    # Estado geral
    safety_level: SafetyLevel = SafetyLevel.NORMAL
    emergency_stop_active: bool = False
    failsafe_active: bool = False
    maintenance_mode: bool = False
    
    # Hardware
    motors_enabled: bool = True
    servos_enabled: bool = True
    audio_enabled: bool = True
    vision_enabled: bool = True
    
    # Condições
    serial_connected: bool = False
    heartbeat_received: bool = False
    last_heartbeat_time: float = 0.0
    
    # Sensores
    battery_level: float = 100.0
    system_temperature: float = 25.0
    servo_temperatures: Dict[int, float] = field(default_factory=dict)
    servo_currents: Dict[int, float] = field(default_factory=dict)
    motor_currents: Dict[str, float] = field(default_factory=dict)
    
    # Contadores
    total_emergency_stops: int = 0
    total_failsafe_activations: int = 0
    uptime_seconds: float = 0.0


class SafetyMonitor:
    """
    Monitor de segurança contínuo.
    Verifica condições de segurança em loop dedicado.
    """
    
    def __init__(self, thresholds: SafetyThresholds = None):
        self.logger = logging.getLogger("Fredbear.Safety")
        
        # Configuração
        self.thresholds = thresholds or SafetyThresholds()
        
        # Estado
        self.state = SafetyState()
        
        # Histórico de eventos
        self.event_history: List[SafetyEvent] = []
        self.event_counter = 0
        self.max_history = 1000
        
        # Callbacks
        self.event_callbacks: List[Callable[[SafetyEvent], None]] = []
        self.emergency_callbacks: List[Callable[[], None]] = []
        
        # Thread de monitoramento
        self.running = False
        self.monitor_thread = None
        self.monitor_rate = 50  # Hz
        
        # Locks
        self.state_lock = threading.RLock()
        
        self.logger.info("[SAFETY] Sistema de segurança inicializado")
    
    def start_monitoring(self):
        """Inicia monitoramento contínuo"""
        self.running = True
        self.state.uptime_seconds = 0.0
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("[SAFETY] Monitoramento iniciado")
    
    def stop_monitoring(self):
        """Para monitoramento"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        self.logger.info("[SAFETY] Monitoramento parado")
    
    def _monitor_loop(self):
        """Loop principal de monitoramento"""
        last_time = time.time()
        
        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            with self.state_lock:
                # Atualizar uptime
                self.state.uptime_seconds += dt
                
                # Verificar todas as condições de segurança
                self._check_battery()
                self._check_temperature()
                self._check_communication()
                self._check_currents()
                
                # Atualizar nível de segurança geral
                self._update_safety_level()
            
            time.sleep(1.0 / self.monitor_rate)
    
    def _check_battery(self):
        """Verifica nível da bateria"""
        level = self.state.battery_level
        
        if level <= self.thresholds.battery_critical_percent:
            self._create_event(
                SafetyEventType.BATTERY_CRITICAL,
                SafetyLevel.CRITICAL,
                f"Bateria crítica: {level:.1f}%"
            )
            # Ação: forçar modo economia
            self._disable_non_essential()
            
        elif level <= self.thresholds.battery_low_percent:
            self._create_event(
                SafetyEventType.BATTERY_LOW,
                SafetyLevel.WARNING,
                f"Bateria baixa: {level:.1f}%"
            )
            
        elif level <= self.thresholds.battery_warning_percent:
            self._create_event(
                SafetyEventType.BATTERY_LOW,
                SafetyLevel.CAUTION,
                f"Bateria em atenção: {level:.1f}%"
            )
    
    def _check_temperature(self):
        """Verifica temperatura do sistema"""
        temp = self.state.system_temperature
        
        if temp >= self.thresholds.temperature_critical_c:
            self._create_event(
                SafetyEventType.TEMPERATURE_CRITICAL,
                SafetyLevel.CRITICAL,
                f"Temperatura crítica: {temp:.1f}°C"
            )
            # Ação: parar tudo
            self.trigger_emergency_stop("temperature_critical")
            
        elif temp >= self.thresholds.temperature_high_c:
            self._create_event(
                SafetyEventType.TEMPERATURE_HIGH,
                SafetyLevel.WARNING,
                f"Temperatura alta: {temp:.1f}°C"
            )
            # Ação: reduzir atividade
            
        elif temp >= self.thresholds.temperature_warning_c:
            self._create_event(
                SafetyEventType.TEMPERATURE_HIGH,
                SafetyLevel.CAUTION,
                f"Temperatura elevada: {temp:.1f}°C"
            )
        
        # Verificar temperatura de servos individuais
        for servo_id, servo_temp in self.state.servo_temperatures.items():
            if servo_temp >= self.thresholds.temperature_critical_c:
                self._create_event(
                    SafetyEventType.SERVO_OVERHEAT,
                    SafetyLevel.DANGER,
                    f"Servo {servo_id} superaquecido: {servo_temp:.1f}°C",
                    data={"servo_id": servo_id}
                )
                # Desabilitar servo específico
                self.state.servos_enabled = False
    
    def _check_communication(self):
        """Verifica saúde da comunicação serial"""
        current_time = time.time()
        
        # Verificar heartbeat
        time_since_heartbeat = (current_time - self.state.last_heartbeat_time) * 1000  # ms
        
        if time_since_heartbeat > self.thresholds.heartbeat_timeout_ms:
            self.state.heartbeat_received = False
            
            self._create_event(
                SafetyEventType.HEARTBEAT_LOST,
                SafetyLevel.WARNING,
                f"Heartbeat perdido há {time_since_heartbeat:.0f}ms"
            )
        
        # Verificar watchdog
        if time_since_heartbeat > self.thresholds.watchdog_timeout_ms:
            self._create_event(
                SafetyEventType.WATCHDOG_TIMEOUT,
                SafetyLevel.DANGER,
                "Watchdog timeout - sem comunicação"
            )
            # Ativar failsafe
            self.trigger_failsafe("watchdog_timeout")
        
        # Verificar conexão serial
        if not self.state.serial_connected:
            self._create_event(
                SafetyEventType.SERIAL_DISCONNECTED,
                SafetyLevel.WARNING,
                "Conexão serial perdida"
            )
    
    def _check_currents(self):
        """Verifica correntes de servos e motores"""
        # Servos
        for servo_id, current in self.state.servo_currents.items():
            if current > self.thresholds.servo_overcurrent_ma:
                self._create_event(
                    SafetyEventType.SERVO_OVERCURRENT,
                    SafetyLevel.DANGER,
                    f"Servo {servo_id} sobrecorrente: {current:.0f}mA",
                    data={"servo_id": servo_id, "current_ma": current}
                )
        
        # Motores
        for motor_id, current in self.state.motor_currents.items():
            if current > self.thresholds.motor_overcurrent_ma:
                self._create_event(
                    SafetyEventType.MOTOR_OVERCURRENT,
                    SafetyLevel.DANGER,
                    f"Motor {motor_id} sobrecorrente: {current:.0f}mA",
                    data={"motor_id": motor_id, "current_ma": current}
                )
                # Desabilitar motor
                self.state.motors_enabled = False
    
    def _update_safety_level(self):
        """Atualiza nível de segurança geral do sistema"""
        if self.state.emergency_stop_active:
            self.state.safety_level = SafetyLevel.EMERGENCY
        elif self.state.failsafe_active:
            self.state.safety_level = SafetyLevel.CRITICAL
        elif not self.state.serial_connected:
            self.state.safety_level = SafetyLevel.DANGER
        elif self.state.battery_level < self.thresholds.battery_critical_percent:
            self.state.safety_level = SafetyLevel.CRITICAL
        elif self.state.system_temperature >= self.thresholds.temperature_high_c:
            self.state.safety_level = SafetyLevel.DANGER
        elif self.state.battery_level < self.thresholds.battery_low_percent:
            self.state.safety_level = SafetyLevel.WARNING
        elif not self.state.heartbeat_received:
            self.state.safety_level = SafetyLevel.WARNING
        else:
            self.state.safety_level = SafetyLevel.NORMAL
    
    def _create_event(self, event_type: SafetyEventType, level: SafetyLevel,
                     message: str, source: str = "monitor", data: dict = None) -> SafetyEvent:
        """Cria e registra evento de segurança"""
        self.event_counter += 1
        
        event = SafetyEvent(
            event_id=self.event_counter,
            event_type=event_type,
            level=level,
            timestamp=time.time(),
            source=source,
            message=message,
            data=data or {}
        )
        
        # Adicionar ao histórico
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # Log
        log_msg = f"[SAFETY] {level.value.upper()}: {event_type.value} - {message}"
        if level in [SafetyLevel.CRITICAL, SafetyLevel.EMERGENCY]:
            self.logger.critical(log_msg)
        elif level == SafetyLevel.DANGER:
            self.logger.error(log_msg)
        elif level == SafetyLevel.WARNING:
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)
        
        # Notificar callbacks
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"[SAFETY] Erro em callback: {e}")
        
        return event
    
    def _disable_non_essential(self):
        """Desabilita sistemas não essenciais para economizar energia"""
        self.state.audio_enabled = False
        self.state.vision_enabled = False
    
    # ==================== API PÚBLICA ====================
    
    def trigger_emergency_stop(self, reason: str = "manual"):
        """Dispara parada de emergência"""
        with self.state_lock:
            if self.state.emergency_stop_active:
                return  # Já em emergência
            
            self.state.emergency_stop_active = True
            self.state.motors_enabled = False
            self.state.servos_enabled = False
            self.state.total_emergency_stops += 1
            
            self._create_event(
                SafetyEventType.EMERGENCY_STOP,
                SafetyLevel.EMERGENCY,
                f"Parada de emergência: {reason}",
                data={"reason": reason}
            )
            
            # Notificar callbacks de emergência
            for callback in self.emergency_callbacks:
                try:
                    callback()
                except Exception as e:
                    self.logger.error(f"[SAFETY] Erro em callback de emergência: {e}")
    
    def release_emergency_stop(self):
        """Libera parada de emergência"""
        with self.state_lock:
            self.state.emergency_stop_active = False
            self.state.motors_enabled = True
            self.state.servos_enabled = True
            self.state.safety_level = SafetyLevel.NORMAL
            
            self._create_event(
                SafetyEventType.EMERGENCY_RELEASE,
                SafetyLevel.NORMAL,
                "Parada de emergência liberada"
            )
    
    def trigger_failsafe(self, reason: str = "auto"):
        """Ativa modo failsafe"""
        with self.state_lock:
            self.state.failsafe_active = True
            self.state.total_failsafe_activations += 1
            
            # Parar motores
            self.state.motors_enabled = False
            
            self._create_event(
                SafetyEventType.FAILSAFE_ACTIVATED,
                SafetyLevel.CRITICAL,
                f"Failsafe ativado: {reason}",
                data={"reason": reason}
            )
    
    def release_failsafe(self):
        """Libera modo failsafe"""
        with self.state_lock:
            self.state.failsafe_active = False
            self.state.safety_level = SafetyLevel.NORMAL
    
    def update_battery(self, level: float):
        """Atualiza nível da bateria"""
        with self.state_lock:
            self.state.battery_level = level
    
    def update_temperature(self, temp: float, servo_id: int = None):
        """Atualiza temperatura"""
        with self.state_lock:
            if servo_id is not None:
                self.state.servo_temperatures[servo_id] = temp
            else:
                self.state.system_temperature = temp
    
    def update_current(self, component_id: str, current_ma: float, is_servo: bool = True):
        """Atualiza leitura de corrente"""
        with self.state_lock:
            if is_servo:
                self.state.servo_currents[int(component_id)] = current_ma
            else:
                self.state.motor_currents[component_id] = current_ma
    
    def update_serial_status(self, connected: bool):
        """Atualiza status de conexão serial"""
        with self.state_lock:
            self.state.serial_connected = connected
    
    def receive_heartbeat(self):
        """Registra recebimento de heartbeat"""
        with self.state_lock:
            self.state.heartbeat_received = True
            self.state.last_heartbeat_time = time.time()
    
    def acknowledge_event(self, event_id: int) -> bool:
        """Confirma conhecimento de um evento"""
        for event in self.event_history:
            if event.event_id == event_id:
                event.acknowledged = True
                return True
        return False
    
    def resolve_event(self, event_id: int) -> bool:
        """Marca evento como resolvido"""
        for event in self.event_history:
            if event.event_id == event_id:
                event.resolved = True
                event.resolution_time = time.time()
                return True
        return False
    
    def register_event_callback(self, callback: Callable[[SafetyEvent], None]):
        """Registra callback para eventos de segurança"""
        self.event_callbacks.append(callback)
    
    def register_emergency_callback(self, callback: Callable[[], None]):
        """Registra callback para emergência"""
        self.emergency_callbacks.append(callback)
    
    def can_operate(self) -> bool:
        """Verifica se o sistema pode operar normalmente"""
        with self.state_lock:
            return (not self.state.emergency_stop_active and
                   not self.state.failsafe_active and
                   self.state.serial_connected and
                   self.state.battery_level > self.thresholds.battery_low_percent)
    
    def get_state(self) -> SafetyState:
        """Retorna cópia do estado atual"""
        with self.state_lock:
            return self.state
    
    def get_recent_events(self, count: int = 20, level: SafetyLevel = None) -> List[SafetyEvent]:
        """Retorna eventos recentes"""
        events = list(self.event_history[-count:])
        
        if level:
            events = [e for e in events if e.level == level]
        
        return events
    
    def get_status(self) -> dict:
        """Retorna status completo de segurança"""
        with self.state_lock:
            return {
                "safety_level": self.state.safety_level.value,
                "emergency_stop": self.state.emergency_stop_active,
                "failsafe_active": self.state.failsafe_active,
                "can_operate": self.can_operate(),
                "hardware": {
                    "motors_enabled": self.state.motors_enabled,
                    "servos_enabled": self.state.servos_enabled,
                    "audio_enabled": self.state.audio_enabled,
                    "vision_enabled": self.state.vision_enabled
                },
                "sensors": {
                    "battery_level": round(self.state.battery_level, 1),
                    "temperature": round(self.state.system_temperature, 1),
                    "serial_connected": self.state.serial_connected,
                    "heartbeat": self.state.heartbeat_received
                },
                "statistics": {
                    "uptime_seconds": round(self.state.uptime_seconds, 1),
                    "total_emergency_stops": self.state.total_emergency_stops,
                    "total_failsafe_activations": self.state.total_failsafe_activations
                },
                "recent_events": [
                    {
                        "id": e.event_id,
                        "type": e.event_type.value,
                        "level": e.level.value,
                        "message": e.message,
                        "timestamp": round(e.timestamp, 2),
                        "acknowledged": e.acknowledged
                    }
                    for e in self.get_recent_events(10)
                ]
            }


class EmergencyStopHandler:
    """
    Handler dedicado para parada de emergência.
    Gerencia botões físicos de emergência e LEDs de status.
    """
    
    def __init__(self, safety_monitor: SafetyMonitor):
        self.logger = logging.getLogger("Fredbear.EStop")
        self.safety = safety_monitor
        
        # Estado
        self.estop_buttons: Dict[str, bool] = {}  # button_id -> pressed
        self.estop_led_state = False
        
        # Thread de monitoramento de botões
        self.running = False
        self.button_thread = None
        
        # GPIO (se disponível)
        self.gpio_available = False
        try:
            import RPi.GPIO
            self.gpio = RPi.GPIO
            self.gpio_available = True
        except ImportError:
            pass
    
    def setup_gpio(self, button_pins: Dict[str, int], led_pin: int):
        """Configura GPIOs para botões e LED de emergência"""
        if not self.gpio_available:
            self.logger.warning("[ESTOP] GPIO não disponível")
            return
        
        self.button_pins = button_pins
        self.led_pin = led_pin
        
        try:
            self.gpio.setmode(self.gpio.BCM)
            
            # Configurar botões como entrada com pull-up
            for button_id, pin in button_pins.items():
                self.gpio.setup(pin, self.gpio.IN, pull_up_down=self.gpio.PUD_UP)
                self.estop_buttons[button_id] = False
            
            # Configurar LED
            self.gpio.setup(led_pin, self.gpio.OUT)
            
            self.logger.info(f"[ESTOP] GPIO configurado: {len(button_pins)} botões, LED no pino {led_pin}")
            
        except Exception as e:
            self.logger.error(f"[ESTOP] Erro ao configurar GPIO: {e}")
    
    def start_monitoring(self):
        """Inicia monitoramento de botões de emergência"""
        self.running = True
        self.button_thread = threading.Thread(target=self._button_monitor_loop, daemon=True)
        self.button_thread.start()
        self.logger.info("[ESTOP] Monitoramento de botões iniciado")
    
    def stop_monitoring(self):
        """Para monitoramento"""
        self.running = False
        if self.button_thread:
            self.button_thread.join(timeout=1.0)
    
    def _button_monitor_loop(self):
        """Loop de monitoramento de botões"""
        while self.running:
            if not self.gpio_available:
                time.sleep(0.1)
                continue
            
            try:
                for button_id, pin in self.button_pins.items():
                    # Ler estado (ativo baixo com pull-up)
                    pressed = not self.gpio.input(pin)
                    
                    # Detectar mudança
                    if pressed and not self.estop_buttons[button_id]:
                        self.logger.warning(f"[ESTOP] Botão {button_id} pressionado!")
                        self.safety.trigger_emergency_stop(f"button_{button_id}")
                    
                    self.estop_buttons[button_id] = pressed
                
                # Atualizar LED
                self._update_led()
                
                time.sleep(0.05)  # 50ms polling
                
            except Exception as e:
                self.logger.error(f"[ESTOP] Erro no loop: {e}")
    
    def _update_led(self):
        """Atualiza LED de status de emergência"""
        if not self.gpio_available:
            return
        
        # LED piscando se em emergência
        if self.safety.state.emergency_stop_active:
            self.estop_led_state = not self.estop_led_state
        else:
            self.estop_led_state = False
        
        try:
            self.gpio.output(self.led_pin, self.estop_led_state)
        except:
            pass
    
    def update_led_pattern(self):
        """Atualiza padrão do LED baseado no estado"""
        # Padrões diferentes para estados diferentes
        pass
    
    def get_status(self) -> dict:
        """Retorna status do handler de emergência"""
        return {
            "buttons": self.estop_buttons,
            "led_state": self.estop_led_state,
            "gpio_available": self.gpio_available
        }


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar monitor de segurança
    monitor = SafetyMonitor()
    
    # Iniciar monitoramento
    monitor.start_monitoring()
    
    # Simular algumas condições
    print("\n[FREDBEAR SAFETY] Simulando condições:")
    
    # Bateria baixa
    monitor.update_battery(25.0)
    time.sleep(0.2)
    
    # Restaurar
    monitor.update_battery(85.0)
    time.sleep(0.2)
    
    # Receber heartbeat
    monitor.receive_heartbeat()
    
    # Status
    print("\n[FREDBEAR SAFETY] Status:")
    import json
    print(json.dumps(monitor.get_status(), indent=2))
    
    # Parar
    monitor.stop_monitoring()