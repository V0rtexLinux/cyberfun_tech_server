# Cyber Fun Endoskeleton API Reference

## Core Module

### HardwareController

```python
from core import HardwareController

hw = HardwareController(serial_port="/dev/ttyACM0")
hw.connect()

# Servos
hw.set_servo_pulse(0, 1500)  # Jaw, neutral
hw.set_servo_angle(3, 20)    # Eye X, 20 degrees right
hw.set_multiple_servos({0: 1500, 1: 2500})

# Motors
hw.set_motor_speed("left", 128)
hw.set_both_motors(100, 100)
hw.stop_all_motors()

# LEDs
hw.set_led_rgb("left_eye", 0, 100, 255)

# Safety
hw.emergency_stop()
hw.activate_failsafe()
```

### FacialExpressionController

```python
from core import FacialExpressionController, EmotionPreset

expr = FacialExpressionController()
expr.set_pwm_callback(hw.set_servo_pulse)
expr.start_expression_loop()

# Emotions
expr.set_emotion(EmotionPreset.HAPPY)
expr.set_emotion(EmotionPreset.EXCITED, duration=0.5)
expr.set_emotion(EmotionPreset.SURPRISED)

# Manual control
expr.look_at(30, 15)      # X, Y degrees
expr.open_jaw(25)
expr.do_wink("right")
expr.set_ears(15)

# Lip sync
expr.start_lip_sync()
expr.process_audio_for_lip_sync(audio_data)
expr.stop_lip_sync()
```

### AIChatBrain

```python
from core.ai import AIChatBrain, PersonalityMode, AIResponse

brain = AIChatBrain(openai_key=os.getenv("OPENAI_API_KEY"))
brain.start()

# Callback
def on_response(response: AIResponse):
    print(f"Text: {response.text}")
    print(f"Emotion: {response.emotion}")
    print(f"Voice: {response.tts_voice}")

brain.on_response = on_response

# Chat
brain.chat("Olá Fredbear!")

# Change personality
brain.set_mode(PersonalityMode.EXCITED)
brain.set_mode(PersonalityMode.CREEPY)

# Status
status = brain.get_status()
```

### FaceTracker

```python
from core.vision.face_tracker import FaceTracker

tracker = FaceTracker(
    camera_index=0,
    resolution=(640, 480),
    tracking_distance=100,
)

# Callbacks
tracker.on_gaze_direction = lambda x, y: expression.look_at(x, y)
tracker.on_face_detected = lambda face: print(f"New face: {face.face_id}")
tracker.on_face_lost = lambda id: print(f"Lost face: {id}")

# Start
tracker.start()

# Get tracked faces
faces = tracker.get_tracked_faces()
primary = tracker.get_primary_face()

# Status
status = tracker.get_status()
```

### AdvancedLocomotion

```python
from core.locomotion import AdvancedLocomotion

nav = AdvancedLocomotion(
    wheel_base=0.3,
    max_linear_speed=0.5,
    enable_slam=True,
    enable_pathfinding=True,
)

nav.start()

# Navigation
nav.navigate_to(x=2.5, y=1.0)

# Update position (from odometry/SLAM)
nav.update_position(x=0.1, y=0.0, theta=0.1)

# Report obstacle
nav.report_obstacle(x=1.0, y=0.5, radius=0.1)

# Get commands for HAL
linear, angular = nav.get_velocity_commands()
left_speed, right_speed = nav.convert_to_wheel_speeds(linear, angular)

# Callbacks
nav.on_path_complete = lambda: print("Arrived!")
nav.on_obstacle_detected = lambda obs: print(f"Obstacle!")
```

### Configuration

```python
from core.config import load_config, save_config

# Load
config = load_config("config/fredbear.yaml")

# Access
print(config.name)
print(config.hardware["Jaw"].max_angle)
print(config.ai.backend_priority)
print(config.vision.resolution)

# Modify
config.ai.max_tokens = 150

# Save
save_config(config, "config/custom.yaml")

# Defaults
from core.config.loader import get_fredbear_default_config
config = get_fredbear_default_config()
```

## WebSocket API

### Servidor

```python
from core.network.ws_server import CyberFunWebServer

server = CyberFunWebServer(port=8765)
server.inject_systems(
    kernel=kernel,
    tts=tts,
    ai=ai,
    expression=expression,
    show=show,
)
server.start()
```

### Protocolo

**Conectar:**
```javascript
ws = new WebSocket("ws://raspberrypi:8765")
```

**Enviar comando:**
```json
{
  "type": "COMMAND",
  "action": "set_emotion",
  "params": {"emotion": "happy", "duration": 0.5}
}
```

**Receber status:**
```json
{
  "type": "STATUS",
  "data": {
    "expression": {"jaw_angle": 5, "emotion": "happy"},
    "sensors": {"pir": true, "ultrasonic": 45},
    "position": {"x": 0.5, "y": 1.2}
  }
}
```

**Ações disponíveis:**

