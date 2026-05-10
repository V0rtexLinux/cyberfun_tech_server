"""
================================================================================
Springbonnie'S SHOW PIZZARIA - Sistema de Locomoção e Navegação
Módulo: Posicionamento UWB e Navegação Autônoma
================================================================================
Sistema de navegação usando âncoras UWB (Ultra-Wideband) para localização
precisa em centímetros dentro da pizzaria. Inclui pathfinding e controle
diferencial de motores industriais.
================================================================================
"""

import numpy as np
import threading
import time
import heapq
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Set
from enum import Enum
import logging
import json
import math


class RobotState(Enum):
    """Estados do robô durante navegação"""
    IDLE = "idle"                    # Parado, sem navegação
    NAVIGATING = "navigating"        # Em movimento para destino
    WANDERING = "wandering"          # Modo roaming aleatório
    AT_TARGET = "at_target"          # Chegou ao destino
    OBSTACLE_AVOIDANCE = "avoiding"  # Desviando de obstáculo
    EMERGENCY_STOP = "emergency"     # Parada de emergência
    ERROR = "error"                  # Erro no sistema


class MotorState(Enum):
    """Estados dos motores"""
    STOPPED = "stopped"
    FORWARD = "forward"
    BACKWARD = "backward"
    TURNING_LEFT = "turning_left"
    TURNING_RIGHT = "turning_right"
    ROTATING = "rotating"            # Giro sobre o próprio eixo


@dataclass
class Position:
    """Posição 2D com orientação"""
    x: float          # cm
    y: float          # cm
    theta: float      # radianos (0 = norte, pi/2 = leste)
    timestamp: float = field(default_factory=time.time)
    
    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)
    
    def distance_to(self, other: 'Position') -> float:
        """Calcula distância Euclidiana até outra posição"""
        return np.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
    
    def angle_to(self, other: 'Position') -> float:
        """Calcula ângulo até outra posição"""
        return np.arctan2(other.y - self.y, other.x - self.x)


@dataclass
class UWBBAnchor:
    """Âncora UWB para posicionamento"""
    anchor_id: int
    position: Tuple[float, float]    # Posição conhecida da âncora
    distance: float = 0.0            # Distância medida (cm)
    last_update: float = 0.0


@dataclass
class Waypoint:
    """Ponto de navegação"""
    waypoint_id: int
    position: Position
    name: str = ""
    is_stage: bool = False           # É um local de apresentação
    is_table: bool = False           # É uma mesa de cliente
    radius: float = 30.0             # Raio de chegada (cm)


@dataclass
class PathNode:
    """Nó para pathfinding A*"""
    x: int
    y: int
    g_cost: float = 0                # Custo do início até aqui
    h_cost: float = 0                # Heurística até o destino
    parent: Optional['PathNode'] = None
    
    @property
    def f_cost(self) -> float:
        return self.g_cost + self.h_cost


