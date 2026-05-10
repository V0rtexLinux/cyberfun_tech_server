"""
================================================================================
SISTEMA DE RASTREAMENTO FACIAL AVANÇADO
================================================================================
Integra detecção facial, tracking e controle de olhos.
================================================================================
"""

import numpy as np
import cv2
import threading
import time
import logging
from typing import Optional, List, Tuple, Dict, Callable
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger("CyberFun.Vision")


@dataclass
class FaceDetection:
    """Detecção de rosto com métricas"""
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    face_id: Optional[int] = None
    age_gender: Optional[Dict] = None
    emotion: Optional[str] = None
    landmarks: Optional[List[Tuple[int, int]]] = None
    last_seen: float = field(default_factory=time.time)


@dataclass
class TrackedFace:
    """Rosto sendo rastreado"""
    face_id: int
    detections: deque = field(default_factory=lambda: deque(maxlen=10))
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    is_active: bool = True
    
    @property
    def smoothed_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """Retorna bbox suavizado por média móvel"""
        if not self.detections:
            return None
        
        bboxes = [d.bbox for d in self.detections]
        x = int(np.mean([b[0] for b in bboxes]))
        y = int(np.mean([b[1] for b in bboxes]))
        w = int(np.mean([b[2] for b in bboxes]))
        h = int(np.mean([b[3] for b in bboxes]))
        
        return (x, y, w, h)
    
    @property
    def center(self) -> Optional[Tuple[int, int]]:
        """Retorna centro do rosto"""
        bbox = self.smoothed_bbox
        if bbox is None:
            return None
        return (bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2)


