"""
================================================================================
  CYBER FUN ENDOSKELETON - Sistema Principal (Raspberry Pi 4)
  Versão 3.0 - ULTRA AVANÇADO
================================================================================
  Sistema completo de controle do animatrônico Cyber Fun:
    - Comunicação serial com Arduino Mega 2560
    - Expressões faciais avançadas com micro-expressões
    - Sincronia labial (lip-sync) em tempo real
    - Texto-para-fala (TTS) em português
    - Inteligência Artificial (GPT-4o / Ollama local)
    - Detecção facial via câmera (TFLite)
    - Sensores completos (PIR, Ultrassônico, IMU, Microfone)
    - Navegação autônoma com desvio de obstáculos
    - Sistema de shows com timeline sincronizada
    - Servidor WebSocket para controle remoto
    - Máquina de estados finita (FSM) para comportamento seguro
    - Watchdog de segurança e parada de emergência
================================================================================
  Inicialização:
    python3 main.py [--port /dev/ttyACM0] [--no-camera] [--no-ai] [--debug]
================================================================================
"""

import sys
import os
import time
import signal
import logging
import threading
import argparse
import json
from typing import Optional

# ==================== CONFIGURAÇÃO DE LOGGING ====================
def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]

    # Log em arquivo
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler(f"logs/cyberfun_{int(time.time())}.log")
    file_handler.setLevel(logging.DEBUG)
    handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s",
        handlers=handlers
    )


logger = logging.getLogger("CyberFun.Main")