class UWBPositioningSystem:
    """
    Sistema de posicionamento Ultra-Wideband.
    Usa âncoras de rádio instaladas na pizzaria para localização
    com precisão de centímetros dentro do salão.
    """
    
    def __init__(self, anchors: List[UWBBAnchor] = None):
        self.logger = logging.getLogger("Springbonnie.UWB")
        
        # Âncoras UWB
        self.anchors = anchors if anchors else self._create_default_anchors()
        self.anchor_positions = {a.anchor_id: a.position for a in self.anchors}
        
        # Estado de posicionamento
        self.current_position = Position(0, 0, 0)
        self.position_history: List[Position] = []
        self.max_history = 100
        
        # Kalman Filter para suavização
        self.kalman_state = np.array([0.0, 0.0, 0.0])  # x, y, theta
        self.kalman_covariance = np.eye(3) * 100
        
        # Precisão
        self.accuracy = 5.0  # cm (precisão esperada do UWB)
        self.last_update_time = 0.0
        
        # Threading
        self.running = False
        self.update_thread = None
        self.update_rate = 20  # Hz
        
        self.logger.info(f"[UWB] Sistema inicializado com {len(self.anchors)} âncoras")
    
    def _create_default_anchors(self) -> List[UWBBAnchor]:
        """Cria âncoras padrão para uma pizzaria típica"""
        # Layout padrão: pizzaria 15m x 10m
        return [
            UWBBAnchor(0, (0, 0)),         # Canto noroeste
            UWBBAnchor(1, (1500, 0)),     # Canto nordeste
            UWBBAnchor(2, (1500, 1000)),  # Canto sudeste
            UWBBAnchor(3, (0, 1000)),     # Canto sudoeste
        ]
    
    def set_anchors(self, anchors: List[UWBBAnchor]):
        """Configura novas âncoras UWB"""
        self.anchors = anchors
        self.anchor_positions = {a.anchor_id: a.position for a in self.anchors}
        self.logger.info(f"[UWB] Âncoras atualizadas: {len(self.anchors)} âncoras")
    
    def load_anchors_from_config(self, config_path: str):
        """Carrega configuração de âncoras de arquivo"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            anchors = []
            for anchor_data in config.get('anchors', []):
                anchors.append(UWBBAnchor(
                    anchor_id=anchor_data['id'],
                    position=tuple(anchor_data['position'])
                ))
            
            self.set_anchors(anchors)
            
        except Exception as e:
            self.logger.error(f"[UWB] Erro ao carregar config: {e}")
    
    def trilaterate(self, distances: Dict[int, float]) -> Optional[Position]:
        """
        Calcula posição usando trilateração a partir de distâncias às âncoras.
        Implementação usando mínimos quadrados não-linear.
        """
        if len(distances) < 3:
            self.logger.warning("[UWB] Mínimo 3 âncoras necessárias")
            return None
        
        # Preparar dados
        anchor_points = []
        dist_list = []
        
        for anchor_id, dist in distances.items():
            if anchor_id in self.anchor_positions:
                anchor_points.append(self.anchor_positions[anchor_id])
                dist_list.append(dist)
        
        if len(anchor_points) < 3:
            return None
        
        # Estimativa inicial (centróide)
        anchor_array = np.array(anchor_points)
        estimate = np.mean(anchor_array, axis=0)
        
        # Iteração de mínimos quadrados
        for _ in range(10):  # Máximo de iterações
            jacobian = np.zeros((len(anchor_points), 2))
            residuals = np.zeros(len(anchor_points))
            
            for i, (anchor, dist) in enumerate(zip(anchor_points, dist_list)):
                dx = estimate[0] - anchor[0]
                dy = estimate[1] - anchor[1]
                pred_dist = np.sqrt(dx**2 + dy**2)
                
                if pred_dist > 0:
                    jacobian[i, 0] = dx / pred_dist
                    jacobian[i, 1] = dy / pred_dist
                    residuals[i] = dist - pred_dist
            
            # Atualizar estimativa
            try:
                delta = np.linalg.lstsq(jacobian, residuals, rcond=None)[0]
                estimate = estimate + delta
                
                if np.linalg.norm(delta) < 0.1:  # Convergiu
                    break
            except:
                break
        
        # Calcular orientação (será atualizada pelo compass/giroscópio)
        theta = self.current_position.theta
        
        return Position(estimate[0], estimate[1], theta)
    
    def kalman_update(self, measurement: Position):
        """
        Atualiza filtro de Kalman com nova medição.
        Suaviza o trajectory e reduz ruído.
        """
        # Matriz de transição (motion model simples)
        F = np.eye(3)
        
        # Matriz de observação
        H = np.eye(3)
        
        # Ruído de processo
        Q = np.eye(3) * 0.1
        
        # Ruído de medição (baseado na precisão UWB)
        R = np.eye(3) * self.accuracy**2
        
        # Predict
        predicted_state = F @ self.kalman_state
        predicted_covariance = F @ self.kalman_covariance @ F.T + Q
        
        # Update
        measurement_vec = np.array([measurement.x, measurement.y, measurement.theta])
        y = measurement_vec - H @ predicted_state
        S = H @ predicted_covariance @ H.T + R
        K = predicted_covariance @ H.T @ np.linalg.inv(S)
        
        self.kalman_state = predicted_state + K @ y
        self.kalman_covariance = (np.eye(3) - K @ H) @ predicted_covariance
        
        # Atualizar posição
        self.current_position = Position(
            self.kalman_state[0],
            self.kalman_state[1],
            self.kalman_state[2]
        )
    
    def read_anchor_distances(self) -> Dict[int, float]:
        """
        Lê distâncias das âncoras UWB.
        Em produção, isso leria do hardware UWB via serial/SPI.
        """
        # Simulação: retornar distâncias calculadas
        distances = {}
        
        for anchor in self.anchors:
            # Calcular distância real + ruído simulado
            dx = self.current_position.x - anchor.position[0]
            dy = self.current_position.y - anchor.position[1]
            true_distance = np.sqrt(dx**2 + dy**2)
            
            # Adicionar ruído gaussiano (precisão UWB)
            noise = np.random.normal(0, self.accuracy / 3)
            measured_distance = true_distance + noise
            
            distances[anchor.anchor_id] = measured_distance
            anchor.distance = measured_distance
            anchor.last_update = time.time()
        
        return distances
    
    def update_position(self) -> Position:
        """Atualiza posição atual do robô"""
        distances = self.read_anchor_distances()
        new_position = self.trilaterate(distances)
        
        if new_position:
            self.kalman_update(new_position)
            
            # Adicionar ao histórico
            self.position_history.append(self.current_position)
            if len(self.position_history) > self.max_history:
                self.position_history.pop(0)
            
            self.last_update_time = time.time()
        
        return self.current_position
    
    def get_position(self) -> Position:
        """Retorna posição atual"""
        return self.current_position
    
    def get_velocity(self) -> Tuple[float, float]:
        """Calcula velocidade atual baseada no histórico"""
        if len(self.position_history) < 2:
            return (0.0, 0.0)
        
        prev = self.position_history[-2]
        curr = self.current_position
        
        dt = curr.timestamp - prev.timestamp
        if dt == 0:
            return (0.0, 0.0)
        
        vx = (curr.x - prev.x) / dt  # cm/s
        vy = (curr.y - prev.y) / dt
        
        return (vx, vy)
    
    def start_continuous_update(self):
        """Inicia thread de atualização contínua de posição"""
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        self.logger.info("[UWB] Atualização contínua iniciada")
    
    def _update_loop(self):
        """Loop de atualização de posição"""
        while self.running:
            self.update_position()
            time.sleep(1.0 / self.update_rate)
    
    def stop_continuous_update(self):
        """Para thread de atualização"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=1.0)


