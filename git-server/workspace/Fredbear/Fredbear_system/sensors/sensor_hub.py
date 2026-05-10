"""
================================================================================
  CYBER FUN ENDOSKELETON - Hub Central de Sensores
  Gerencia todos os sensores: PIR, Ultrassônico, IMU, Temperatura, Câmera
================================================================================
"""

import threading
import time
import queue
import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List
from enum import Enum

logger = logging.getLogger("CyberFun.Sensors")


class SensorType(Enum):
    PIR         = "pir"
    ULTRASONIC  = "ultrasonic"
    IMU         = "imu"
    TEMPERATURE = "temperature"
    BATTERY     = "battery"
    CAMERA      = "camera"
    MICROPHONE  = "microphone"
    TOUCH       = "touch"


@dataclass
class SensorReading:
    sensor_type: SensorType
    value: object
    timestamp: float = field(default_factory=time.time)
    unit: str = ""
    sensor_id: str = ""


@dataclass
class IMUData:
    acc_x: float = 0.0
    acc_y: float = 0.0
    acc_z: float = 0.0
    gyr_x: float = 0.0
    gyr_y: float = 0.0
    gyr_z: float = 0.0
    roll:  float = 0.0
    pitch: float = 0.0
    yaw:   float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class UltrasonicData:
    front_cm:  float = 999.0
    back_cm:   float = 999.0
    left_cm:   float = 999.0
    right_cm:  float = 999.0
    timestamp: float = field(default_factory=time.time)

    def min_distance(self) -> float:
        return min(self.front_cm, self.back_cm, self.left_cm, self.right_cm)

    def is_obstacle_near(self, threshold_cm: float = 30.0) -> bool:
        return self.min_distance() < threshold_cm

    def obstacle_direction(self) -> str:
        distances = {
            "front": self.front_cm,
            "back":  self.back_cm,
            "left":  self.left_cm,
            "right": self.right_cm
        }
        return min(distances, key=distances.get)


class SerialSensorParser:
    """
    Parseia leituras de sensores vindas do Arduino via serial.
    Formato: @<TYPE> <DATA>
    """

    def __init__(self):
        self.callbacks: Dict[str, Callable] = {}

    def register(self, sensor_prefix: str, callback: Callable):
        self.callbacks[sensor_prefix] = callback

    def parse_line(self, line: str) -> Optional[SensorReading]:
        """Parseia uma linha de dados do Arduino."""
        line = line.strip()
        if not line.startswith("@"):
            return None

        parts = line[1:].split(" ", 1)
        if len(parts) < 2:
            return None

        prefix = parts[0]
        data   = parts[1]

        if prefix in self.callbacks:
            try:
                return self.callbacks[prefix](data)
            except Exception as e:
                logger.error(f"[SENSORS] Erro ao parsear {prefix}: {e}")

        return None


class PIRSensor:
    """Sensor de presença passivo infrared."""

    def __init__(self):
        self.detected = False
        self.last_detected_time = 0.0
        self.detection_count = 0
        self.cooldown_s = 2.0
        self.on_detected: Optional[Callable] = None
        self.on_lost: Optional[Callable] = None

    def update(self, detected: bool):
        was_detected = self.detected
        self.detected = detected

        if detected and not was_detected:
            self.last_detected_time = time.time()
            self.detection_count += 1
            logger.info(f"[PIR] Presença detectada! (total: {self.detection_count})")
            if self.on_detected:
                self.on_detected()

        elif not detected and was_detected:
            logger.info("[PIR] Presença perdida")
            if self.on_lost:
                self.on_lost()

    def time_since_last_detection(self) -> float:
        return time.time() - self.last_detected_time if self.last_detected_time > 0 else float('inf')


class UltrasonicSensorHub:
    """Gerencia os 4 sensores ultrassônicos."""

    def __init__(self):
        self.data = UltrasonicData()
        self.obstacle_threshold_cm = 40.0
        self.on_obstacle: Optional[Callable[[str, float], None]] = None
        self._prev_obstacle = False

    def update(self, direction: str, distance_cm: float):
        setattr(self.data, f"{direction}_cm", distance_cm)
        self.data.timestamp = time.time()

        # Checar obstáculo
        is_near = self.data.is_obstacle_near(self.obstacle_threshold_cm)
        if is_near and not self._prev_obstacle:
            dir_name = self.data.obstacle_direction()
            dist = getattr(self.data, f"{dir_name}_cm")
            logger.warning(f"[ULTRASONIC] Obstáculo detectado! {dir_name}: {dist:.0f}cm")
            if self.on_obstacle:
                self.on_obstacle(dir_name, dist)
        self._prev_obstacle = is_near

    def get_data(self) -> UltrasonicData:
        return self.data


