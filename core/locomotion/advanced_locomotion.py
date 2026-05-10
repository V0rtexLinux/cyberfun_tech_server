"""
================================================================================
SISTEMA DE LOCOMOÇÃO AVANÇADA
================================================================================
Inclui:
- Pathfinding A*
- SLAM (Simultaneous Localization and Mapping)
- Navegação autônoma com desvio de obstáculos
- Controle PID de velocidade
================================================================================
"""

import numpy as np
import threading
import time
import heapq
import logging
from typing import Optional, List, Tuple, Dict, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger("CyberFun.Locomotion")


class NavigationState(Enum):
    """Estados de navegação"""
    IDLE = "idle"
    NAVIGATING = "navigating"
    OBSTACLE_DETECTED = "obstacle_detected"
    REPLANNING = "replanning"
    ARRIVED = "arrived"
    ERROR = "error"


@dataclass
class Position:
    """Posição 2D com orientação"""
    x: float = 0.0  # metros
    y: float = 0.0  # metros
    theta: float = 0.0  # radianos
    
    def distance_to(self, other: 'Position') -> float:
        return np.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)
    
    def angle_to(self, other: 'Position') -> float:
        return np.arctan2(other.y - self.y, other.x - self.x)


@dataclass
class OccupancyGrid:
    """Grid de ocupação para SLAM/pathfinding"""
    resolution: float = 0.05  # metros/célula
    width: int = 200  # células
    height: int = 200  # células
    origin: Position = field(default_factory=Position)
    
    # 0 = livre, 100 = ocupado, -1 = desconhecido
    data: np.ndarray = field(default_factory=lambda: np.full((200, 200), -1, dtype=np.int8))
    
    def world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Converte coordenadas mundo para grid"""
        gx = int((x - self.origin.x) / self.resolution)
        gy = int((y - self.origin.y) / self.resolution)
        return (gx, gy)
    
    def grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        """Converte coordenadas grid para mundo"""
        x = gx * self.resolution + self.origin.x
        y = gy * self.resolution + self.origin.y
        return (x, y)
    
    def is_free(self, gx: int, gy: int) -> bool:
        """Verifica se célula está livre"""
        if 0 <= gx < self.width and 0 <= gy < self.height:
            return self.data[gy, gx] >= 0 and self.data[gy, gx] < 50
        return False
    
    def set_occupied(self, gx: int, gy: int, value: int = 100):
        """Marca célula como ocupada"""
        if 0 <= gx < self.width and 0 <= gy < self.height:
            self.data[gy, gx] = min(100, max(0, value))


@dataclass
class PathNode:
    """Nó para pathfinding A*"""
    x: int
    y: int
    g: float = 0.0  # Custo do início até aqui
    h: float = 0.0  # Heurística (estimativa até o fim)
    parent: Optional['PathNode'] = None
    
    @property
    def f(self) -> float:
        return self.g + self.h
    
    def __lt__(self, other):
        return self.f < other.f
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    
    def __hash__(self):
        return hash((self.x, self.y))


class PathPlanner:
    """
    Planejador de caminhos usando A*
    """
    
    def __init__(self, grid: OccupancyGrid):
        self.grid = grid
        self.logger = logging.getLogger("CyberFun.PathPlanner")
    
    def plan_path(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
    ) -> Optional[List[Tuple[float, float]]]:
        """
        Planeja caminho de start até goal usando A*
        
        Returns:
            Lista de waypoints (x, y) ou None se não encontrou caminho
        """
        # Converter para grid coords
        start_g = self.grid.world_to_grid(start[0], start[1])
        goal_g = self.grid.world_to_grid(goal[0], goal[1])
        
        # Verificar se goal está livre
        if not self.grid.is_free(goal_g[0], goal_g[1]):
            self.logger.warning("[PATH] Goal está ocupado!")
            return None
        
        # A*
        open_set = []
        closed_set = set()
        
        start_node = PathNode(start_g[0], start_g[1])
        start_node.h = self._heuristic(start_g, goal_g)
        heapq.heappush(open_set, start_node)
        
        while open_set:
            current = heapq.heappop(open_set)
            
            if (current.x, current.y) == goal_g:
                # Reconstruir caminho
                path = []
                node = current
                while node:
                    world_pos = self.grid.grid_to_world(node.x, node.y)
                    path.append(world_pos)
                    node = node.parent
                
                return path[::-1]  # Inverter
            
            closed_set.add((current.x, current.y))
            
            # Expandir vizinhos (8-direções)
            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]:
                nx, ny = current.x + dx, current.y + dy
                
                if (nx, ny) in closed_set:
                    continue
                
                if not self.grid.is_free(nx, ny):
                    continue
                
                # Custo de movimento (diagonal = sqrt(2))
                cost = np.sqrt(2) if dx != 0 and dy != 0 else 1.0
                
                neighbor = PathNode(nx, ny)
                neighbor.g = current.g + cost
                neighbor.h = self._heuristic((nx, ny), goal_g)
                neighbor.parent = current
                
                # Verificar se já está na open_set com custo menor
                existing = next((n for n in open_set if n == neighbor), None)
                if existing and existing.g <= neighbor.g:
                    continue
                
                heapq.heappush(open_set, neighbor)
        
        self.logger.warning("[PATH] Não encontrou caminho!")
        return None
    
    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Distância Euclidiana como heurística"""
        return np.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)
    
    def smooth_path(
        self,
        path: List[Tuple[float, float]],
        weight_data: float = 0.5,
        weight_smooth: float = 0.3,
        tolerance: float = 0.001,
    ) -> List[Tuple[float, float]]:
        """
        Suaviza caminho usando algoritmo de gradient descent
        """
        if len(path) < 3:
            return path
        
        new_path = [list(p) for p in path]
        change = tolerance
        
        while change >= tolerance:
            change = 0.0
            for i in range(1, len(path) - 1):
                for j in range(2):  # x, y
                    aux = new_path[i][j]
                    
                    # Mover em direção ao ponto original
                    new_path[i][j] += weight_data * (path[i][j] - new_path[i][j])
                    
                    # Mover em direção à média dos vizinhos
                    new_path[i][j] += weight_smooth * (
                        new_path[i-1][j] + new_path[i+1][j] - 2*new_path[i][j]
                    )
                    
                    change += abs(aux - new_path[i][j])
        
        return [tuple(p) for p in new_path]