class NavigationMap:
    """
    Mapa de navegação da pizzaria com grid de ocupação.
    Usado para pathfinding e detecção de obstáculos.
    """
    
    def __init__(self, width_cm: float = 1500, height_cm: float = 1000,
                 resolution_cm: float = 10):
        self.logger = logging.getLogger("Springbonnie.NavMap")
        
        self.width_cm = width_cm
        self.height_cm = height_cm
        self.resolution = resolution_cm
        
        # Dimensões do grid
        self.grid_width = int(width_cm / resolution_cm)
        self.grid_height = int(height_cm / resolution_cm)
        
        # Grid de ocupação (0 = livre, 1 = ocupado, 0.5 = desconhecido)
        self.occupancy_grid = np.zeros((self.grid_height, self.grid_width))
        
        # Waypoints e zonas
        self.waypoints: Dict[int, Waypoint] = {}
        self.stage_areas: List[Tuple[float, float, float, float]] = []  # (x1, y1, x2, y2)
        self.table_areas: List[Tuple[float, float, float, float]] = []
        self.obstacle_areas: List[Tuple[float, float, float, float]] = []
        
        # Zonas proibidas
        self.restricted_zones: List[Tuple[float, float, float]] = []  # (x, y, radius)
        
        self.logger.info(f"[NAVMAP] Mapa criado: {self.grid_width}x{self.grid_height} células")
    
    def cm_to_grid(self, x_cm: float, y_cm: float) -> Tuple[int, int]:
        """Converte coordenadas em cm para índices do grid"""
        gx = int(np.clip(x_cm / self.resolution, 0, self.grid_width - 1))
        gy = int(np.clip(y_cm / self.resolution, 0, self.grid_height - 1))
        return (gx, gy)
    
    def grid_to_cm(self, gx: int, gy: int) -> Tuple[float, float]:
        """Converte índices do grid para coordenadas em cm"""
        x_cm = gx * self.resolution + self.resolution / 2
        y_cm = gy * self.resolution + self.resolution / 2
        return (x_cm, y_cm)
    
    def is_valid_cell(self, gx: int, gy: int) -> bool:
        """Verifica se célula está dentro do mapa"""
        return 0 <= gx < self.grid_width and 0 <= gy < self.grid_height
    
    def is_cell_free(self, gx: int, gy: int) -> bool:
        """Verifica se célula está livre para navegação"""
        if not self.is_valid_cell(gx, gy):
            return False
        return self.occupancy_grid[gy, gx] < 0.5
    
    def mark_obstacle(self, x_cm: float, y_cm: float, radius_cm: float = 30):
        """Marca área como obstáculo no mapa"""
        gx, gy = self.cm_to_grid(x_cm, y_cm)
        r_cells = int(radius_cm / self.resolution)
        
        for dx in range(-r_cells, r_cells + 1):
            for dy in range(-r_cells, r_cells + 1):
                if dx**2 + dy**2 <= r_cells**2:
                    nx, ny = gx + dx, gy + dy
                    if self.is_valid_cell(nx, ny):
                        self.occupancy_grid[ny, nx] = 1.0
        
        self.obstacle_areas.append((x_cm - radius_cm, y_cm - radius_cm,
                                    x_cm + radius_cm, y_cm + radius_cm))
    
    def mark_free(self, x_cm: float, y_cm: float, radius_cm: float = 30):
        """Marca área como livre no mapa"""
        gx, gy = self.cm_to_grid(x_cm, y_cm)
        r_cells = int(radius_cm / self.resolution)
        
        for dx in range(-r_cells, r_cells + 1):
            for dy in range(-r_cells, r_cells + 1):
                if dx**2 + dy**2 <= r_cells**2:
                    nx, ny = gx + dx, gy + dy
                    if self.is_valid_cell(nx, ny):
                        self.occupancy_grid[ny, nx] = 0.0
    
    def add_waypoint(self, waypoint: Waypoint):
        """Adiciona waypoint ao mapa"""
        self.waypoints[waypoint.waypoint_id] = waypoint
        
        if waypoint.is_stage:
            self.stage_areas.append((
                waypoint.position.x - 50, waypoint.position.y - 50,
                waypoint.position.x + 50, waypoint.position.y + 50
            ))
        
        if waypoint.is_table:
            self.table_areas.append((
                waypoint.position.x - 40, waypoint.position.y - 40,
                waypoint.position.x + 40, waypoint.position.y + 40
            ))
    
    def add_restricted_zone(self, x: float, y: float, radius: float):
        """Adiciona zona restrita (não pode entrar)"""
        self.restricted_zones.append((x, y, radius))
    
    def setup_default_pizzaria(self):
        """Configura mapa padrão para uma pizzaria típica"""
        # Palco principal
        stage = Waypoint(
            waypoint_id=0,
            position=Position(750, 100, 0),
            name="Palco Principal",
            is_stage=True
        )
        self.add_waypoint(stage)
        
        # Mesas dos clientes
        for i in range(6):
            angle = (i / 6) * 2 * np.pi
            x = 750 + 400 * np.cos(angle)
            y = 500 + 300 * np.sin(angle)
            
            table = Waypoint(
                waypoint_id=i + 1,
                position=Position(x, y, 0),
                name=f"Mesa {i + 1}",
                is_table=True
            )
            self.add_waypoint(table)
        
        # Marcar área do palco como obstáculo para navegação
        # (Springbonnie não anda no palco, fica no modo performance)
        self.mark_obstacle(750, 50, 60)
        
        # Área de Behind-the-scenes (zona restrita)
        self.add_restricted_zone(100, 900, 100)
        
        self.logger.info("[NAVMAP] Layout padrão da pizzaria configurado")


