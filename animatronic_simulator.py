#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  ANIMATRONIC SIMULATOR - Simulação Dual Fredbear & Springbonnie
  Versão 1.0
================================================================================
Script de simulação que executa ambos os animatrônicos simultaneamente
usando seus códigos originais sem modificações.

Funcionamento:
  - Adiciona os diretórios Fredbear/ e Springbonnie/ ao Python path
  - Simula o hardware (serial, GPIO) para permitir execução sem Arduino
  - Executa ambos os sistemas em threads paralelas
  - Fornece interface unificada de controle

Uso:
  python animatronic_simulator.py [--debug] [--no-ai]
================================================================================
"""

import sys
import os

# Fix para codificação UTF-8 no Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import time
import signal
import logging
import threading
import argparse
import json
import random
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

# ==============================================================================
# CONFIGURAÇÃO DE PATHS - Adiciona ambos os sistemas ao Python path
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FREDBEAR_DIR = os.path.join(SCRIPT_DIR, "Fredbear")
SPRINGBONNIE_DIR = os.path.join(SCRIPT_DIR, "Springbonnie")

# Adiciona ao início do path para prioridade
sys.path.insert(0, SPRINGBONNIE_DIR)
sys.path.insert(0, FREDBEAR_DIR)
sys.path.insert(0, SCRIPT_DIR)

# ==============================================================================
# SHIM DE MÓDULO - Resolve problema de case-sensitive (springbonnie_system vs Springbonnie_system)
# ==============================================================================
# Pre-popula sys.modules para redirecionar springbonnie_system -> Springbonnie_system
try:
    import Springbonnie_system
    sys.modules['springbonnie_system'] = Springbonnie_system
    
    # Também precisamos mapear todos os submódulos
    import Springbonnie_system.hal.hardware_controller
    import Springbonnie_system.expression.facial_controller
    import Springbonnie_system.sensors.sensor_hub
    import Springbonnie_system.sequences.animation_sequences
    import Springbonnie_system.tts.tts_engine
    import Springbonnie_system.ai.ai_brain
    import Springbonnie_system.audio.show_orchestrator
    import Springbonnie_system.kernel.fsm_kernel
    import Springbonnie_system.network.ws_server
    
    sys.modules['springbonnie_system.hal'] = Springbonnie_system.hal
    sys.modules['springbonnie_system.hal.hardware_controller'] = Springbonnie_system.hal.hardware_controller
    sys.modules['springbonnie_system.expression'] = Springbonnie_system.expression
    sys.modules['springbonnie_system.expression.facial_controller'] = Springbonnie_system.expression.facial_controller
    sys.modules['springbonnie_system.sensors'] = Springbonnie_system.sensors
    sys.modules['springbonnie_system.sensors.sensor_hub'] = Springbonnie_system.sensors.sensor_hub
    sys.modules['springbonnie_system.sequences'] = Springbonnie_system.sequences
    sys.modules['springbonnie_system.sequences.animation_sequences'] = Springbonnie_system.sequences.animation_sequences
    sys.modules['springbonnie_system.tts'] = Springbonnie_system.tts
    sys.modules['springbonnie_system.tts.tts_engine'] = Springbonnie_system.tts.tts_engine
    sys.modules['springbonnie_system.ai'] = Springbonnie_system.ai
    sys.modules['springbonnie_system.ai.ai_brain'] = Springbonnie_system.ai.ai_brain
    sys.modules['springbonnie_system.audio'] = Springbonnie_system.audio
    sys.modules['springbonnie_system.audio.show_orchestrator'] = Springbonnie_system.audio.show_orchestrator
    sys.modules['springbonnie_system.kernel'] = Springbonnie_system.kernel
    sys.modules['springbonnie_system.kernel.fsm_kernel'] = Springbonnie_system.kernel.fsm_kernel
    sys.modules['springbonnie_system.network'] = Springbonnie_system.network
    sys.modules['springbonnie_system.network.ws_server'] = Springbonnie_system.network.ws_server
    
    pass  # Mapeamento realizado com sucesso
except Exception as e:
    print(f"[WARNING] Erro ao mapear modulos Springbonnie: {e}")

# ==============================================================================
# MOCK DE HARDWARE - Simula hardware serial e GPIO para execução sem Arduino
# ==============================================================================
class MockSerial:
    """Simula conexão serial para testes sem hardware físico."""
    
    def __init__(self, port=None, baudrate=115200, timeout=0.1, **kwargs):
        self.port = port or "/dev/ttySIM0"
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self._in_buffer = b""
        self._out_buffer = b""
        logging.getLogger("MockSerial").info(f"[MOCK] Serial aberta em {self.port} @ {baudrate}")
    
    def write(self, data: bytes):
        self._out_buffer += data
        # Simula resposta automática de sucesso
        if len(data) > 3:
            # Protocolo: START(0xAA) + CMD + ... + END(0x55)
            if data[0] == 0xAA and data[-1] == 0x55:
                # Resposta de sucesso: START + CMD + 0x00 + END
                response = bytes([0xAA, data[1], 0x00, 0x55])
                self._in_buffer += response
    
    def read(self, size: int = 1) -> bytes:
        if self._in_buffer:
            result = self._in_buffer[:size]
            self._in_buffer = self._in_buffer[size:]
            return result
        return b""
    
    def read_all(self) -> bytes:
        result = self._in_buffer
        self._in_buffer = b""
        return result
    
    @property
    def in_waiting(self) -> int:
        return len(self._in_buffer)
    
    def flush(self):
        pass
    
    def close(self):
        self.is_open = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


# Aplica mocks antes de importar os módulos dos animatrônicos
try:
    import serial.tools.list_ports
except ImportError:
    pass

import serial
serial.Serial = MockSerial

# Mock do serial.tools.list_ports
class MockListPorts:
    @staticmethod
    def comports():
        return [type('MockPort', (), {'device': '/dev/ttySIM0'})()]

serial.tools = type('tools', (), {})()
serial.tools.list_ports = MockListPorts()

# ==============================================================================
# CONFIGURAÇÃO DE LOGGING
# ==============================================================================
def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    
    # Cria diretório de logs
    os.makedirs("simulator_logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"simulator_logs/simulation_{timestamp}.log")
    ]
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-8s] %(name)-25s: %(message)s",
        handlers=handlers
    )


# ==============================================================================
# BANNERS
# ==============================================================================
DUAL_BANNER = """
================================================================================
         ANIMATRONIC DUAL SIMULATOR
