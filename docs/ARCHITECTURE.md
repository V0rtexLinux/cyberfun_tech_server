# Cyber Fun Endoskeleton v3.1.0 - Arquitetura Técnica

## Visão Geral

O Cyber Fun Endoskeleton é um sistema de controle animatrônico profissional, projetado para operar com hardware Raspberry Pi 4 + Arduino Mega 2560. O sistema suporta dois personagens (Fredbear e Springbonnie) com código compartilhado via módulo `core/`.

```
┌─────────────────────────────────────────────────────────────────┐
│                         APLICAÇÃO                               │
│              (Fredbear / Springbonnie / Simulator)              │
├─────────────────────────────────────────────────────────────────┤
│                         CORE MODULE                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │   HAL    │ │Expression│ │   AI     │ │  Vision  │           │
│  │(Hardware)│ │ (Facial) │ │ (Brain)  │ │(FaceTrack│           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  Kernel │ │  TTS     │ │ Locomotion│ │ Network  │           │
│  │  (FSM)  │ │(Speech)  │ │ (Nav)    │ │(WebSock) │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
├─────────────────────────────────────────────────────────────────┤
│                    CONFIGURAÇÃO (YAML)                          │
├─────────────────────────────────────────────────────────────────┤
│                      HARDWARE INTERFACE                         │
│              Serial (USB) / GPIO / I2C / PWM                   │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. HAL - Hardware Abstraction Layer

**Arquivo:** `core/hal/hardware_controller.py`

Responsável por toda comunicação com hardware físico:

- **Protocolo Serial Binário:** `0xAA [CMD] [DATA...] 0x55`
- **Servos:** 7 canais PWM (500-2500µs)
- **Motores:** 2 canais DC com controle diferencial
- **LEDs:** 2 RGB para olhos
- **Safety:** Watchdog 5s, failsafe automático

```python
class HardwareController:
    def set_servo_pulse(servo_id: int, pulse: int)
    def set_motor_speed(motor_id: str, speed: int)
    def emergency_stop()
    def activate_failsafe()
```

### 2. Expression Controller

**Arquivo:** `core/expression/facial_controller.py`

Sistema de expressão facial de 7 eixos:

| Servo | Função | Range | Velocidade |
|-------|--------|-------|------------|
| 0 | Mandíbula | 0-45° | 120°/s |
| 1 | Pálpebra Esq | 0-100% | 400°/s |
| 2 | Pálpebra Dir | 0-100% | 400°/s |
| 3 | Olho X | -45° a +45° | 180°/s |
| 4 | Olho Y | -30° a +30° | 180°/s |
| 5 | Orelha Esq | -20° a +20° | 90°/s |
| 6 | Orelha Dir | -20° a +20° | 90°/s |

**Features:**
- 12 presets de emoção
- Suavização com easing functions (linear, ease_in_out, bounce, elastic)
- Auto-blink (2-6s intervalo)
- Lip-sync via análise de amplitude de áudio

### 3. AI Brain

**Arquivo:** `core/ai/ai_brain.py`

Sistema de IA com fallback chain:

```
User Input
    ↓
OpenAI GPT-4o-mini (se disponível)
    ↓ (falha)
Ollama Local (llama3.2:3b)
    ↓ (falha)
Fallback Brain (respostas pré-programadas)
    ↓
Emotion Detection → Facial Expression
    ↓
TTS Voice Selection
```

**Modos de Personalidade:**
- `FRIENDLY` - Normal, amigável
- `EXCITED` - Empolgado, festa
- `CREEPY` - Modo noturno assustador
- `STORYTELLER` - Contador de histórias
- `DJ` - Modo show/música
- `GUARDIAN` - Protetor, sério

### 4. Face Tracker

**Arquivo:** `core/vision/face_tracker.py`

Sistema de visão computacional:

- **Detector:** Haar Cascade ou DNN (OpenCV)
- **Tracking:** Multi-face com ID persistente
- **Gaze Control:** Converte posição de rosto para ângulos oculares
- **Suavização:** Média móvel de 10 frames

```python
face_tracker.on_gaze_direction = expression.look_at
face_tracker.on_face_detected = on_new_visitor
```

### 5. Advanced Locomotion

**Arquivo:** `core/locomotion/advanced_locomotion.py`

Sistema de navegação autônoma:

- **SLAM:** Occupancy Grid 200x200 (resolução 5cm)
- **Pathfinding:** A* com heurística Euclidiana
- **Obstacle Avoidance:** Campos potenciais
- **Control:** Pure pursuit com PID

**Interface:**
```python
locomotion.navigate_to(x=2.5, y=1.0)
locomotion.report_obstacle(x=1.0, y=0.5, radius=0.1)
linear, angular = locomotion.get_velocity_commands()
```

### 6. FSM Kernel

**Arquivo:** `core/kernel/fsm_kernel.py`

Máquina de estados finita para comportamento seguro:

```
                    ┌─────────┐
                    │ OFFLINE │
                    └────┬────┘
                         │ initialize()
                    ┌────▼────┐
                    │INITIALIZ│
                    └────┬────┘
                         │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
        ┌────────┐  ┌──────┐  ┌────────┐
        │  IDLE  │  │ERROR │  │SHUTDOWN│
        └───┬────┘  └──┬───┘  └────────┘
            │          │
    ┌───────┼──────────┘
    ▼       ▼       ▼