class PathFinder:
    """
    Sistema de pathfinding usando A* para navegação.
    Calcula rotas ótimas entre pontos do salão.
    """
    
    def __init__(self, nav_map: NavigationMap):
        self.nav_map = nav_map
        self.logger = logging.getLogger("Springbonnie.PathFinder")
        
        # Cache de caminhos
        self.path_cache: Dict[Tuple, List[Position]] = {}
        self.cache_max_size = 50
        
        # Configuração
        self.smoothing_iterations = 3
        self.robot_radius_cm = 40  # Raio do robô para colisão
    
    def heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Heurística de distância para A* (Euclidiana)"""
        return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
    
    def get_neighbors(self, node: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Retorna vizinhos válidos de um nó (8-conectividade)"""
        neighbors = []
        directions = [
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1),          (0, 1),
            (1, -1),  (1, 0), (1, 1)
        ]
        
        for dx, dy in directions:
            nx, ny = node[0] + dx, node[1] + dy
            
            # Verificar colisão
            if not self.nav_map.is_cell_free(nx, ny):
                continue
            
            # Verificar se robô cabe (expandir verificação)
            r_cells = int(self.robot_radius_cm / self.nav_map.resolution)
            can_move = True
            
            for cx in range(-r_cells, r_cells + 1):
                for cy in range(-r_cells, r_cells + 1):
                    if cx**2 + cy**2 <= r_cells**2:
                        check_x, check_y = nx + cx, ny + cy
                        if not self.nav_map.is_cell_free(check_x, check_y):
                            can_move = False
                            break
                if not can_move:
                    break
            
            if can_move:
                neighbors.append((nx, ny))
        
        return neighbors
    
    def find_path(self, start: Position, goal: Position) -> List[Position]:
        """
        Encontra caminho entre start e goal usando A*.
        Retorna lista de posições a seguir.
        """
        # Converter para grid
        start_grid = self.nav_map.cm_to_grid(start.x, start.y)
        goal_grid = self.nav_map.cm_to_grid(goal.x, goal.y)
        
        # Verificar cache
        cache_key = (start_grid, goal_grid)
        if cache_key in self.path_cache:
            return self.path_cache[cache_key]
        
        # A* algorithm
        open_set = []
        closed_set: Set[Tuple[int, int]] = set()
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        
        g_score: Dict[Tuple[int, int], float] = {start_grid: 0}
        f_score: Dict[Tuple[int, int], float] = {start_grid: self.heuristic(start_grid, goal_grid)}
        
        heapq.heappush(open_set, (f_score[start_grid], start_grid))
        
        while open_set:
            current = heapq.heappop(open_set)[1]
            
            if current == goal_grid:
                # Reconstruir caminho
                path = self._reconstruct_path(came_from, current)
                smoothed_path = self._smooth_path(path)
                
                # Atualizar cache
                self._update_cache(cache_key, smoothed_path)
                
                return smoothed_path
            
            closed_set.add(current)
            
            for neighbor in self.get_neighbors(current):
                if neighbor in closed_set:
                    continue
                
                # Custo do movimento (diagonal custa mais)
                is_diagonal = abs(neighbor[0] - current[0]) + abs(neighbor[1] - current[1]) == 2
                move_cost = 1.414 if is_diagonal else 1.0
                
                tentative_g = g_score[current] + move_cost
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self.heuristic(neighbor, goal_grid)
                    
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        # Nenhum caminho encontrado
        self.logger.warning(f"[PATHFINDER] Nenhum caminho encontrado de {start_grid} para {goal_grid}")
        return []
    
    def _reconstruct_path(self, came_from: Dict, current: Tuple[int, int]) -> List[Position]:
        """Reconstrói caminho a partir do dicionário de predecessores"""
        path = []
        
        while current in came_from:
            x_cm, y_cm = self.nav_map.grid_to_cm(current[0], current[1])
            path.append(Position(x_cm, y_cm, 0))
            current = came_from[current]
        
        path.reverse()
        return path
    
    def _smooth_path(self, path: List[Position]) -> List[Position]:
        """Suaviza caminho usando interpolação"""
        if len(path) < 3:
            return path
        
        smoothed = path.copy()
        
        for _ in range(self.smoothing_iterations):
            new_smoothed = [smoothed[0]]  # Manter início
            
            for i in range(1, len(smoothed) - 1):
                prev_pos = smoothed[i - 1]
                curr_pos = smoothed[i]
                next_pos = smoothed[i + 1]
                
                # Média ponderada
                new_x = 0.25 * prev_pos.x + 0.5 * curr_pos.x + 0.25 * next_pos.x
                new_y = 0.25 * prev_pos.y + 0.5 * curr_pos.y + 0.25 * next_pos.y
                
                # Verificar se posição suavizada é válida
                gx, gy = self.nav_map.cm_to_grid(new_x, new_y)
                if self.nav_map.is_cell_free(gx, gy):
                    new_smoothed.append(Position(new_x, new_y, 0))
                else:
                    new_smoothed.append(curr_pos)
            
            new_smoothed.append(smoothed[-1])  # Manter fim
            smoothed = new_smoothed
        
        # Calcular orientações
        for i in range(len(smoothed) - 1):
            angle = smoothed[i].angle_to(smoothed[i + 1])
            smoothed[i].theta = angle
        
        return smoothed
    
    def _update_cache(self, key: Tuple, path: List[Position]):
        """Atualiza cache de caminhos"""
        if len(self.path_cache) >= self.cache_max_size:
            # Remover entrada mais antiga
            oldest_key = next(iter(self.path_cache))
            del self.path_cache[oldest_key]
        
        self.path_cache[key] = path