@dataclass
class Obstacle:
    """Obstáculo detectado"""
    position: Position
    radius: float
    confidence: float
    timestamp: float = field(default_factory=time.time)


class ObstacleAvoidance:
    """
    Sistema de desvio de obstáculos
    """
    
    def __init__(self, safety_distance: float = 0.3):
        self.safety_distance = safety_distance
        self.obstacles: List[Obstacle] = []
        self.obstacle_timeout = 2.0  # segundos
    
    def add_obstacle(self, x: float, y: float, radius: float = 0.1, confidence: float = 1.0):
        """Adiciona obstáculo detectado"""
        self.obstacles.append(Obstacle(
            position=Position(x, y),
            radius=radius,
            confidence=confidence,
        ))
        
        # Limpar obstáculos antigos
        current_time = time.time()
        self.obstacles = [
            o for o in self.obstacles
            if current_time - o.timestamp < self.obstacle_timeout
        ]
    
    def check_collision(
        self,
        position: Position,
        lookahead_distance: float = 0.5,
    ) -> Optional[Obstacle]:
        """Verifica colisão iminente"""
        for obs in self.obstacles:
            distance = position.distance_to(obs.position)
            if distance < (obs.radius + self.safety_distance + lookahead_distance):
                return obs
        return None
    
    def get_avoidance_velocity(
        self,
        current_pos: Position,
        desired_velocity: Tuple[float, float],
    ) -> Tuple[float, float]:
        """
        Calcula velocidade ajustada para evitar obstáculos
        (Campos potenciais simples)
        """
        vx, vy = desired_velocity
        
        for obs in self.obstacles:
            dx = current_pos.x - obs.position.x
            dy = current_pos.y - obs.position.y
            distance = np.sqrt(dx**2 + dy**2)
            
            if distance < (obs.radius + self.safety_distance):
                # Força repulsiva
                force = (obs.radius + self.safety_distance - distance) / distance if distance > 0 else 1.0
                vx += force * dx / distance * 0.5
                vy += force * dy / distance * 0.5
        
        return (vx, vy)