class IMUSensor:
    """Sensor IMU MPU-6050 (acelerômetro + giroscópio)."""

    def __init__(self):
        self.data = IMUData()
        self._kalman_roll  = 0.0
        self._kalman_pitch = 0.0
        self.on_tilt: Optional[Callable[[float, float], None]] = None
        self.tilt_threshold_deg = 20.0

    def update(self, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z):
        dt = time.time() - self.data.timestamp if self.data.timestamp > 0 else 0.01

        self.data.acc_x, self.data.acc_y, self.data.acc_z = acc_x, acc_y, acc_z
        self.data.gyr_x, self.data.gyr_y, self.data.gyr_z = gyr_x, gyr_y, gyr_z
        self.data.timestamp = time.time()

        # Calcular ângulos via acelerômetro
        acc_roll  = np.degrees(np.arctan2(acc_y, acc_z))
        acc_pitch = np.degrees(np.arctan2(-acc_x, np.sqrt(acc_y**2 + acc_z**2)))

        # Filtro complementar (0.96 giroscópio + 0.04 acelerômetro)
        self.data.roll  = 0.96 * (self.data.roll  + gyr_x * dt) + 0.04 * acc_roll
        self.data.pitch = 0.96 * (self.data.pitch + gyr_y * dt) + 0.04 * acc_pitch

        # Detectar inclinação excessiva
        if abs(self.data.roll) > self.tilt_threshold_deg or abs(self.data.pitch) > self.tilt_threshold_deg:
            if self.on_tilt:
                self.on_tilt(self.data.roll, self.data.pitch)


class MicrophoneSensor:
    """
    Sensor de microfone para detecção de som e análise de áudio em tempo real.
    Usado para lip-sync reativo e detecção de palmas/gritos.
    """

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.rms_level = 0.0
        self.peak_level = 0.0
        self.is_speech = False
        self.speech_threshold = 0.02
        self.clap_threshold = 0.15

        self.on_speech_start: Optional[Callable] = None
        self.on_speech_end:   Optional[Callable] = None
        self.on_clap:         Optional[Callable] = None
        self.on_audio_chunk:  Optional[Callable] = None

        self.running = False
        self._thread = None

    def start(self):
        """Inicia captura de microfone."""
        try:
            import pyaudio
            self.running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            logger.info("[MIC] Captura de microfone iniciada")
        except ImportError:
            logger.warning("[MIC] pyaudio não disponível. pip install pyaudio")

    def _capture_loop(self):
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            was_speech = False
            while self.running:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                audio = np.frombuffer(data, dtype=np.float32)

                self.rms_level  = float(np.sqrt(np.mean(audio**2)))
                self.peak_level = float(np.max(np.abs(audio)))

                # Detecção de fala
                is_speech_now = self.rms_level > self.speech_threshold
                if is_speech_now and not was_speech:
                    if self.on_speech_start: self.on_speech_start()
                elif not is_speech_now and was_speech:
                    if self.on_speech_end: self.on_speech_end()
                was_speech = is_speech_now

                # Detecção de palmas (pico alto e curto)
                if self.peak_level > self.clap_threshold:
                    if self.on_clap: self.on_clap()

                # Callback de chunk de áudio (lip-sync)
                if self.on_audio_chunk:
                    self.on_audio_chunk(audio)

            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception as e:
            logger.error(f"[MIC] Erro na captura: {e}")

    def stop(self):
        self.running = False

    def get_rms(self) -> float:
        return self.rms_level