class DifferentialDriveController:
    """
    Controlador de tração diferencial para motores industriais.
    Permite giros sobre o próprio eixo e movimentos suaves.
    Simula o caminhar pesado de um robô de grande porte.
    """
    
    def __init__(self, wheelbase_cm: float = 60, wheel_radius_cm: float = 15):
        self.logger = logging.getLogger("Springbonnie.DiffDrive")
        
        # Parâmetros físicos
        self.wheelbase = wheelbase_cm      # Distância entre rodas
        self.wheel_radius = wheel_radius_cm
        
        # Limites de velocidade (para movimentos suaves)
        self.max_linear_speed = 30.0       # cm/s (lento para animatrônico)
        self.max_angular_speed = 0.5       # rad/s
        self.max_acceleration = 10.0       # cm/s²
        
        # Estado atual
        self.left_wheel_speed = 0.0        # cm/s
        self.right_wheel_speed = 0.0       # cm/s
        self.linear_velocity = 0.0         # cm/s
        self.angular_velocity = 0.0        # rad/s
        
        # Controle PID
        self.linear_kp = 2.0
        self.linear_ki = 0.1
        self.linear_kd = 0.5
        self.angular_kp = 3.0
        self.angular_ki = 0.1
        self.angular_kd = 0.8
        
        self.linear_integral = 0.0
        self.linear_prev_error = 0.0
        self.angular_integral = 0.0
        self.angular_prev_error = 0.0
        
        # Estado do motor
        self.motor_state = MotorState.STOPPED
        self.is_emergency_stop = False
        
        # PWM para motores (simulado)
        self.left_pwm = 0
        self.right_pwm = 0
        
        self.logger.info("[DIFFDRIVE] Controlador diferencial inicializado")
    
    def compute_wheel_speeds(self, linear_vel: float, angular_vel: float) -> Tuple[float, float]:
        """
        Calcula velocidades das rodas a partir de velocidades linear e angular.
        Cinemática de robô diferencial.
        """
        # v = (v_right + v_left) / 2
        # w = (v_right - v_left) / L
        
        v_right = linear_vel + angular_vel * self.wheelbase / 2
        v_left = linear_vel - angular_vel * self.wheelbase / 2
        
        return (v_left, v_right)
    
    def apply_speed_limits(self, left_speed: float, right_speed: float) -> Tuple[float, float]:
        """Aplica limites de velocidade e aceleração"""
        # Limitar velocidade máxima
        max_wheel_speed = self.max_linear_speed
        
        left_speed = np.clip(left_speed, -max_wheel_speed, max_wheel_speed)
        right_speed = np.clip(right_speed, -max_wheel_speed, max_wheel_speed)
        
        # Limitar aceleração (suavização)
        max_delta = self.max_acceleration * 0.05  # dt = 50ms
        
        left_delta = left_speed - self.left_wheel_speed
        right_delta = right_speed - self.right_wheel_speed
        
        if abs(left_delta) > max_delta:
            left_speed = self.left_wheel_speed + np.sign(left_delta) * max_delta
        if abs(right_delta) > max_delta:
            right_speed = self.right_wheel_speed + np.sign(right_delta) * max_delta
        
        return (left_speed, right_speed)
    
    def compute_motor_pwm(self, left_speed: float, right_speed: float) -> Tuple[int, int]:
        """Converte velocidades para PWM dos motores"""
        # PWM proporcional à velocidade (simplificado)
        # Em produção, usaria feedback de encoders
        
        max_pwm = 255
        
        left_pwm = int(np.clip(left_speed / self.max_linear_speed * max_pwm, -max_pwm, max_pwm))
        right_pwm = int(np.clip(right_speed / self.max_linear_speed * max_pwm, -max_pwm, max_pwm))
        
        return (left_pwm, right_pwm)
    
    def update_motor_state(self):
        """Atualiza estado do motor baseado nas velocidades"""
        if self.is_emergency_stop:
            self.motor_state = MotorState.STOPPED
            return
        
        if abs(self.linear_velocity) < 0.1 and abs(self.angular_velocity) < 0.01:
            self.motor_state = MotorState.STOPPED
        elif abs(self.angular_velocity) > 0.1:
            if self.angular_velocity > 0:
                self.motor_state = MotorState.TURNING_LEFT
            else:
                self.motor_state = MotorState.TURNING_RIGHT
        elif abs(self.angular_velocity) > 0.3:
            self.motor_state = MotorState.ROTATING
        elif self.linear_velocity > 0:
            self.motor_state = MotorState.FORWARD
        else:
            self.motor_state = MotorState.BACKWARD
    
    def move_to_target(self, current_pos: Position, target_pos: Position,
                       current_vel: Tuple[float, float] = (0, 0)) -> Tuple[float, float]:
        """
        Calcula comandos de velocidade para navegar até um alvo.
        Usa controle PID para suavizar o movimento.
        """
        if self.is_emergency_stop:
            return (0.0, 0.0)
        
        # Calcular erro de posição
        distance = current_pos.distance_to(target_pos)
        angle_to_target = current_pos.angle_to(target_pos)
        
        # Erro angular (normalizado para [-pi, pi])
        angle_error = angle_to_target - current_pos.theta
        angle_error = np.arctan2(np.sin(angle_error), np.cos(angle_error))
        
        # PID linear
        self.linear_integral += distance * 0.05
        linear_derivative = (distance - self.linear_prev_error) / 0.05
        
        linear_vel = (self.linear_kp * distance + 
                     self.linear_ki * self.linear_integral +
                     self.linear_kd * linear_derivative)
        
        self.linear_prev_error = distance
        
        # PID angular
        self.angular_integral += angle_error * 0.05
        angular_derivative = (angle_error - self.angular_prev_error) / 0.05
        
        angular_vel = (self.angular_kp * angle_error +
                      self.angular_ki * self.angular_integral +
                      self.angular_kd * angular_derivative)
        
        self.angular_prev_error = angle_error
        
        # Reduzir velocidade linear se precisar girar muito
        if abs(angle_error) > 0.5:  # ~30 graus
            linear_vel *= 0.3
        
        # Aplicar limites
        linear_vel = np.clip(linear_vel, -self.max_linear_speed, self.max_linear_speed)
        angular_vel = np.clip(angular_vel, -self.max_angular_speed, self.max_angular_speed)
        
        # Calcular velocidades das rodas
        left_speed, right_speed = self.compute_wheel_speeds(linear_vel, angular_vel)
        
        # Aplicar suavização
        left_speed, right_speed = self.apply_speed_limits(left_speed, right_speed)
        
        # Atualizar estado
        self.left_wheel_speed = left_speed
        self.right_wheel_speed = right_speed
        self.linear_velocity = linear_vel
        self.angular_velocity = angular_vel
        self.left_pwm, self.right_pwm = self.compute_motor_pwm(left_speed, right_speed)
        
        self.update_motor_state()
        
        return (linear_vel, angular_vel)
    
    def rotate_in_place(self, target_angle: float, current_angle: float) -> Tuple[float, float]:
        """Gira o robô sobre o próprio eixo até o ângulo alvo"""
        angle_error = target_angle - current_angle
        angle_error = np.arctan2(np.sin(angle_error), np.cos(angle_error))
        
        # Se erro pequeno, parar
        if abs(angle_error) < 0.05:  # ~3 graus
            return (0.0, 0.0)
        
        # Velocidade angular proporcional ao erro
        angular_vel = np.clip(angle_error * 2, -self.max_angular_speed, self.max_angular_speed)
        
        # Rotação no lugar: rodas em direções opostas
        left_speed, right_speed = self.compute_wheel_speeds(0, angular_vel)
        
        self.left_wheel_speed = left_speed
        self.right_wheel_speed = right_speed
        self.angular_velocity = angular_vel
        self.linear_velocity = 0
        
        self.motor_state = MotorState.ROTATING
        
        return (0.0, angular_vel)
    
    def stop(self):
        """Para o robô suavemente"""
        # Reduzir velocidade gradualmente
        self.left_wheel_speed *= 0.8
        self.right_wheel_speed *= 0.8
        self.linear_velocity *= 0.8
        self.angular_velocity *= 0.8
        
        if abs(self.linear_velocity) < 0.1:
            self.left_wheel_speed = 0
            self.right_wheel_speed = 0
            self.linear_velocity = 0
            self.angular_velocity = 0
            self.motor_state = MotorState.STOPPED
    
    def emergency_stop(self):
        """Parada de emergência imediata"""
        self.is_emergency_stop = True
        self.left_wheel_speed = 0
        self.right_wheel_speed = 0
        self.linear_velocity = 0
        self.angular_velocity = 0
        self.left_pwm = 0
        self.right_pwm = 0
        self.motor_state = MotorState.STOPPED
        self.logger.warning("[DIFFDRIVE] EMERGÊNCIA - Motores parados!")
    
    def release_emergency_stop(self):
        """Libera parada de emergência"""
        self.is_emergency_stop = False
        self.logger.info("[DIFFDRIVE] Parada de emergência liberada")
    
    def get_status(self) -> dict:
        """Retorna status do controlador"""
        return {
            "motor_state": self.motor_state.value,
            "linear_velocity_cm_s": round(self.linear_velocity, 2),
            "angular_velocity_rad_s": round(self.angular_velocity, 3),
            "left_wheel_speed": round(self.left_wheel_speed, 2),
            "right_wheel_speed": round(self.right_wheel_speed, 2),
            "left_pwm": self.left_pwm,
            "right_pwm": self.right_pwm,
            "emergency_stop": self.is_emergency_stop
        }