# ==================== BANNER ====================
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║       CYBER FUN ENDOSKELETON - Sistema v3.0                  ║
║       Raspberry Pi 4 × Arduino Mega 2560                     ║
║                                                              ║
║  Módulos: TTS | IA | Visão | Sensores | WebSocket | Shows    ║
╚══════════════════════════════════════════════════════════════╝
"""


class CyberFunSystem:
    """
    Sistema principal do animatrônico Cyber Fun.
    Orquestra todos os subsistemas e gerencia o ciclo de vida.
    """

    def __init__(self, args):
        self.args = args
        self.running = False
        self.subsystems = {}

        # ---- Subsistemas ----
        self.kernel     = None
        self.hal        = None
        self.expression = None
        self.show       = None
        self.tts        = None
        self.ai         = None
        self.vision     = None
        self.sensors    = None
        self.locomotion = None
        self.ws_server  = None
        self.sequences  = None

        # Thread de loop principal
        self.main_thread = None

    def initialize(self) -> bool:
        """Inicializa todos os subsistemas em ordem."""
        logger.info("=" * 60)
        logger.info("  Iniciando CyberFun v3.0...")
        logger.info("=" * 60)

        try:
            # 1. HAL (Hardware Abstraction Layer)
            logger.info("[INIT] 1/9 - Hardware Abstraction Layer...")
            from springbonnie_system.hal.hardware_controller import HardwareController
            self.hal = HardwareController(
                serial_port=self.args.port,
                baudrate=115200
            )

            if not self.args.no_hardware:
                try:
                    self.hal.connect(self.args.port)
                    logger.info("  ✓ Hardware conectado")
                except Exception as e:
                    logger.warning(f"  ⚠ Hardware offline (simulado): {e}")

            # 2. Expressões Faciais
            logger.info("[INIT] 2/9 - Sistema de Expressão Facial...")
            from springbonnie_system.expression.facial_controller import FacialExpressionController
            self.expression = FacialExpressionController()
            self.expression.set_pwm_callback(self.hal.set_servo_pulse)
            self.expression.start_expression_loop()
            logger.info("  ✓ Expressões faciais ativas")

            # 3. Sensores
            logger.info("[INIT] 3/9 - Hub de Sensores...")
            from springbonnie_system.sensors.sensor_hub import SensorHub
            self.sensors = SensorHub()
            self.sensors.pir.on_detected = self._on_presence_detected
            self.sensors.ultrasonic.on_obstacle = self._on_obstacle_detected
            self.sensors.imu.on_tilt = self._on_excessive_tilt

            if not self.args.no_mic:
                self.sensors.start_microphone()
                self.sensors.microphone.on_audio_chunk = self._on_audio_chunk

            logger.info("  ✓ Sensores inicializados")

            # 4. Sequências de Animação
            logger.info("[INIT] 4/9 - Sequências de Animação...")
            from springbonnie_system.sequences.animation_sequences import SequencePlayer
            self.sequences = SequencePlayer()
            self.sequences.inject_systems(expression=self.expression)
            logger.info("  ✓ Sequências carregadas")

            # 5. TTS (Text-to-Speech)
            logger.info("[INIT] 5/9 - Motor de Síntese de Voz...")
            from springbonnie_system.tts.tts_engine import TTSManager
            self.tts = TTSManager()
            self.tts.on_speaking_start = self._on_tts_start
            self.tts.on_speaking_end   = self._on_tts_end
            self.tts.on_phoneme        = self._on_phoneme  # Lip-sync
            self.tts.start()
            logger.info(f"  ✓ TTS: engines={self.tts._available_engines}")

            # 6. IA (Brain)
            if not self.args.no_ai:
                logger.info("[INIT] 6/9 - Cérebro de IA...")
                from springbonnie_system.ai.ai_brain import AIChatBrain
                self.ai = AIChatBrain(openai_key=os.environ.get("OPENAI_API_KEY"))
                self.ai.on_response = self._on_ai_response
                self.ai.start()
                logger.info(f"  ✓ IA: backend={self.ai._active_backend}")
            else:
                logger.info("[INIT] 6/9 - IA desabilitada (--no-ai)")

            # 7. Sistema de Shows
            logger.info("[INIT] 7/9 - Orquestrador de Shows...")
            from springbonnie_system.audio.show_orchestrator import ShowOrchestrator, EventType
            self.show = ShowOrchestrator()
            self._register_show_callbacks()
            self._load_default_shows()
            logger.info("  ✓ Shows carregados")

            # 8. Kernel / FSM
            logger.info("[INIT] 8/9 - Kernel e FSM...")
            from springbonnie_system.kernel.fsm_kernel import SpringbonnieKernel
            self.kernel = SpringbonnieKernel()
            self.kernel.initialize()
            logger.info("  ✓ Kernel FSM ativo")

            # 9. Servidor WebSocket
            if not self.args.no_network:
                logger.info("[INIT] 9/9 - Servidor WebSocket...")
                from springbonnie_system.network.ws_server import CyberFunWebServer
                self.ws_server = CyberFunWebServer(port=self.args.ws_port)
                self.ws_server.inject_systems(
                    kernel=self.kernel,
                    tts=self.tts,
                    ai=self.ai,
                    expression=self.expression,
                    show=self.show
                )
                self.ws_server.start()
                logger.info(f"  ✓ WebSocket: ws://0.0.0.0:{self.args.ws_port}")
            else:
                logger.info("[INIT] 9/9 - WebSocket desabilitado (--no-network)")

            # Animação de boot
            from Springbonnie_system.sequences.animation_sequences import SequenceType
            self.sequences.play(SequenceType.BOOT_UP, blocking=True)
            time.sleep(0.5)

            # Anunciar inicialização
            if self.tts:
                self.tts.speak("Sistema Cyber Fun iniciado. Pronto para diversão!")

            logger.info("=" * 60)
            logger.info("  ✓ SISTEMA COMPLETAMENTE INICIALIZADO!")
            logger.info(f"  Dashboard: http://$(hostname -I | cut -d' ' -f1):{self.args.ws_port}")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.critical(f"[INIT] FALHA CRÍTICA: {e}", exc_info=True)
            return False

    def run(self):
        """Loop principal do sistema."""
        self.running = True
        logger.info("[MAIN] Sistema em execução. Ctrl+C para parar.")

        idle_timer = time.time()
        idle_interval_s = 30.0   # Animação idle a cada 30s sem atividade

        while self.running:
            try:
                now = time.time()

                # Heartbeat para o Arduino
                if self.hal and self.hal.serial_connected:
                    self.hal._send_heartbeat()

                # Idle animation
                if self.sequences and not self.sequences.is_playing:
                    if now - idle_timer > idle_interval_s:
                        self._do_idle_behavior()
                        idle_timer = now

                # Broadcast de status para WebSocket
                if self.ws_server:
                    self.ws_server.broadcast("STATUS", self._get_full_status())

                time.sleep(0.5)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"[MAIN] Erro no loop principal: {e}")
                time.sleep(1.0)

        self.shutdown()

    def _do_idle_behavior(self):
        """Comportamento idle aleatório."""
        import random
        from Springbonnie_system.sequences.animation_sequences import SequenceType

        behaviors = [
            lambda: self.sequences.play(SequenceType.EYE_ROLL),
            lambda: self.sequences.play(SequenceType.THINKING),
            lambda: self._random_look(),
            lambda: self.expression.do_wink(random.choice(["left", "right"])),
        ]
        random.choice(behaviors)()

    def _random_look(self):
        """Olha em direção aleatória."""
        import random
        x = random.uniform(-30, 30)
        y = random.uniform(-15, 15)
        self.expression.look_at(x, y)
        time.sleep(1.0)
        self.expression.look_at(0, 0)

    # ==================== CALLBACKS ====================

    def _on_presence_detected(self):
        """Reage quando alguém é detectado pelo PIR."""
        logger.info("[MAIN] Presença detectada - reagindo!")
        from Springbonnie_system.sequences.animation_sequences import SequenceType
        from Springbonnie_system.expression.facial_controller import EmotionPreset
        from Springbonnie_system.tts.tts_engine import TTSVoice

        self.expression.set_emotion(EmotionPreset.EXCITED, duration=0.3)
        self.sequences.play(SequenceType.GREETING)

        if self.tts:
            self.tts.speak_preset("greeting_day", voice=TTSVoice.CHEERFUL)

        if self.ws_server:
            self.ws_server.broadcast("EVENT", {"type": "presence_detected"})

    def _on_obstacle_detected(self, direction: str, distance_cm: float):
        """Reage a obstáculo detectado pelos sensores ultrassônicos."""
        logger.warning(f"[MAIN] Obstáculo: {direction} @ {distance_cm:.0f}cm")

        if self.kernel:
            self.kernel.send_command("stop_motors", {})

        if self.tts and distance_cm < 20:
            self.tts.speak_now("Cuidado! Obstáculo detectado!")

        if self.ws_server:
            self.ws_server.broadcast("EVENT", {
                "type": "obstacle",
                "direction": direction,
                "distance_cm": distance_cm
            })

    def _on_excessive_tilt(self, roll: float, pitch: float):
        """Reage a inclinação excessiva do IMU."""
        logger.warning(f"[MAIN] Inclinação excessiva: roll={roll:.1f}° pitch={pitch:.1f}°")
        if self.kernel:
            self.kernel.send_command("emergency_stop", {})

    def _on_audio_chunk(self, audio_data):
        """Processa chunk de áudio do microfone para lip-sync."""
        if self.expression:
            self.expression.process_audio_for_lip_sync(audio_data)

    def _on_tts_start(self, text: str):
        """Quando TTS começa a falar, ativar expressão de fala."""
        from Springbonnie_system.expression.facial_controller import EmotionPreset
        if self.expression:
            self.expression.start_lip_sync()
        logger.debug(f"[TTS] Falando: {text[:40]}...")

    def _on_tts_end(self, text: str):
        """Quando TTS termina, voltar à expressão neutra."""
        from Springbonnie_system.expression.facial_controller import EmotionPreset
        if self.expression:
            self.expression.stop_lip_sync()
            self.expression.set_emotion(EmotionPreset.NEUTRAL, duration=0.5)

    def _on_phoneme(self, phoneme_data):
        """Callback de fonema para lip-sync preciso."""
        if self.expression:
            jaw_angle = phoneme_data.mouth_openness * 40  # 0-40 graus
            self.expression.open_jaw(jaw_angle)

    def _on_ai_response(self, response):
        """Quando IA gera resposta, falar e mudar expressão."""
        from Springbonnie_system.tts.tts_engine import TTSVoice
        from Springbonnie_system.expression.facial_controller import EmotionPreset

        logger.info(f"[AI] Resposta: {response.text[:60]}...")

        # Mudar expressão baseada na emoção detectada
        if self.expression:
            try:
                emotion = EmotionPreset(response.expression)
                self.expression.set_emotion(emotion, duration=0.4)
            except ValueError:
                pass

        # Falar
        if self.tts:
            try:
                voice = TTSVoice(response.tts_voice)
            except ValueError:
                voice = TTSVoice.ROBOT_MALE
            self.tts.speak(response.text, voice=voice)

        # Broadcast
        if self.ws_server:
            self.ws_server.broadcast("CHAT", {
                "text": response.text,
                "emotion": response.emotion,
                "expression": response.expression
            })

    def _register_show_callbacks(self):
        """Registra callbacks para eventos de show."""
        from Springbonnie_system.audio.show_orchestrator import EventType
        from Springbonnie_system.expression.facial_controller import EmotionPreset

        def on_jaw(params, duration):
            if self.expression:
                self.expression.open_jaw(params.get("angle", 0))

        def on_emotion(params, duration):
            if self.expression:
                try:
                    preset = EmotionPreset(params.get("emotion", "neutral"))
                    self.expression.set_emotion(preset, duration=duration/1000)
                except ValueError:
                    pass

        def on_blink(params, duration):
            if self.expression:
                self.expression.set_eyelids(0)
                time.sleep(0.12)
                self.expression.set_eyelids(100)

        def on_wink(params, duration):
            if self.expression:
                side = params.get("side", "right")
                self.expression.do_wink(side, duration=duration/1000)

        def on_eyes(params, duration):
            if self.expression:
                self.expression.look_at(params.get("x", 0), params.get("y", 0))

        def on_ears(params, duration):
            if self.expression:
                self.expression.set_ears(params.get("angle", 0))

        def on_talking_start(params, duration):
            if self.expression:
                self.expression.start_lip_sync()

        def on_talking_stop(params, duration):
            if self.expression:
                self.expression.stop_lip_sync()

        self.show.register_event_callback(EventType.JAW,           on_jaw)
        self.show.register_event_callback(EventType.EMOTION,       on_emotion)
        self.show.register_event_callback(EventType.BLINK,         on_blink)
        self.show.register_event_callback(EventType.WINK,          on_wink)
        self.show.register_event_callback(EventType.EYES,          on_eyes)
        self.show.register_event_callback(EventType.EARS,          on_ears)
        self.show.register_event_callback(EventType.TALKING_START, on_talking_start)
        self.show.register_event_callback(EventType.TALKING_STOP,  on_talking_stop)

    def _load_default_shows(self):
        """Carrega shows padrão disponíveis."""
        shows_dir = "Springbonnie_system/audio/shows"
        if not os.path.exists(shows_dir):
            return

        # Run Rabbit Run (show original)
        rrr_audio    = os.path.join(shows_dir, "Run,_Rabbit,_Run_-_Alan_Foster_-_Mack_Triplets.mp3")
        rrr_timeline = os.path.join(shows_dir, "run_rabbit_run_timeline.json")
        if os.path.exists(rrr_audio):
            self.show.load_show(rrr_audio, rrr_timeline if os.path.exists(rrr_timeline) else None)
            logger.info("  ✓ Show: Run Rabbit Run")

    def _get_full_status(self) -> dict:
        status = {"timestamp": time.time(), "system": "CyberFun v3.0"}

        if self.kernel:     status["kernel"]     = self.kernel.get_status()
        if self.expression: status["expression"] = self.expression.get_status()
        if self.sensors:    status["sensors"]    = self.sensors.get_status()
        if self.tts:        status["tts"]        = self.tts.get_status()
        if self.ai:         status["ai"]         = self.ai.get_status()
        if self.sequences:  status["sequences"]  = self.sequences.get_status()

        return status

    def shutdown(self):
        """Desliga o sistema de forma segura."""
        logger.info("[MAIN] Iniciando shutdown...")
        self.running = False

        from Springbonnie_system.sequences.animation_sequences import SequenceType
        if self.sequences:
            self.sequences.play(SequenceType.SHUTDOWN, blocking=True)

        if self.tts:
            self.tts.speak_now("Desligando. Até logo!")
            time.sleep(2.0)
            self.tts.stop()

        if self.ai:          self.ai.stop()
        if self.expression:  self.expression.stop_expression_loop()
        if self.ws_server:   self.ws_server.stop()
        if self.sensors:     self.sensors.microphone.stop()
        if self.hal:         self.hal.disconnect()
        if self.kernel:      self.kernel.shutdown()

        logger.info("[MAIN] Sistema desligado com segurança.")


# ==================== ENTRY POINT ====================

def parse_args():
    parser = argparse.ArgumentParser(description="CyberFun Animatronic System v3.0")
    parser.add_argument("--port",         default="/dev/ttyACM0", help="Porta serial do Arduino")
    parser.add_argument("--ws-port",      type=int, default=8765,  help="Porta do servidor WebSocket")
    parser.add_argument("--no-hardware",  action="store_true",     help="Modo simulado (sem Arduino)")
    parser.add_argument("--no-camera",    action="store_true",     help="Desabilitar câmera/visão")
    parser.add_argument("--no-ai",        action="store_true",     help="Desabilitar IA")
    parser.add_argument("--no-network",   action="store_true",     help="Desabilitar WebSocket")
    parser.add_argument("--no-mic",       action="store_true",     help="Desabilitar microfone")
    parser.add_argument("--debug",        action="store_true",     help="Logging debug")
    return parser.parse_args()


def main():
    print(BANNER)
    args = parse_args()
    setup_logging(args.debug)

    system = CyberFunSystem(args)

    # Handler de sinais
    def signal_handler(sig, frame):
        logger.info(f"\n[MAIN] Sinal {sig} recebido - desligando...")
        system.running = False

    signal.signal(signal.SIGINT,  signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Inicializar
    if not system.initialize():
        logger.critical("[MAIN] Falha na inicialização. Abortando.")
        sys.exit(1)

    # Executar loop principal
    system.run()


if __name__ == "__main__":
    main()

