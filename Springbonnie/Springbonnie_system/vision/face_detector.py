"""
================================================================================
SPRINGBONNIE'S SHOW PIZZARIA - Sistema de Visão Computacional
Módulo: Detecção Facial com TFLite de Baixa Latência
================================================================================
Sistema de sensores ópticos para detecção e rastreamento de rostos em tempo real.
Permite que o animatrônico "olhe" e interaja com as pessoas sem atraso perceptível.
================================================================================
"""

import numpy as np
import threading
import time
import queue
import os
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum
import logging

# Importar dependências reais (obrigatório)
try:
    import tflite_runtime.interpreter as tflite
    TFLITE_AVAILABLE = True
except ImportError:
    try:
        from tensorflow.lite.python.interpreter import Interpreter as tflite
        TFLITE_AVAILABLE = True
    except ImportError:
        raise Exception("TensorFlow Lite é obrigatório para o sistema de visão. Instale tflite-runtime ou tensorflow.")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    raise Exception("OpenCV é obrigatório para o sistema de visão. Instale opencv-python.")


class FaceDetectionState(Enum):
    """Estados do sistema de detecção facial"""
    IDLE = "idle"                      # Sistema inativo
    SCANNING = "scanning"              # Procurando rostos
    TRACKING = "tracking"              # Rastreando rosto detectado
    LOCKED = "locked"                  # Rosto travado para interação
    LOST = "lost"                      # Perdeu rastro
    ERROR = "error"                    # Erro no sistema


@dataclass
class DetectedFace:
    """Estrutura de dados para rosto detectado"""
    face_id: int
    bbox: Tuple[int, int, int, int]    # x, y, width, height
    confidence: float
    landmarks: Optional[np.ndarray]     # Pontos faciais (olhos, nariz, boca)
    timestamp: float
    center: Tuple[int, int]             # Centro do rosto para tracking
    is_stable: bool                     # Rosto estável por X frames


@dataclass
class LEDState:
    """Estado dos LEDs de feedback visual nos olhos"""
    intensity: float = 0.5              # 0.0 a 1.0
    color: Tuple[int, int, int] = (0, 100, 255)  # BGR - Azul padrão Springbonnie
    pattern: str = "static"             # static, pulse, blink, fade
    pulse_rate: float = 1.0             # Hz para padrão pulse