class LocomotionSystem:
    """
    Sistema principal de locomoção que integra UWB, navegação e controle de motores.
    """
    
    def __init__(self, config: dict = None):
        self.logger = logging.getLogger("Springbonnie.Locomotion")
        
        # Configuração
        self.config = config or {}
        
        # Componentes
        self.uwb = UWBPositioningSystem()
        self.nav_map = NavigationMap()
        self.pathfinder = PathFinder(self.nav_map)
        self.motor_controller = DifferentialDriveController()
        
        # Estado de navegação
        self.state = RobotState.IDLE
        self.current_path: List[Position] = []
        self.current_waypoint_index = 0
        self.target_waypoint: Optional[Waypoint] = None
        
        # Wandering mode
        self.wandering_enabled = False
        self.wandering_interval = 30.0  # Segundos entre movimentos
        self.last_wander_time = 0.0
        
        # Threading
        self.running = False
        self.navigation_thread = None
        
        # Configurar mapa padrão
        self.nav_map.setup_default_pizzaria()
        
        self.logger.info("[LOCOMOTION] Sistema de locomoção inicializado")
    
    def navigate_to(self, target: Position) -> bool:
        """Inicia navegação até posição alvo"""
        current = self.uwb.get_position()
        
        # Calcular caminho
        path = self.pathfinder.find_path(current, target)
        
        if not path:
            self.logger.error(f"[LOCOMOTION] Falha ao calcular caminho para {target}")
            return False
        
        self.current_path = path
        self.current_waypoint_index = 0
        self.state = RobotState.NAVIGATING
        
        self.logger.info(f"[LOCOMOTION] Navegando para {target}, {len(path)} waypoints")
        return True
    
    def navigate_to_waypoint(self, waypoint_id: int) -> bool:
        """Navega até um waypoint específico"""
        if waypoint_id not in self.nav_map.waypoints:
            return False
        
        waypoint = self.nav_map.waypoints[waypoint_id]
        self.target_waypoint = waypoint
        
        return self.navigate_to(waypoint.position)
    
    def update_navigation(self):
        """Atualiza navegação - chamado periodicamente"""
        if self.state == RobotState.IDLE:
            return
        
        if self.state == RobotState.EMERGENCY_STOP or self.state == RobotState.ERROR:
            return
        
        # Obter posição atual
        current = self.uwb.get_position()
        
        if self.state == RobotState.NAVIGATING:
            # Verificar se chegou ao waypoint atual
            if self.current_waypoint_index < len(self.current_path):
                target = self.current_path[self.current_waypoint_index]
                
                distance = current.distance_to(target)
                
                if distance < 20:  # Chegou no waypoint (20cm)
                    self.current_waypoint_index += 1
                    
                    if self.current_waypoint_index >= len(self.current_path):
                        # Chegou ao destino final
                        self.state = RobotState.AT_TARGET
                        self.motor_controller.stop()
                        self.logger.info("[LOCOMOTION] Destino alcançado!")
                        return
                
                # Mover em direção ao target
                self.motor_controller.move_to_target(current, target)
                
            else:
                self.state = RobotState.AT_TARGET
        
        elif self.state == RobotState.WANDERING:
            self._wandering_update()
        
        elif self.state == RobotState.OBSTACLE_AVOIDANCE:
            self._obstacle_avoidance_update()
    
    def _wandering_update(self):
        """Atualiza modo de roaming aleatório"""
        current_time = time.time()
        
        if current_time - self.last_wander_time < self.wandering_interval:
            return
        
        # Escolher mesa aleatória para visitar
        table_ids = [wp_id for wp_id, wp in self.nav_map.waypoints.items() if wp.is_table]
        
        if not table_ids:
            return
        
        import random
        target_id = random.choice(table_ids)
        
        self.navigate_to_waypoint(target_id)
        self.last_wander_time = current_time
    
    def _obstacle_avoidance_update(self):
        """Atualiza desvio de obstáculo"""
        # Implementação simplificada - girar e tentar novo caminho
        current = self.uwb.get_position()
        
        if self.target_waypoint:
            # Recalcular caminho
            new_path = self.pathfinder.find_path(current, self.target_waypoint.position)
            
            if new_path:
                self.current_path = new_path
                self.current_waypoint_index = 0
                self.state = RobotState.NAVIGATING
    
    def start_wandering(self):
        """Inicia modo de roaming"""
        self.wandering_enabled = True
        self.state = RobotState.WANDERING
        self.last_wander_time = time.time()
        self.logger.info("[LOCOMOTION] Modo roaming ativado")
    
    def stop_wandering(self):
        """Para modo de roaming"""
        self.wandering_enabled = False
        if self.state == RobotState.WANDERING:
            self.state = RobotState.IDLE
            self.motor_controller.stop()
        self.logger.info("[LOCOMOTION] Modo roaming desativado")
    
    def return_to_stage(self):
        """Retorna ao palco principal"""
        stage_id = 0  # ID do palco principal
        
        if stage_id in self.nav_map.waypoints:
            self.navigate_to_waypoint(stage_id)
            self.logger.info("[LOCOMOTION] Retornando ao palco")
    
    def emergency_stop(self):
        """Aciona parada de emergência"""
        self.state = RobotState.EMERGENCY_STOP
        self.motor_controller.emergency_stop()
        self.logger.warning("[LOCOMOTION] PARADA DE EMERGÊNCIA!")
    
    def release_emergency(self):
        """Libera parada de emergência"""
        self.motor_controller.release_emergency_stop()
        self.state = RobotState.IDLE
        self.logger.info("[LOCOMOTION] Emergência liberada")
    
    def start_navigation_loop(self):
        """Inicia loop de navegação em thread separada"""
        self.running = True
        self.uwb.start_continuous_update()
        self.navigation_thread = threading.Thread(target=self._navigation_loop, daemon=True)
        self.navigation_thread.start()
    
    def _navigation_loop(self):
        """Loop principal de navegação"""
        while self.running:
            self.update_navigation()
            time.sleep(0.05)  # 20 Hz
    
    def stop_all(self):
        """Para todos os sistemas de navegação"""
        self.running = False
        self.uwb.stop_continuous_update()
        self.motor_controller.stop()
        
        if self.navigation_thread:
            self.navigation_thread.join(timeout=1.0)
        
        self.logger.info("[LOCOMOTION] Sistema parado")
    
    def get_status(self) -> dict:
        """Retorna status completo do sistema de locomoção"""
        return {
            "state": self.state.value,
            "position": {
                "x_cm": round(self.uwb.current_position.x, 1),
                "y_cm": round(self.uwb.current_position.y, 1),
                "theta_rad": round(self.uwb.current_position.theta, 3)
            },
            "velocity": self.motor_controller.get_status(),
            "navigation": {
                "path_length": len(self.current_path),
                "current_waypoint": self.current_waypoint_index,
                "target_waypoint": self.target_waypoint.name if self.target_waypoint else None
            },
            "wandering": self.wandering_enabled
        }


# Módulo de Teste
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Criar sistema
    locomotion = LocomotionSystem()
    
    # Testar navegação
    print("\n[Springbonnie LOCOMOTION] Status inicial:")
    print(json.dumps(locomotion.get_status(), indent=2))
    
    # Navegar para mesa 1
    locomotion.navigate_to_waypoint(1)
    
    # Simular algumas atualizações
    for i in range(10):
        locomotion.update_navigation()
        status = locomotion.get_status()
        print(f"\n[UPDATE {i+1}] Posição: ({status['position']['x_cm']}, {status['position']['y_cm']})")
        print(f"[UPDATE {i+1}] Motores: {status['velocity']['motor_state']}")
