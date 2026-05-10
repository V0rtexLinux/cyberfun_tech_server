"""
================================================================================
  CYBER FUN ENDOSKELETON v3.1.0 - Sistema Principal Fredbear
  Sistema refatorado usando core module compartilhado
================================================================================
"""

import sys
import os
import time
import signal
import logging
import argparse

# Adicionar root ao path para importar core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import HardwareController, FacialExpressionController, EmotionPreset, AnimatronicKernel
from core.config import load_config
from core.ai import AIChatBrain, PersonalityMode
from core.vision import FaceTracker
from core.locomotion import AdvancedLocomotion, NavigationState


def setup_logging(level: str = "INFO"):
    """Configura logging"""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def main():
    parser = argparse.ArgumentParser(description="Fredbear v3.1.0")
    parser.add_argument("--config", default="config/fredbear.yaml", help="Arquivo de configuração")
    parser.add_argument("--no-hardware", action="store_true", help="Modo simulação")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()
    
    # Setup
    config = load_config(args.config)
    setup_logging("DEBUG" if args.debug else config.log_level)
    logger = logging.getLogger("Fredbear.Main")
    
    logger.info("=" * 60)
    logger.info("  FREDBEAR v3.1.0 - Inicializando...")
    logger.info("=" * 60)
    
    try:
        # 1. HAL
        logger.info("[INIT] Hardware Abstraction Layer...")
        hal = HardwareController(
            serial_port="/dev/ttyACM0" if not args.no_hardware else None,
            baudrate=115200,
        )
        
        if not args.no_hardware:
            try:
                hal.connect()
                logger.info("  ✓ Hardware conectado")
            except Exception as e:
                logger.warning(f"  ⚠ Hardware offline: {e}")
        
        # 2. Expression
        logger.info("[INIT] Sistema de Expressão Facial...")
        expression = FacialExpressionController()
        expression.set_pwm_callback(hal.set_servo_pulse)
        expression.start_expression_loop()
        logger.info("  ✓ Expressões ativas")
        
        # 3. Kernel/FSM
        logger.info("[INIT] Kernel FSM...")
        kernel = AnimatronicKernel()
        kernel.initialize()
        logger.info("  ✓ Kernel ativo")
        
        # 4. AI
        logger.info("[INIT] Cérebro de IA...")
        brain = AIChatBrain(openai_key=os.environ.get("OPENAI_API_KEY"))
        
        def on_ai_response(response):
            expression.set_emotion(response.expression)
            # TTS seria aqui
            logger.info(f"[AI] {response.text[:50]}...")
        
        brain.on_response = on_ai_response
        brain.start()
        logger.info(f"  ✓ IA: backend={brain._active_backend}")
        
        # 5. Vision (se habilitado)
        if config.vision.enabled:
            logger.info("[INIT] Sistema de Visão...")
            tracker = FaceTracker(
                camera_index=config.vision.camera_index,
                resolution=config.vision.resolution,
                tracking_distance=config.vision.max_tracking_distance,
            )
            tracker.on_gaze_direction = lambda x, y: expression.look_at(x, y)
            tracker.start()
            logger.info("  ✓ Visão ativa")
        else:
            tracker = None
            logger.info("[INIT] Visão desabilitada")
        
        # 6. Locomotion (se habilitado)
        if config.locomotion.enabled:
            logger.info("[INIT] Sistema de Locomoção...")
            nav = AdvancedLocomotion(
                wheel_base=config.locomotion.wheel_base,
                max_linear_speed=config.locomotion.max_linear_speed,
                enable_slam=config.locomotion.enable_slam,
                enable_pathfinding=config.locomotion.enable_pathfinding,
            )
            nav.start()
            logger.info("  ✓ Locomoção ativa")
        else:
            nav = None
            logger.info("[INIT] Locomoção desabilitada")
        
        # Boot animation
        logger.info("[INIT] Animação de boot...")
        expression.set_emotion(EmotionPreset.EXCITED)
        time.sleep(0.5)
        expression.set_emotion(EmotionPreset.NEUTRAL)
        
        logger.info("=" * 60)
        logger.info("  ✓ SISTEMA PRONTO!")
        logger.info("=" * 60)
        
        # Loop principal
        running = True
        
        def signal_handler(sig, frame):
            nonlocal running
            running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        
        idle_timer = time.time()
        
        while running:
            try:
                # Heartbeat
                if hal.serial_connected:
                    hal._send_heartbeat()
                
                # Idle behavior
                if time.time() - idle_timer > 30:
                    import random
                    behaviors = [
                        lambda: expression.do_wink("right"),
                        lambda: expression.set_emotion(EmotionPreset.HAPPY, 0.3),
                    ]
                    random.choice(behaviors)()
                    idle_timer = time.time()
                
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                break
        
        # Shutdown
        logger.info("[SHUTDOWN] Desligando...")
        
        if tracker:
            tracker.stop()
        if nav:
            nav.stop()
        expression.stop_expression_loop()
        brain.stop()
        hal.disconnect()
        
        logger.info("[SHUTDOWN] Sistema desligado com segurança")
        
    except Exception as e:
        logger.critical(f"[FATAL] {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