┌──────┐ ┌──────┐ ┌────────┐
│WANDER│ │INTERA│ │SHOWTIME│
└──────┘ └──────┘ └────────┘
```

**Transições validadas:** Impede ações conflitantes (ex: wander durante show)

### 7. Configuration System

**Arquivo:** `core/config/loader.py`

Configuração via YAML centralizado:

```yaml
name: "Fredbear"
hardware:
  servos:
    - id: 0
      name: "Jaw"
      min_angle: 0.0
      max_angle: 45.0
ai:
  backend_priority: ["openai", "ollama", "fallback"]
  max_tokens: 100
vision:
  enabled: true
  track_faces: true
```

## Fluxo de Dados

### Inicialização

```
1. Parse args
2. Load config (YAML)
3. Init HAL
   └─ Connect serial
   └─ Load servo configs
4. Init Expression
   └─ Start update thread (60Hz)
5. Init Sensors
   └─ PIR, Ultrasonic, IMU, Mic
6. Init TTS
   └─ Load engines
7. Init AI
   └─ Detect backend
8. Init Vision (se enabled)
   └─ Start camera
9. Init Locomotion (se enabled)
10. Init Network
    └─ Start WebSocket
11. Boot animation
```

### Interação com Visitante

```
PIR Detection
    ↓
Kernel.transition_to(INTERACTING)
    ↓
FaceTracker.detect() → look_at(face_center)
    ↓
Expression.set_emotion(EXCITED)
    ↓
TTS.speak(greeting)
    ↓
AI.chat(user_input) → response
    ↓
Expression.set_emotion(detected_emotion)
    ↓
TTS.speak(response) + lip-sync
    ↓
Return to IDLE (timeout)
```

## Especificações Técnicas

### Hardware Requerido

| Componente | Especificação | Interface |
|------------|---------------|-----------|
| SBC | Raspberry Pi 4 (4GB+) | - |
| Microcontrolador | Arduino Mega 2560 | USB Serial |
| Servos | 7x MG996R / DS3218 | PWM 50Hz |
| Motores | 2x DC 12V com encoder | PWM + GPIO |
| Sensores | PIR HC-SR501 | GPIO |
| | Ultrassom HC-SR04 | GPIO |
| | IMU MPU-6050 | I2C |
| | Microfone USB | USB |
| Câmera | Raspberry Pi Camera v2 | CSI |
| LEDs | 2x RGB 5050 | GPIO/PWM |

### Consumo Estimado

- **Parado:** ~5W (Raspberry Pi idle)
- **Operação normal:** ~15W (servos ativos)
- **Pico:** ~25W (motores em movimento)

### Performance

| Operação | Latência |
|----------|----------|
| Serial command | <5ms |
| Servo update | ~16ms (60Hz) |
| Face detection | ~50ms |
| AI response | 1-3s (GPT) / <1s (fallback) |
| Path planning | <100ms (grid 200x200) |

## Segurança

### Mecanismos de Proteção

1. **FSM State Validation:** Impede comandos em estados incompatíveis
2. **Hardware Watchdog:** Reset automático após 5s sem heartbeat
3. **Failsafe:** Posições neutras ao perder comunicação
4. **E-Stop:** Parada imediata via comando serial 0xFE
5. **Servo Limits:** Clamp de ângulos e velocidades
6. **Motor Timeout:** Parada após 100ms sem comando

### Estados de Emergência

```python
EMERGENCY → Desliga tudo, mantém apenas sensores
ERROR → Log, tenta recovery
SHUTDOWN → Animação de desligamento, posições seguras
```

## Extensibilidade

### Adicionar Novo Comportamento

```python
# 1. Criar callback
kernel.fsm.register_callback(
    SystemState.MY_NEW_STATE,
    my_callback
)

# 2. Adicionar comando
kernel.register_command("my_command", my_handler)

# 3. Atualizar FSM transitions
kernel.fsm.valid_transitions[State.NEW] = {State.IDLE, State.EMERGENCY}
```

### Adicionar Novo Hardware

```python
class MyNewSensor:
    def __init__(self, callback):
        self.callback = callback
        self.thread = threading.Thread(target=self._loop)
    
    def _loop(self):
        while self.running:
            value = self.read()
            if value > threshold:
                self.callback(value)
```

## Testes

Suite completa em `tests/`:

```bash
# Todos os testes
pytest tests/ -v

# Com cobertura
pytest tests/ --cov=core --cov-report=html

# Específico
pytest tests/test_hardware.py::TestSerialProtocol -v
```

| Suite | Cobertura |
|-------|-----------|
| Config | 95% |
| Hardware | 80% |
| Expression | 90% |
| AI | 85% |
| Integration | 75% |

---

**Versão:** 3.1.0  
**Atualizado:** 2024