class SensorHub:
    """
    Hub central que agrega todos os sensores do animatrônico.
    Parseia dados seriais do Arduino e expõe dados unificados.
    """

    def __init__(self):
        self.pir        = PIRSensor()
        self.ultrasonic = UltrasonicSensorHub()
        self.imu        = IMUSensor()
        self.microphone = MicrophoneSensor()

        self.battery_voltage = 12.0
        self.system_temp_c   = 25.0

        # Parser serial
        self.parser = SerialSensorParser()
        self._register_parsers()

        # Fila de eventos de sensores
        self.event_queue: queue.Queue = queue.Queue(maxsize=100)

        # Callbacks globais
        self.on_sensor_event: Optional[Callable[[SensorReading], None]] = None

        logger.info("[SENSORS] Hub de sensores inicializado")

    def _register_parsers(self):
        """Registra parsers para cada tipo de dado do Arduino."""

        def parse_pir(data: str) -> SensorReading:
            detected = data.strip() == "1"
            self.pir.update(detected)
            return SensorReading(SensorType.PIR, detected, unit="bool", sensor_id="pir0")

        def parse_us_front(data: str) -> SensorReading:
            dist = float(data.strip())
            self.ultrasonic.update("front", dist)
            return SensorReading(SensorType.ULTRASONIC, dist, unit="cm", sensor_id="us_front")

        def parse_us_back(data: str) -> SensorReading:
            dist = float(data.strip())
            self.ultrasonic.update("back", dist)
            return SensorReading(SensorType.ULTRASONIC, dist, unit="cm", sensor_id="us_back")

        def parse_us_left(data: str) -> SensorReading:
            dist = float(data.strip())
            self.ultrasonic.update("left", dist)
            return SensorReading(SensorType.ULTRASONIC, dist, unit="cm", sensor_id="us_left")

        def parse_us_right(data: str) -> SensorReading:
            dist = float(data.strip())
            self.ultrasonic.update("right", dist)
            return SensorReading(SensorType.ULTRASONIC, dist, unit="cm", sensor_id="us_right")

        def parse_imu(data: str) -> SensorReading:
            vals = [float(v) for v in data.strip().split(",")]
            if len(vals) == 6:
                self.imu.update(*vals)
            return SensorReading(SensorType.IMU, vals, unit="mixed", sensor_id="imu0")

        def parse_battery(data: str) -> SensorReading:
            self.battery_voltage = float(data.strip())
            return SensorReading(SensorType.BATTERY, self.battery_voltage, unit="V", sensor_id="bat0")

        self.parser.register("PIR", parse_pir)
        self.parser.register("UF",  parse_us_front)
        self.parser.register("UB",  parse_us_back)
        self.parser.register("UL",  parse_us_left)
        self.parser.register("UR",  parse_us_right)
        self.parser.register("IMU", parse_imu)
        self.parser.register("BAT", parse_battery)

    def process_serial_line(self, line: str):
        """Processa uma linha de dados serial do Arduino."""
        reading = self.parser.parse_line(line)
        if reading:
            self.event_queue.put(reading)
            if self.on_sensor_event:
                self.on_sensor_event(reading)

    def start_microphone(self):
        self.microphone.start()

    def get_status(self) -> dict:
        us = self.ultrasonic.data
        imu = self.imu.data
        return {
            "pir": {
                "detected": self.pir.detected,
                "detection_count": self.pir.detection_count,
                "last_seen_s": round(self.pir.time_since_last_detection(), 1)
            },
            "ultrasonic": {
                "front_cm": round(us.front_cm, 1),
                "back_cm":  round(us.back_cm, 1),
                "left_cm":  round(us.left_cm, 1),
                "right_cm": round(us.right_cm, 1),
                "obstacle_near": us.is_obstacle_near()
            },
            "imu": {
                "roll_deg":  round(imu.roll, 1),
                "pitch_deg": round(imu.pitch, 1),
                "acc": [round(imu.acc_x,2), round(imu.acc_y,2), round(imu.acc_z,2)],
                "gyr": [round(imu.gyr_x,1), round(imu.gyr_y,1), round(imu.gyr_z,1)],
            },
            "microphone": {
                "rms_level": round(self.microphone.rms_level, 4),
                "peak_level": round(self.microphone.peak_level, 4),
                "is_speech": self.microphone.is_speech,
            },
            "battery": {
                "voltage_v": round(self.battery_voltage, 2),
                "percent":   round(min(100, max(0, (self.battery_voltage - 10.0) / 2.5 * 100)), 1)
            },
            "temperature_c": round(self.system_temp_c, 1),
        }