| Ação | Parâmetros | Descrição |
|------|------------|-----------|
| `set_emotion` | `emotion`, `duration` | Muda expressão facial |
| `speak` | `text`, `voice` | Texto para fala |
| `look_at` | `x`, `y` | Move olhos |
| `navigate_to` | `x`, `y` | Navegação autônoma |
| `start_show` | `show_name` | Inicia show |
| `emergency_stop` | - | Parada de emergência |
| `chat` | `message` | Conversa com IA |

## Eventos

### Sistema

```python
# Hardware callbacks
hw.on_emergency_callback = lambda reason: print(f"Emergency: {reason}")
hw.on_sensor_update_callback = lambda data: print(f"Sensor: {data}")

# Kernel callbacks
kernel.register_callback(SystemState.IDLE, on_idle)
kernel.register_callback(SystemState.EMERGENCY, on_emergency)

# Sensor callbacks
sensors.pir.on_detected = on_presence
sensors.ultrasonic.on_obstacle = on_obstacle
sensors.imu.on_tilt = on_tilt
```

### Eventos Disponíveis

| Evento | Fonte | Dados |
|--------|-------|-------|
| `presence_detected` | PIR | - |
| `obstacle_detected` | Ultrasonic | `distance`, `direction` |
| `excessive_tilt` | IMU | `roll`, `pitch` |
| `face_detected` | Vision | `face_id`, `position` |
| `tts_start` | TTS | `text` |
| `tts_end` | TTS | `text` |
| `ai_response` | AI | `text`, `emotion` |
| `path_complete` | Locomotion | - |

## Constants

### EmotionPreset

```python
class EmotionPreset(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    SURPRISED = "surprised"
    SAD = "sad"
    ANGRY = "angry"
    WINK = "wink"
    BLINK = "blink"
    TALKING = "talking"
    SINGING = "singing"
    LAUGHING = "laughing"
    SLEEPY = "sleepy"
```

### SystemState

```python
class SystemState(Enum):
    OFFLINE = "offline"
    INITIALIZING = "initializing"
    IDLE = "idle"
    WANDERING = "wandering"
    INTERACTING = "interacting"
    SHOWTIME = "showtime"
    PERFORMING = "performing"
    MAINTENANCE = "maintenance"
    EMERGENCY = "emergency"
    ERROR = "error"
    SHUTDOWN = "shutdown"
```

### PersonalityMode

```python
class PersonalityMode(Enum):
    FRIENDLY = "friendly"
    EXCITED = "excited"
    CREEPY = "creepy"
    STORYTELLER = "storyteller"
    DJ = "dj"
    GUARDIAN = "guardian"
```

## Exemplos

### Exemplo 1: Interação Básica

```python
import os
from core import HardwareController, FacialExpressionController
from core.ai import AIChatBrain, PersonalityMode
from core.tts import TTSManager

# Inicializar
hw = HardwareController()
hw.connect("/dev/ttyACM0")

expr = FacialExpressionController()
expr.set_pwm_callback(hw.set_servo_pulse)
expr.start_expression_loop()

tts = TTSManager()
tts.start()

brain = AIChatBrain(openai_key=os.getenv("OPENAI_API_KEY"))

def on_ai_response(response):
    # Atualizar expressão
    expr.set_emotion(response.expression)
    
    # Falar
    tts.speak(response.text, voice=response.tts_voice)

brain.on_response = on_ai_response
brain.start()

# Loop principal
while True:
    user_input = input("Você: ")
    brain.chat(user_input)
```

### Exemplo 2: Navegação Autônoma

```python
from core import HardwareController
from core.locomotion import AdvancedLocomotion

hw = HardwareController()
nav = AdvancedLocomotion(
    wheel_base=0.3,
    enable_slam=True,
    enable_pathfinding=True,
)

nav.start()

def on_path_complete():
    print("Chegamos!")
    hw.set_motor_speed("left", 0)
    hw.set_motor_speed("right", 0)

nav.on_path_complete = on_path_complete

# Navegar
nav.navigate_to(x=3.0, y=2.0)

# Loop de controle
while nav.navigation_state != NavigationState.ARRIVED:
    linear, angular = nav.get_velocity_commands()
    left, right = nav.convert_to_wheel_speeds(linear, angular)
    
    hw.set_motor_speed("left", int(left * 255))
    hw.set_motor_speed("right", int(right * 255))
    
    time.sleep(0.05)
```

### Exemplo 3: Controle WebSocket

```javascript
const ws = new WebSocket("ws://localhost:8765")

// Receber status
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.type === "STATUS") {
        console.log("Expression:", msg.data.expression)
    }
}

// Enviar comandos
function setEmotion(emotion) {
    ws.send(JSON.stringify({
        type: "COMMAND",
        action: "set_emotion",
        params: { emotion, duration: 0.5 }
    }))
}

function speak(text) {
    ws.send(JSON.stringify({
        type: "COMMAND",
        action: "speak",
        params: { text, voice: "cheerful" }
    }))
}
```

---

**Versão:** 3.1.0