class FaceDetectorTFLite:
    """
    Detector de rostos usando TensorFlow Lite para inferência de baixa latência.
    Otimizado para execução em tempo real no animatrônico.
    """
    
    def __init__(self, model_path: str = "models/face_detection.tflite",
                 confidence_threshold: float = 0.7,
                 iou_threshold: float = 0.5,
                 input_size: Tuple[int, int] = (320, 320)):
        
        self.logger = logging.getLogger("Springbonnie.Vision")
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.input_size = input_size
        
        # Estado interno
        self.state = FaceDetectionState.IDLE
        self.detected_faces: List[DetectedFace] = []
        self.tracked_face: Optional[DetectedFace] = None
        self.face_history: List[DetectedFace] = []  # Para estabilidade
        self.face_counter = 0
        self.frame_count = 0
        self.last_detection_time = 0.0
        self.stability_threshold = 5  # Frames para considerar estável
        
        # LED State
        self.led_state = LEDState()
        
        # Threading para processamento assíncrono
        self.frame_queue = queue.Queue(maxsize=3)
        self.result_queue = queue.Queue(maxsize=3)
        self.processing_thread = None
        self.running = False
        
        # Performance metrics
        self.fps = 0.0
        self.inference_time = 0.0
        self.avg_latency = 0.0
        
        # Inicializar modelo
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self._init_model()
        
        self.logger.info("[SPRINGBONNIE VISION] Sistema de Visão inicializado")
    
    def _init_model(self):
        """Inicializa o modelo TFLite para detecção facial"""
        try:
            # Verificar se arquivo de modelo existe
            if not os.path.exists(self.model_path):
                raise Exception(f"Arquivo de modelo não encontrado: {self.model_path}")
            
            # Carregar interpreter TFLite
            self.interpreter = tflite.Interpreter(model_path=self.model_path)
            self.interpreter.allocate_tensors()
            
            # Obter detalhes de input/output
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            self.logger.info(f"[VISION] Modelo TFLite carregado: {self.model_path}")
            self.logger.info(f"[VISION] Input shape: {self.input_details[0]['shape']}")
            
        except Exception as e:
            self.logger.error(f"[VISION] Erro ao carregar modelo: {e}")
            self.state = FaceDetectionState.ERROR
            raise Exception(f"Falha crítica ao carregar modelo de visão: {e}")
    
    def preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Pré-processa o frame para inferência TFLite.
        Redimensiona, normaliza e converte para formato esperado.
        """
        # Redimensionar para tamanho de input do modelo
        input_frame = cv2.resize(frame, self.input_size)
        
        # Normalizar para float32 (0-1)
        input_frame = input_frame.astype(np.float32) / 255.0
        
        # Adicionar dimensão de batch
        input_frame = np.expand_dims(input_frame, axis=0)
        
        return input_frame
    
    def run_inference(self, preprocessed_input: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Executa inferência no modelo TFLite.
        Retorna: boxes, scores, classes, num_detections
        """
        if self.interpreter is None:
            raise Exception("Modelo TFLite não inicializado. Verifique o arquivo do modelo.")
        
        start_time = time.perf_counter()
        
        # Set input tensor
        self.interpreter.set_tensor(self.input_details[0]['index'], preprocessed_input)
        
        # Invoke inference
        self.interpreter.invoke()
        
        # Get output tensors
        boxes = self.interpreter.get_tensor(self.output_details[0]['index'])
        scores = self.interpreter.get_tensor(self.output_details[1]['index'])
        classes = self.interpreter.get_tensor(self.output_details[2]['index'])
        num_detections = self.interpreter.get_tensor(self.output_details[3]['index'])
        
        self.inference_time = (time.perf_counter() - start_time) * 1000  # ms
        
        return boxes[0], scores[0], classes[0], int(num_detections[0])
    
    def process_detections(self, boxes: np.ndarray, scores: np.ndarray, 
                          classes: np.ndarray, num_detections: int,
                          frame_shape: Tuple[int, int]) -> List[DetectedFace]:
        """
        Processa as detecções brutas e cria objetos DetectedFace.
        Aplica NMS e filtros de confiança.
        """
        faces = []
        height, width = frame_shape[:2]
        
        for i in range(num_detections):
            if scores[i] < self.confidence_threshold:
                continue
            
            # Converter coordenadas normalizadas para pixels
            ymin, xmin, ymax, xmax = boxes[i]
            x = int(xmin * width)
            y = int(ymin * height)
            w = int((xmax - xmin) * width)
            h = int((ymax - ymin) * height)
            
            # Calcular centro
            center_x = x + w // 2
            center_y = y + h // 2
            
            # Criar face detectada
            face = DetectedFace(
                face_id=self._get_face_id(x, y, w, h),
                bbox=(x, y, w, h),
                confidence=float(scores[i]),
                landmarks=None,  # Será preenchido se disponível
                timestamp=time.time(),
                center=(center_x, center_y),
                is_stable=False
            )
            
            faces.append(face)
        
        # Aplicar Non-Maximum Suppression se múltiplas detecções
        if len(faces) > 1:
            faces = self._apply_nms(faces)
        
        return faces
    
    def _get_face_id(self, x: int, y: int, w: int, h: int) -> int:
        """Gera ID único para rosto baseado em posição (para tracking)"""
        # Verificar se rosto similar já foi detectado
        for face in self.face_history:
            fx, fy, fw, fh = face.bbox
            # Distância Euclidiana entre centros
            dist = np.sqrt((x + w/2 - fx - fw/2)**2 + (y + h/2 - fy - fh/2)**2)
            if dist < 50:  # Tolerância de 50 pixels
                return face.face_id
        
        # Novo rosto
        self.face_counter += 1
        return self.face_counter
    
    def _apply_nms(self, faces: List[DetectedFace]) -> List[DetectedFace]:
        """Aplica Non-Maximum Suppression para remover detecções duplicadas"""
        if len(faces) == 0:
            return faces
        
        boxes = np.array([f.bbox for f in faces])
        scores = np.array([f.confidence for f in faces])
        
        # Ordenar por confiança
        indices = np.argsort(scores)[::-1]
        
        keep = []
        while len(indices) > 0:
            current = indices[0]
            keep.append(current)
            
            if len(indices) == 1:
                break
            
            # Calcular IoU com outras boxes
            remaining = indices[1:]
            ious = self._calculate_iou(boxes[current], boxes[remaining])
            
            # Remover boxes com IoU alto
            indices = remaining[ious < self.iou_threshold]
        
        return [faces[i] for i in keep]
    
    def _calculate_iou(self, box1: np.ndarray, boxes: np.ndarray) -> np.ndarray:
        """Calcula Intersection over Union entre uma box e múltiplas boxes"""
        x1 = max(box1[0], boxes[:, 0])
        y1 = max(box1[1], boxes[:, 1])
        x2 = min(box1[0] + box1[2], boxes[:, 0] + boxes[:, 2])
        y2 = min(box1[1] + box1[3], boxes[:, 1] + boxes[:, 3])
        
        intersection = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
        
        area1 = box1[2] * box1[3]
        area_boxes = boxes[:, 2] * boxes[:, 3]
        
        union = area1 + area_boxes - intersection
        
        return intersection / (union + 1e-6)
    
    def check_stability(self, face: DetectedFace) -> bool:
        """Verifica se o rosto está estável (presente por múltiplos frames)"""
        # Adicionar ao histórico
        self.face_history.append(face)
        
        # Manter apenas últimos N frames
        if len(self.face_history) > 30:
            self.face_history.pop(0)
        
        # Contar frames com mesmo face_id
        count = sum(1 for f in self.face_history if f.face_id == face.face_id)
        
        return count >= self.stability_threshold
    
    def update_led_feedback(self):
        """Atualiza LEDs de feedback visual baseado no estado de detecção"""
        if self.state == FaceDetectionState.IDLE:
            self.led_state.intensity = 0.3
            self.led_state.color = (0, 100, 255)  # Azul - standby
            self.led_state.pattern = "static"
            
        elif self.state == FaceDetectionState.SCANNING:
            self.led_state.intensity = 0.5
            self.led_state.color = (0, 200, 255)  # Azul claro - buscando
            self.led_state.pattern = "pulse"
            self.led_state.pulse_rate = 2.0
            
        elif self.state == FaceDetectionState.TRACKING:
            self.led_state.intensity = 0.7
            self.led_state.color = (0, 255, 200)  # Cyan - rastreando
            self.led_state.pattern = "pulse"
            self.led_state.pulse_rate = 1.0
            
        elif self.state == FaceDetectionState.LOCKED:
            self.led_state.intensity = 1.0
            self.led_state.color = (0, 255, 100)  # Verde - travado
            self.led_state.pattern = "static"
            
        elif self.state == FaceDetectionState.LOST:
            self.led_state.intensity = 0.8
            self.led_state.color = (0, 165, 255)  # Laranja - perdido
            self.led_state.pattern = "blink"
            
        elif self.state == FaceDetectionState.ERROR:
            self.led_state.intensity = 1.0
            self.led_state.color = (0, 0, 255)  # Vermelho - erro
            self.led_state.pattern = "blink"
    
    def get_gaze_target(self) -> Optional[Tuple[int, int]]:
        """Retorna posição para onde os olhos devem olhar (centro do rosto travado)"""
        if self.tracked_face is not None:
            return self.tracked_face.center
        return None
    
    def detect_frame(self, frame: np.ndarray) -> List[DetectedFace]:
        """
        Método principal para detecção em um frame.
        Executa pipeline completo de detecção.
        """
        self.frame_count += 1
        
        # Pré-processar
        preprocessed = self.preprocess_frame(frame)
        
        # Inferência
        boxes, scores, classes, num_detections = self.run_inference(preprocessed)
        
        # Processar detecções
        self.detected_faces = self.process_detections(
            boxes, scores, classes, num_detections, frame.shape
        )
        
        # Atualizar estado
        self._update_state()
        
        # Atualizar LEDs
        self.update_led_feedback()
        
        # Atualizar FPS
        self._update_fps()
        
        return self.detected_faces
    
    def _update_state(self):
        """Atualiza estado do sistema de detecção"""
        if len(self.detected_faces) == 0:
            if self.state in [FaceDetectionState.TRACKING, FaceDetectionState.LOCKED]:
                self.state = FaceDetectionState.LOST
                self.tracked_face = None
            else:
                self.state = FaceDetectionState.SCANNING
        else:
            # Selecionar rosto mais confiável
            best_face = max(self.detected_faces, key=lambda f: f.confidence)
            
            # Verificar estabilidade
            best_face.is_stable = self.check_stability(best_face)
            
            if best_face.is_stable:
                self.state = FaceDetectionState.LOCKED
                self.tracked_face = best_face
            else:
                self.state = FaceDetectionState.TRACKING
                self.tracked_face = best_face
    
    def _update_fps(self):
        """Atualiza métrica de FPS"""
        current_time = time.time()
        if self.last_detection_time > 0:
            delta = current_time - self.last_detection_time
            self.avg_latency = (self.avg_latency * 0.9) + (delta * 0.1)
            self.fps = 1.0 / self.avg_latency if self.avg_latency > 0 else 0
        self.last_detection_time = current_time
    
    def start_async_processing(self):
        """Inicia thread de processamento assíncrono"""
        self.running = True
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        self.logger.info("[VISION] Processamento assíncrono iniciado")
    
    def _processing_loop(self):
        """Loop de processamento assíncrono"""
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.1)
                faces = self.detect_frame(frame)
                self.result_queue.put((frame, faces, self.state, self.led_state))
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"[VISION] Erro no processamento: {e}")
    
    def stop_async_processing(self):
        """Para thread de processamento assíncrono"""
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)
        self.logger.info("[VISION] Processamento assíncrono parado")
    
    def get_status(self) -> dict:
        """Retorna status atual do sistema de visão"""
        return {
            "state": self.state.value,
            "fps": round(self.fps, 1),
            "inference_time_ms": round(self.inference_time, 2),
            "detected_faces": len(self.detected_faces),
            "tracked_face_id": self.tracked_face.face_id if self.tracked_face else None,
            "led_state": {
                "intensity": self.led_state.intensity,
                "color_bgr": self.led_state.color,
                "pattern": self.led_state.pattern
            }
        }