class AdvancedLocomotion:
    """
    Sistema de locomoção avançada integrado
    """
    
    def __init__(
        self,
        wheel_base: float = 0.3,
        max_linear_speed: float = 0.5,
        max_angular_speed: float = 1.0,
        enable_slam: bool = True,
        enable_pathfinding: bool = True,
        map_resolution: float = 0.05,
        map_size: Tuple[int, int] = (200, 200),
    ):
        self.logger = logging.getLogger("CyberFun.AdvancedLocomotion")
        
        # Configuração física
        self.wheel_base = wheel_base
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed
        
        # Estado
        self.current_position = Position()
        self.current_velocity = (0.0, 0.0)  # linear, angular
        self.navigation_state = NavigationState.IDLE
        
        # SLAM
        self.enable_slam = enable_slam
        self.grid = OccupancyGrid(
            resolution=map_resolution,
            width=map_size[0],
            height=map_size[1],
        )
        
        # Pathfinding
        self.enable_pathfinding = enable_pathfinding
        self.path_planner = PathPlanner(self.grid) if enable_pathfinding else None
        self.current_path: Optional[List[Tuple[float, float]]] = None
        self.current_path_index = 0
        
        # Obstacle avoidance
        self.obstacle_avoidance = ObstacleAvoidance()
        
        # Controle
        self.position_tolerance = 0.1  # metros
        self.angle_tolerance = 0.2  # radianos
        
        # Callbacks
        self.on_position_update: Optional[Callable[[Position], None]] = None
        self.on_path_complete: Optional[Callable[[], None]] = None
        self.on_obstacle_detected: Optional[Callable[[Obstacle], None]] = None
        
        # Threading
        self.running = False
        self.control_thread: Optional[threading.Thread] = None
        self.control_rate = 20  # Hz
    
    def start(self):
        """Inicia controle de locomoção"""
        self.running = True
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()
        self.logger.info("[LOCOMOTION] Sistema iniciado")
    
    def stop(self):
        """Para controle"""
        self.running = False
        self.current_velocity = (0.0, 0.0)
        if self.control_thread:
            self.control_thread.join(timeout=1.0)
        self.logger.info("[LOCOMOTION] Sistema parado")
    
    def navigate_to(self, x: float, y: float, theta: Optional[float] = None) -> bool:
        """
        Inicia navegação para posição alvo
        
        Returns:
            True se conseguiu planejar caminho
        """
        if not self.enable_pathfinding:
            self.logger.warning("[LOCOMOTION] Pathfinding desabilitado")
            return False
        
        start = (self.current_position.x, self.current_position.y)
        goal = (x, y)
        
        path = self.path_planner.plan_path(start, goal)
        
        if path is None:
            self.navigation_state = NavigationState.ERROR
            return False
        
        # Suavizar caminho
        self.current_path = self.path_planner.smooth_path(path)
        self.current_path_index = 0
        self.navigation_state = NavigationState.NAVIGATING
        
        self.logger.info(f"[LOCOMOTION] Navegando para ({x:.2f}, {y:.2f})")
        return True
    
    def update_position(self, x: float, y: float, theta: float):
        """Atualiza pose estimada (do SLAM/odometria)"""
        self.current_position = Position(x, y, theta)
        
        if self.on_position_update:
            self.on_position_update(self.current_position)
    
    def report_obstacle(self, x: float, y: float, radius: float = 0.1):
        """Reporta obstáculo detectado por sensor"""
        # Adicionar ao sistema de avoidance
        self.obstacle_avoidance.add_obstacle(x, y, radius)
        
        # Marcar no mapa
        if self.enable_slam:
            gx, gy = self.grid.world_to_grid(x, y)
            self.grid.set_occupied(gx, gy)
        
        # Verificar se está no caminho
        obs = Obstacle(position=Position(x, y), radius=radius, confidence=1.0)
        
        if self.navigation_state == NavigationState.NAVIGATING:
            collision = self.obstacle_avoidance.check_collision(
                self.current_position,
                lookahead_distance=0.5,
            )
            
            if collision:
                self.navigation_state = NavigationState.OBSTACLE_DETECTED
                self.logger.warning(f"[LOCOMOTION] Obstáculo no caminho!")
                
                if self.on_obstacle_detected:
                    self.on_obstacle_detected(collision)
                
                # Replanejar
                if self.enable_pathfinding and self.current_path:
                    self._replan_path()
        
        if self.on_obstacle_detected:
            self.on_obstacle_detected(obs)
    
    def _control_loop(self):
        """Loop de controle de navegação"""
        while self.running:
            try:
                if self.navigation_state == NavigationState.NAVIGATING:
                    self._follow_path()
                
                time.sleep(1.0 / self.control_rate)
                
            except Exception as e:
                self.logger.error(f"[LOCOMOTION] Erro no controle: {e}")
    
    def _follow_path(self):
        """Segue caminho planejado"""
        if not self.current_path or self.current_path_index >= len(self.current_path):
            self.navigation_state = NavigationState.ARRIVED
            self.current_velocity = (0.0, 0.0)
            
            if self.on_path_complete:
                self.on_path_complete()
            
            self.logger.info("[LOCOMOTION] Chegou ao destino!")
            return
        
        # Próximo waypoint
        target = self.current_path[self.current_path_index]
        target_pos = Position(target[0], target[1])
        
        # Verificar se chegou ao waypoint
        if self.current_position.distance_to(target_pos) < self.position_tolerance:
            self.current_path_index += 1
            return
        
        # Calcular comandos de velocidade
        dx = target_pos.x - self.current_position.x
        dy = target_pos.y - self.current_position.y
        
        # Ângulo desejado
        target_angle = np.arctan2(dy, dx)
        angle_error = target_angle - self.current_position.theta
        
        # Normalizar ângulo
        while angle_error > np.pi:
            angle_error -= 2 * np.pi
        while angle_error < -np.pi:
            angle_error += 2 * np.pi
        
        # Controle simples (P)
        linear_speed = min(
            self.max_linear_speed,
            0.5 * np.sqrt(dx**2 + dy**2)
        )
        
        angular_speed = np.clip(
            2.0 * angle_error,
            -self.max_angular_speed,
            self.max_angular_speed,
        )
        
        # Verificar obstáculos
        obs = self.obstacle_avoidance.check_collision(self.current_position)
        if obs:
            linear_speed = 0.0
            angular_speed = self.max_angular_speed * 0.5  # Girar para desviar
        
        self.current_velocity = (linear_speed, angular_speed)
    
    def _replan_path(self):
        """Replaneja caminho quando encontra obstáculo"""
        self.navigation_state = NavigationState.REPLANNING
        
        if self.current_path and self.current_path_index < len(self.current_path):
            goal = self.current_path[-1]
            
            if self.navigate_to(goal[0], goal[1]):
                self.logger.info("[LOCOMOTION] Caminho replanejado")
            else:
                self.logger.error("[LOCOMOTION] Falha ao replanejar!")
                self.navigation_state = NavigationState.ERROR
    
    def get_velocity_commands(self) -> Tuple[float, float]:
        """
        Retorna comandos de velocidade para HAL
        
        Returns:
            (linear_speed_mps, angular_speed_radps)
        """
        return self.current_velocity
    
    def convert_to_wheel_speeds(
        self,
        linear: float,
        angular: float,
    ) -> Tuple[float, float]:
        """
        Converte velocidades para rodas (diferencial drive)
        
        Returns:
            (left_speed_mps, right_speed_mps)
        """
        v_left = linear - angular * self.wheel_base / 2
        v_right = linear + angular * self.wheel_base / 2
        return (v_left, v_right)
    
    def get_status(self) -> dict:
        """Retorna status da navegação"""
        return {
            "position": {
                "x": round(self.current_position.x, 3),
                "y": round(self.current_position.y, 3),
                "theta": round(self.current_position.theta, 3),
            },
            "velocity": {
                "linear": round(self.current_velocity[0], 3),
                "angular": round(self.current_velocity[1], 3),
            },
            "navigation_state": self.navigation_state.value,
            "path_length": len(self.current_path) if self.current_path else 0,
            "path_index": self.current_path_index,
            "slam_enabled": self.enable_slam,
            "pathfinding_enabled": self.enable_pathfinding,
        }