================================================================================
    Simulacao simultanea de Fredbear e Springbonnie
    Hardware simulado | IA ativa | Expressoes faciais
================================================================================
"""

# ==============================================================================
# SIMULADOR DE ANIMATRÔNICO INDIVIDUAL
# ==============================================================================
@dataclass
class SimulatedAnimatronic:
    """Container para um animatrônico simulado."""
    name: str
    system: Any
    thread: Optional[threading.Thread] = None
    running: bool = False
    status: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.status is None:
            self.status = {}


class AnimatronicSimulator:
    """
    Simulador mestre que gerencia ambos os animatrônicos.
    Mantém os códigos originais intactos, apenas orquestrando a execução.
    """
    
    def __init__(self, args):
        self.args = args
        self.logger = logging.getLogger("AnimatronicSimulator")
        
        self.fredbear: Optional[SimulatedAnimatronic] = None
        self.springbonnie: Optional[SimulatedAnimatronic] = None
        
        self.running = False
        self.simulation_thread = None
        
        # Estatísticas
        self.start_time = None
        self.interaction_count = 0
        
    def _create_mock_args(self, name: str, ws_port: int):
        """Cria argumentos simulados para cada animatrônico."""
        class MockArgs:
            pass
        
        args = MockArgs()
        args.port = "/dev/ttySIM0"
        args.ws_port = ws_port
        args.no_hardware = True  # SEMPRE simulado
        args.no_camera = True
        args.no_ai = self.args.no_ai
        args.no_network = True  # WebSocket desabilitado na simulacao
        args.no_mic = True
        args.debug = self.args.debug
        
        return args
    
    def initialize_fredbear(self) -> bool:
        """Inicializa o sistema Fredbear."""
        self.logger.info("=" * 60)
        self.logger.info("  [INIT] Inicializando Fredbear...")
        self.logger.info("=" * 60)
        
        try:
            # Importa o sistema Fredbear
            from Fredbear_system.main import CyberFunSystem, setup_logging as fb_setup_logging
            
            # Cria args simulados
            fb_args = self._create_mock_args("Fredbear", 8765)
            
            # Cria sistema (sem logging duplicado)
            fb_system = CyberFunSystem(fb_args)
            
            # Inicializa
            if not fb_system.initialize():
                self.logger.error("[FREDBEAR] Falha na inicializacao!")
                return False
            
            self.fredbear = SimulatedAnimatronic(
                name="Fredbear",
                system=fb_system
            )
            
            self.logger.info("[FREDBEAR] [OK] Inicializado com sucesso!")
            return True
            
        except Exception as e:
            self.logger.error(f"[FREDBEAR] Erro: {e}", exc_info=True)
            return False
    
    def initialize_springbonnie(self) -> bool:
        """Inicializa o sistema Springbonnie."""
        self.logger.info("=" * 60)
        self.logger.info("  [INIT] Inicializando Springbonnie...")
        self.logger.info("=" * 60)
        
        try:
            # Importa o sistema Springbonnie
            from springbonnie_system.main import CyberFunSystem, setup_logging as sb_setup_logging
            
            # Cria args simulados
            sb_args = self._create_mock_args("Springbonnie", 8766)
            
            # Cria sistema
            sb_system = CyberFunSystem(sb_args)
            
            # Inicializa
            if not sb_system.initialize():
                self.logger.error("[SPRINGBONNIE] Falha na inicializacao!")
                return False
            
            self.springbonnie = SimulatedAnimatronic(
                name="Springbonnie",
                system=sb_system
            )
            
            self.logger.info("[SPRINGBONNIE] [OK] Inicializado com sucesso!")
            return True
            
        except Exception as e:
            self.logger.error(f"[SPRINGBONNIE] Erro: {e}", exc_info=True)
            return False
    
    def initialize(self) -> bool:
        """Inicializa ambos os animatrônicos."""
        self.logger.info(DUAL_BANNER)
        
        success = True
        
        # Inicializa Fredbear
        if not self.initialize_fredbear():
            success = False
        
        time.sleep(0.5)  # Pausa entre inicializações
        
        # Inicializa Springbonnie
        if not self.initialize_springbonnie():
            success = False
        
        if success:
            self.logger.info("=" * 60)
            self.logger.info("  [OK] AMBOS OS ANIMATRÔNICOS INICIALIZADOS!")
            self.logger.info("=" * 60)
            self.start_time = time.time()
        else:
            self.logger.error("=" * 60)
            self.logger.error("  FALHA NA INICIALIZACAO")
            self.logger.error("=" * 60)
        
        return success
    
    def _run_animatronic_loop(self, animatronic: SimulatedAnimatronic):
        """Executa loop de um animatrônico em thread separada."""
        self.logger.info(f"[{animatronic.name.upper()}] Loop iniciado")
        
        animatronic.running = True
        
        try:
            while animatronic.running and self.running:
                # Atualiza status
                animatronic.status = animatronic.system._get_full_status()
                
                # Executa ciclo do sistema
                try:
                    # Heartbeat
                    if animatronic.system.hal and animatronic.system.hal.serial_connected:
                        animatronic.system.hal._send_heartbeat()
                    
                    # Idle behavior
                    if animatronic.system.sequences and not animatronic.system.sequences.is_playing:
                        # Verifica timer idle
                        pass  # Simplificado para simulação
                    
                except Exception as e:
                    self.logger.error(f"[{animatronic.name.upper()}] Erro no loop: {e}")
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            pass
        finally:
            animatronic.running = False
            self.logger.info(f"[{animatronic.name.upper()}] Loop encerrado")
    
    def _simulation_control_loop(self):
        """Loop de controle da simulação - interações entre animatrônicos."""
        self.logger.info("[SIMULATOR] Loop de controle iniciado")
        
        while self.running:
            try:
                # Simula interações aleatórias entre os animatrônicos
                if random.random() < 0.1:  # 10% de chance por ciclo
                    self._do_random_interaction()
                
                # Atualiza display de status a cada 5 segundos
                if int(time.time()) % 5 == 0:
                    self._print_status()
                
                time.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"[SIMULATOR] Erro no controle: {e}")
                time.sleep(1.0)
    
    def _do_random_interaction(self):
        """Executa interação aleatória entre os animatrônicos."""
        if not self.fredbear or not self.springbonnie:
            return
        
        interactions = [
            self._interaction_greeting,
            self._interaction_look_at_each_other,
            self._interaction_synchronized_emotion,
            self._interaction_alternate_blink,
        ]
        
        interaction = random.choice(interactions)
        interaction()
        self.interaction_count += 1
    
    def _interaction_greeting(self):
        """Ambos se cumprimentam."""
        self.logger.info("[INTERACTION] Fredbear e Springbonnie se cumprimentam!")
        
        try:
            from Fredbear_system.expression.facial_controller import EmotionPreset as FBEmotion
            from springbonnie_system.expression.facial_controller import EmotionPreset as SBEmotion
            
            self.fredbear.system.expression.set_emotion(FBEmotion.EXCITED, duration=0.5)
            self.springbonnie.system.expression.set_emotion(SBEmotion.EXCITED, duration=0.5)
            
            # Simula fala
            if self.fredbear.system.tts:
                self.fredbear.system.tts.speak("Olá Springbonnie!")
            if self.springbonnie.system.tts:
                self.springbonnie.system.tts.speak("Oi Fredbear!")
                
        except Exception as e:
            self.logger.debug(f"[INTERACTION] Erro no greeting: {e}")
    
    def _interaction_look_at_each_other(self):
        """Olham um para o outro."""
        self.logger.info("[INTERACTION] Olhando um para o outro")
        
        try:
            # Fredbear olha para direita (Springbonnie está à direita)
            self.fredbear.system.expression.look_at(30, 0)
            # Springbonnie olha para esquerda (Fredbear está à esquerda)
            self.springbonnie.system.expression.look_at(-30, 0)
            
            time.sleep(2.0)
            
            # Voltam ao centro
            self.fredbear.system.expression.look_at(0, 0)
            self.springbonnie.system.expression.look_at(0, 0)
            
        except Exception as e:
            self.logger.debug(f"[INTERACTION] Erro no look: {e}")
    
    def _interaction_synchronized_emotion(self):
        """Emoção sincronizada."""
        emotions = ["HAPPY", "SURPRISED", "LAUGHING"]
        emotion_name = random.choice(emotions)
        
        self.logger.info(f"[INTERACTION] Emocao sincronizada: {emotion_name}")
        
        try:
            from Fredbear_system.expression.facial_controller import EmotionPreset as FBEmotion
            from springbonnie_system.expression.facial_controller import EmotionPreset as SBEmotion
            
            fb_emotion = FBEmotion[emotion_name]
            sb_emotion = SBEmotion[emotion_name]
            
            self.fredbear.system.expression.set_emotion(fb_emotion, duration=0.5)
            self.springbonnie.system.expression.set_emotion(sb_emotion, duration=0.5)
            
        except Exception as e:
            self.logger.debug(f"[INTERACTION] Erro na emoção: {e}")
    
    def _interaction_alternate_blink(self):
        """Piscam alternadamente."""
        self.logger.info("[INTERACTION] Piscando alternadamente")
        
        try:
            self.fredbear.system.expression.do_wink("right", duration=0.3)
            time.sleep(0.3)
            self.springbonnie.system.expression.do_wink("left", duration=0.3)
            
        except Exception as e:
            self.logger.debug(f"[INTERACTION] Erro no wink: {e}")
    
    def _print_status(self):
        """Imprime status dos animatrônicos."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        print("\n" + "=" * 70)
        print(f"  STATUS DA SIMULACAO | Tempo: {elapsed:.0f}s | Interacoes: {self.interaction_count}")
        print("=" * 70)
        
        for animatronic in [self.fredbear, self.springbonnie]:
            if animatronic and animatronic.status:
                expr = animatronic.status.get("expression", {})
                current = expr.get("current_expression", {})
                
                print(f"\n  [{animatronic.name}]:")
                print(f"     Expressao: jaw={current.get('jaw_angle', 0):.1f} | "
                      f"eyes=({current.get('eye_x', 0):.1f}, {current.get('eye_y', 0):.1f})")
                print(f"     Palpebras: L={current.get('left_eyelid', 0):.0f}% | "
                      f"R={current.get('right_eyelid', 0):.0f}%")
                print(f"     Orelhas: L={current.get('left_ear', 0):.1f} | "
                      f"R={current.get('right_ear', 0):.1f}")
        
        print("\n" + "=" * 70)
    
    def run(self):
        """Executa a simulação."""
        self.running = True
        
        # Inicia threads dos animatrônicos
        if self.fredbear:
            self.fredbear.thread = threading.Thread(
                target=self._run_animatronic_loop,
                args=(self.fredbear,),
                daemon=True
            )
            self.fredbear.thread.start()
        
        if self.springbonnie:
            self.springbonnie.thread = threading.Thread(
                target=self._run_animatronic_loop,
                args=(self.springbonnie,),
                daemon=True
            )
            self.springbonnie.thread.start()
        
        # Inicia thread de controle
        self.simulation_thread = threading.Thread(
            target=self._simulation_control_loop,
            daemon=True
        )
        self.simulation_thread.start()
        
        self.logger.info("[SIMULATOR] Simulação em execução. Pressione Ctrl+C para parar.")
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.logger.info("[SIMULATOR] Interrupção recebida...")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Desliga a simulação de forma segura."""
        self.logger.info("=" * 60)
        self.logger.info("  [SHUTDOWN] Encerrando simulação...")
        self.logger.info("=" * 60)
        
        self.running = False
        
        # Para threads dos animatrônicos
        for animatronic in [self.fredbear, self.springbonnie]:
            if animatronic:
                animatronic.running = False
                if animatronic.thread:
                    animatronic.thread.join(timeout=2.0)
        
        # Shutdown dos sistemas
        if self.fredbear and self.fredbear.system:
            try:
                self.fredbear.system.shutdown()
            except Exception as e:
                self.logger.debug(f"[FREDBEAR] Erro no shutdown: {e}")
        
        if self.springbonnie and self.springbonnie.system:
            try:
                self.springbonnie.system.shutdown()
            except Exception as e:
                self.logger.debug(f"[SPRINGBONNIE] Erro no shutdown: {e}")
        
        self.logger.info("[SIMULATOR] Simulação encerrada com segurança.")
        
        # Estatísticas finais
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.logger.info(f"[SIMULATOR] Tempo total: {elapsed:.1f}s")
            self.logger.info(f"[SIMULATOR] Interações: {self.interaction_count}")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def parse_args():
    parser = argparse.ArgumentParser(description="Animatronic Dual Simulator v1.0")
    parser.add_argument("--debug", action="store_true", help="Logging debug")
    parser.add_argument("--no-ai", action="store_true", help="Desabilitar IA")
    parser.add_argument("--duration", type=int, default=0, 
                        help="Duração da simulação em segundos (0 = infinito)")
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.debug)
    
    simulator = AnimatronicSimulator(args)
    
    # Handler de sinais
    def signal_handler(sig, frame):
        logging.info(f"[MAIN] Sinal {sig} recebido - desligando...")
        simulator.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Inicializa
    if not simulator.initialize():
        logging.critical("[MAIN] Falha na inicializacao. Abortando.")
        sys.exit(1)
    
    # Executa
    simulator.run()


if __name__ == "__main__":
    main()