class InteractionManager:
    """
    Gerenciador de Interação Automática.
    Diferencia o público de objetos inanimados e inicia rotinas de saudação.
    """
    
    def __init__(self, face_detector: FaceDetectorTFLite):
        self.face_detector = face_detector
        self.logger = logging.getLogger("Springbonnie.Interaction")
        
        # Configurações de interação
        self.greeting_cooldown = 5.0  # Segundos entre saudações
        self.min_interaction_time = 2.0  # Tempo mínimo para iniciar interação
        self.max_interaction_distance = 300  # cm (para câmeras com profundidade)
        
        # Estado de interação
        self.last_greeting_time = 0
        self.current_interaction = None
        self.interaction_history = []
        
        # Callbacks para ações do animatrônico
        self.on_greeting_callback = None
        self.on_wave_callback = None
        self.on_look_at_callback = None
        
    def process_interaction(self) -> Optional[dict]:
        """
        Processa interação baseada no rosto detectado.
        Retorna ação a ser executada ou None.
        """
        current_time = time.time()
        
        if self.face_detector.state != FaceDetectionState.LOCKED:
            return None
        
        tracked_face = self.face_detector.tracked_face
        if tracked_face is None:
            return None
        
        # Verificar cooldown
        if current_time - self.last_greeting_time < self.greeting_cooldown:
            return None
        
        # Calcular tempo de interação
        interaction_time = current_time - tracked_face.timestamp
        
        if interaction_time < self.min_interaction_time:
            # Ainda olhando
            return {
                "action": "look_at",
                "target": tracked_face.center,
                "face_id": tracked_face.face_id
            }
        
        # Iniciar saudação
        self.last_greeting_time = current_time
        self.current_interaction = {
            "face_id": tracked_face.face_id,
            "start_time": current_time,
            "action": "greeting"
        }
        
        return {
            "action": "greeting",
            "target": tracked_face.center,
            "face_id": tracked_face.face_id,
            "confidence": tracked_face.confidence
        }
    
    def set_greeting_callback(self, callback):
        """Define callback para execução de saudação"""
        self.on_greeting_callback = callback
    
    def set_wave_callback(self, callback):
        """Define callback para execução de aceno"""
        self.on_wave_callback = callback
    
    def set_look_at_callback(self, callback):
        """Define callback para olhar em direção"""
        self.on_look_at_callback = callback


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar detector
    detector = FaceDetectorTFLite()
    
    # Criar frame de teste (simulado)
    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Executar detecção
    faces = detector.detect_frame(test_frame)
    
    print(f"\n[SPRINGBONNIE VISION] Status: {detector.get_status()}")
    print(f"[SPRINGBONNIE VISION] Rostos detectados: {len(faces)}")
    
    for face in faces:
        print(f"  - Face ID: {face.face_id}, Conf: {face.confidence:.2f}, Center: {face.center}")