class FaceTracker:
    """
    Sistema de rastreamento facial com:
    - Detecção usando Haar Cascade ou DNN
    - Tracking de múltiplos rostos
    - Suavização temporal
    - Callbacks para reações
    """
    
    def __init__(
        self,
        camera_index: int = 0,
        resolution: Tuple[int, int] = (640, 480),
        fps: int = 30,
        detection_model: str = "haarcascade",
        cascade_path: Optional[str] = None,
        tracking_distance: int = 100,
        max_lost_frames: int = 30,
    ):
        self.logger = logging.getLogger("CyberFun.FaceTracker")
        
        # Configuração de câmera
        self.camera_index = camera_index
        self.resolution = resolution
        self.fps = fps
        self.capture: Optional[cv2.VideoCapture] = None
        
        # Modelo de detecção
        self.detection_model = detection_model
        self.cascade_path = cascade_path or cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade: Optional[cv2.CascadeClassifier] = None
        self.dnn_net: Optional[cv2.dnn.Net] = None
        
        # Tracking
        self.tracked_faces: Dict[int, TrackedFace] = {}
        self.next_face_id = 0
        self.tracking_distance = tracking_distance
        self.max_lost_frames = max_lost_frames
        
        # Estado
        self.running = False
        self.frame_count = 0
        self.detection_fps = 5  # Detectar a cada N frames
        
        # Threading
        self.tracker_thread: Optional[threading.Thread] = None
        self.frame_lock = threading.Lock()
        self.latest_frame: Optional[np.ndarray] = None
        
        # Callbacks
        self.on_face_detected: Optional[Callable[[TrackedFace], None]] = None
        self.on_face_lost: Optional[Callable[[int], None]] = None
        self.on_gaze_direction: Optional[Callable[[float, float], None]] = None
        
        # Métricas
        self.stats = {
            "frames_processed": 0,
            "faces_detected": 0,
            "avg_detection_time_ms": 0,
        }
        
        self._init_detector()
    
    def _init_detector(self):
        """Inicializa detector de faces"""
        if self.detection_model == "haarcascade":
            try:
                self.face_cascade = cv2.CascadeClassifier(self.cascade_path)
                if self.face_cascade.empty():
                    raise ValueError(f"Não foi possível carregar cascade: {self.cascade_path}")
                self.logger.info(f"[VISION] Haar Cascade carregado: {self.cascade_path}")
            except Exception as e:
                self.logger.error(f"[VISION] Erro ao carregar cascade: {e}")
                self.face_cascade = None
        
        elif self.detection_model == "dnn":
            # Carregar modelo DNN (OpenCV face detection)
            try:
                model_file = "opencv_face_detector_uint8.pb"
                config_file = "opencv_face_detector.pbtxt"
                self.dnn_net = cv2.dnn.readNetFromTensorflow(model_file, config_file)
                self.logger.info("[VISION] DNN detector carregado")
            except Exception as e:
                self.logger.error(f"[VISION] Erro ao carregar DNN: {e}")
                self.dnn_net = None
    
    def start(self) -> bool:
        """Inicia captura e tracking"""
        self.logger.info("[VISION] Iniciando FaceTracker...")
        
        # Abrir câmera
        self.capture = cv2.VideoCapture(self.camera_index)
        if not self.capture.isOpened():
            self.logger.error(f"[VISION] Não foi possível abrir câmera {self.camera_index}")
            return False
        
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.capture.set(cv2.CAP_PROP_FPS, self.fps)
        
        self.running = True
        self.tracker_thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self.tracker_thread.start()
        
        self.logger.info("[VISION] FaceTracker iniciado")
        return True
    
    def stop(self):
        """Para tracking"""
        self.running = False
        
        if self.tracker_thread:
            self.tracker_thread.join(timeout=1.0)
        
        if self.capture:
            self.capture.release()
        
        self.logger.info("[VISION] FaceTracker parado")
    
    def _tracking_loop(self):
        """Loop principal de tracking"""
        while self.running:
            try:
                # Capturar frame
                ret, frame = self.capture.read()
                if not ret:
                    continue
                
                self.frame_count += 1
                
                # Detectar faces a cada N frames
                if self.frame_count % self.detection_fps == 0:
                    detections = self._detect_faces(frame)
                    self._update_tracks(detections)
                
                # Atualizar métricas
                self._update_stats()
                
                # Guardar frame processado
                with self.frame_lock:
                    self.latest_frame = frame.copy()
                
                # Notificar callbacks
                self._notify_callbacks()
                
                time.sleep(1.0 / self.fps)
                
            except Exception as e:
                self.logger.error(f"[VISION] Erro no tracking: {e}")
    
    def _detect_faces(self, frame: np.ndarray) -> List[FaceDetection]:
        """Detecta faces no frame"""
        detections = []
        
        if self.face_cascade is not None:
            # Converter para grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detectar faces
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(50, 50),
            )
            
            for (x, y, w, h) in faces:
                detections.append(FaceDetection(
                    bbox=(x, y, w, h),
                    confidence=0.8,  # Haar não dá confidence
                ))
        
        elif self.dnn_net is not None:
            # Usar DNN (mais preciso mas mais lento)
            h, w = frame.shape[:2]
            blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), [104.0, 177.0, 123.0])
            
            self.dnn_net.setInput(blob)
            detections_raw = self.dnn_net.forward()
            
            for i in range(detections_raw.shape[2]):
                confidence = detections_raw[0, 0, i, 2]
                if confidence > 0.5:
                    box = detections_raw[0, 0, i, 3:7] * np.array([w, h, w, h])
                    x1, y1, x2, y2 = box.astype(int)
                    detections.append(FaceDetection(
                        bbox=(x1, y1, x2-x1, y2-y1),
                        confidence=float(confidence),
                    ))
        
        return detections
    
    def _update_tracks(self, detections: List[FaceDetection]):
        """Atualiza tracks de faces"""
        used_detections = set()
        
        # Tentar associar detecções a tracks existentes
        for face_id, track in list(self.tracked_faces.items()):
            if not track.is_active:
                continue
            
            best_detection = None
            best_distance = float('inf')
            
            track_center = track.center
            if track_center is None:
                continue
            
            for i, detection in enumerate(detections):
                if i in used_detections:
                    continue
                
                det_center = (
                    detection.bbox[0] + detection.bbox[2] // 2,
                    detection.bbox[1] + detection.bbox[3] // 2,
                )
                
                distance = np.sqrt(
                    (track_center[0] - det_center[0]) ** 2 +
                    (track_center[1] - det_center[1]) ** 2
                )
                
                if distance < self.tracking_distance and distance < best_distance:
                    best_distance = distance
                    best_detection = i
            
            if best_detection is not None:
                # Atualizar track
                track.detections.append(detections[best_detection])
                track.last_seen = time.time()
                track.is_active = True
                used_detections.add(best_detection)
            else:
                # Verificar se perdeu track por muito tempo
                lost_frames = (time.time() - track.last_seen) * self.fps
                if lost_frames > self.max_lost_frames:
                    track.is_active = False
                    if self.on_face_lost:
                        self.on_face_lost(face_id)
        
        # Criar novos tracks para detecções não associadas
        for i, detection in enumerate(detections):
            if i not in used_detections:
                new_track = TrackedFace(
                    face_id=self.next_face_id,
                    detections=deque([detection], maxlen=10),
                )
                self.tracked_faces[self.next_face_id] = new_track
                
                if self.on_face_detected:
                    self.on_face_detected(new_track)
                
                self.next_face_id += 1
                self.stats["faces_detected"] += 1
    
    def _notify_callbacks(self):
        """Notifica callbacks de gaze tracking"""
        if not self.on_gaze_direction:
            return
        
        # Usar o rosto mais central/confiável
        best_face = None
        best_score = 0
        
        for track in self.tracked_faces.values():
            if not track.is_active:
                continue
            
            center = track.center
            if center is None:
                continue
            
            # Score baseado em confiança e proximidade do centro
            frame_center_x = self.resolution[0] / 2
            distance_from_center = abs(center[0] - frame_center_x)
            score = 1.0 / (1.0 + distance_from_center / 100)
            
            if score > best_score:
                best_score = score
                best_face = track
        
        if best_face and best_face.center:
            # Converter posição de pixel para ângulo de olho
            # Centro da imagem = (0, 0) em ângulos
            cx, cy = best_face.center
            
            # Mapear para ângulos (-45 a 45 graus)
            eye_x = ((cx / self.resolution[0]) - 0.5) * 90
            eye_y = ((cy / self.resolution[1]) - 0.5) * 60
            
            # Clamp
            eye_x = np.clip(eye_x, -45, 45)
            eye_y = np.clip(eye_y, -30, 30)
            
            self.on_gaze_direction(eye_x, eye_y)
    
    def _update_stats(self):
        """Atualiza estatísticas"""
        self.stats["frames_processed"] = self.frame_count
    
    def get_tracked_faces(self) -> List[TrackedFace]:
        """Retorna faces atualmente rastreadas"""
        return [t for t in self.tracked_faces.values() if t.is_active]
    
    def get_primary_face(self) -> Optional[TrackedFace]:
        """Retorna a face principal (mais confiável/central)"""
        active_faces = self.get_tracked_faces()
        if not active_faces:
            return None
        
        # Retornar o track mais antigo (mais estável)
        return min(active_faces, key=lambda t: t.first_seen)
    
    def get_status(self) -> dict:
        """Retorna status do tracker"""
        return {
            "running": self.running,
            "camera_open": self.capture.isOpened() if self.capture else False,
            "active_tracks": len(self.get_tracked_faces()),
            "total_tracks": len(self.tracked_faces),
            "fps": self.fps,
            "resolution": self.resolution,
            "stats": self.stats.copy(),
        }
