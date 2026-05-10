"""
================================================================================
  CYBER FUN ENDOSKELETON - Servidor WebSocket
  Controle remoto em tempo real via rede local ou internet
================================================================================
  Permite controlar o animatrônico de qualquer dispositivo:
    - Dashboard web (browser)
    - App mobile
    - Outro computador na rede
  
  Endpoints REST:
    GET  /api/status       - Status completo do sistema
    GET  /api/servos       - Posições dos servos
    POST /api/servo        - Mover servo
    POST /api/expression   - Aplicar expressão
    POST /api/speak        - Fazer o Springbonnie falar
    POST /api/chat         - Conversar com a IA
    POST /api/show/play    - Iniciar show
    POST /api/show/stop    - Parar show
    POST /api/estop        - Emergência
    GET  /api/streams/video - Stream de câmera
  
  WebSocket /ws:
    Recebe: JSON {"type": "CMD", "data": {...}}
    Envia:  JSON {"type": "STATUS"|"EVENT"|"SENSOR", "data": {...}}
================================================================================
"""

import asyncio
import json
import logging
import time
import threading
from dataclasses import dataclass, asdict
from typing import Optional, Set, Callable, Dict, Any
from enum import Enum

logger = logging.getLogger("CyberFun.Network")

try:
    import websockets
    from aiohttp import web
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False
    logger.warning("[WS] websockets/aiohttp não disponíveis. pip install websockets aiohttp")


class MessageType(Enum):
    STATUS   = "STATUS"
    COMMAND  = "CMD"
    EVENT    = "EVENT"
    SENSOR   = "SENSOR"
    CHAT     = "CHAT"
    ERROR    = "ERROR"
    HELLO    = "HELLO"


@dataclass
class WSMessage:
    type: str
    data: dict
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "data": self.data, "ts": self.timestamp})


class CommandHandler:
    """Handler para comandos recebidos via WebSocket/REST."""

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}

    def register(self, command: str, handler: Callable):
        self._handlers[command] = handler

    def handle(self, command: str, params: dict) -> dict:
        if command in self._handlers:
            try:
                result = self._handlers[command](params)
                return {"success": True, "result": result or {}}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": f"Comando desconhecido: {command}"}


class CyberFunWebServer:
    """
    Servidor web + WebSocket para controle remoto do Springbonnie.
    Suporta múltiplos clientes simultâneos.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.logger = logging.getLogger("CyberFun.Network")

        # Clientes conectados
        self.ws_clients: Set = set()
        self.client_lock = threading.Lock()

        # Handler de comandos
        self.cmd_handler = CommandHandler()

        # Referências ao sistema principal (injetadas externamente)
        self.kernel_ref = None
        self.tts_ref = None
        self.ai_ref = None
        self.expression_ref = None
        self.show_ref = None

        # App aiohttp
        self.app = None
        self.runner = None
        self.site = None

        # Thread do servidor
        self.loop = None
        self.server_thread = None
        self.running = False

        # Buffer de eventos para broadcast
        self.broadcast_queue: asyncio.Queue = None

        # Estatísticas
        self.total_connections = 0
        self.total_messages = 0
        self.start_time = time.time()

        self.logger.info(f"[WS] Servidor configurado em {host}:{port}")

    def inject_systems(self, kernel=None, tts=None, ai=None, expression=None, show=None):
        """Injeta referências aos subsistemas."""
        self.kernel_ref     = kernel
        self.tts_ref        = tts
        self.ai_ref         = ai
        self.expression_ref = expression
        self.show_ref       = show
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Registra handlers padrão para comandos."""

        # --- SERVOS ---
        def cmd_servo(params):
            if not self.kernel_ref: return {}
            servo_id = params.get("id", 0)
            pulse    = params.get("pulse", 1500)
            self.kernel_ref.send_command("set_servo", {"id": servo_id, "pulse": pulse})
            return {"servo": servo_id, "pulse": pulse}

        def cmd_expression(params):
            if not self.expression_ref: return {}
            emotion = params.get("emotion", "neutral")
            duration = params.get("duration", 0.3)
            from Springbonnie_system.expression.facial_controller import EmotionPreset
            try:
                preset = EmotionPreset(emotion)
                self.expression_ref.set_emotion(preset, duration=duration)
                return {"emotion": emotion}
            except ValueError:
                return {"error": f"Emoção desconhecida: {emotion}"}

        def cmd_speak(params):
            if not self.tts_ref: return {}
            text    = params.get("text", "")
            voice   = params.get("voice", "robot_male")
            speed   = params.get("speed", 1.0)
            pitch   = params.get("pitch", 1.0)
            if not text: return {"error": "Texto vazio"}
            from Springbonnie_system.tts.tts_engine import TTSVoice
            try:
                voice_enum = TTSVoice(voice)
            except ValueError:
                voice_enum = TTSVoice.ROBOT_MALE
            self.tts_ref.speak(text, voice=voice_enum, speed=speed, pitch=pitch)
            return {"speaking": text[:50]}

        def cmd_chat(params):
            if not self.ai_ref: return {}
            text = params.get("text", "")
            if not text: return {"error": "Texto vazio"}
            responses = []
            def on_resp(r):
                responses.append(r)
            self.ai_ref.chat(text, callback=on_resp)
            return {"queued": True, "input": text[:50]}

        def cmd_show_play(params):
            if not self.show_ref: return {}
            track = params.get("track", "")
            if track:
                pass  # load specific track
            self.show_ref.start_show()
            return {"show": "started"}

        def cmd_show_stop(params):
            if not self.show_ref: return {}
            self.show_ref.stop_show()
            return {"show": "stopped"}

        def cmd_motors(params):
            if not self.kernel_ref: return {}
            left  = params.get("left", 0)
            right = params.get("right", 0)
            self.kernel_ref.send_command("set_motors", {"left": left, "right": right})
            return {"motors": {"left": left, "right": right}}

        def cmd_estop(params):
            if not self.kernel_ref: return {}
            self.kernel_ref.send_command("emergency_stop", priority_override=True)
            return {"emergency_stop": True}

        def cmd_led(params):
            if not self.kernel_ref: return {}
            start  = params.get("start", 0)
            end    = params.get("end", 59)
            r, g, b = params.get("r", 0), params.get("g", 100), params.get("b", 255)
            self.kernel_ref.send_command("set_leds", {"start": start, "end": end, "r": r, "g": g, "b": b})
            return {"leds": {"start": start, "end": end, "color": [r, g, b]}}

        def cmd_home(params):
            if not self.kernel_ref: return {}
            self.kernel_ref.send_command("home_servos", {})
            return {"home": True}

        def cmd_status(params):
            status = {}
            if self.kernel_ref:     status["kernel"]     = self.kernel_ref.get_status()
            if self.tts_ref:        status["tts"]        = self.tts_ref.get_status()
            if self.ai_ref:         status["ai"]         = self.ai_ref.get_status()
            if self.expression_ref: status["expression"] = self.expression_ref.get_status()
            status["server"] = self.get_server_stats()
            return status

        # Registrar handlers
        self.cmd_handler.register("servo",      cmd_servo)
        self.cmd_handler.register("expression", cmd_expression)
        self.cmd_handler.register("speak",      cmd_speak)
        self.cmd_handler.register("chat",       cmd_chat)
        self.cmd_handler.register("show_play",  cmd_show_play)
        self.cmd_handler.register("show_stop",  cmd_show_stop)
        self.cmd_handler.register("motors",     cmd_motors)
        self.cmd_handler.register("estop",      cmd_estop)
        self.cmd_handler.register("led",        cmd_led)
        self.cmd_handler.register("home",       cmd_home)
        self.cmd_handler.register("status",     cmd_status)

    def start(self):
        """Inicia servidor em thread separada."""
        if not WEB_AVAILABLE:
            self.logger.error("[WS] Dependências não instaladas. Execute: pip install websockets aiohttp")
            return

        self.running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        self.logger.info(f"[WS] Servidor iniciando em ws://{self.host}:{self.port}")

    def _run_server(self):
        """Executa loop asyncio em thread dedicada."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.broadcast_queue = asyncio.Queue()
        self.loop.run_until_complete(self._start_server())

    async def _start_server(self):
        """Inicializa app aiohttp com REST + WebSocket."""
        self.app = web.Application()

        # WebSocket
        self.app.router.add_get('/ws', self._ws_handler)

        # REST API
        self.app.router.add_get('/api/status',         self._rest_status)
        self.app.router.add_post('/api/servo',          self._rest_servo)
        self.app.router.add_post('/api/expression',     self._rest_expression)
        self.app.router.add_post('/api/speak',          self._rest_speak)
        self.app.router.add_post('/api/chat',           self._rest_chat)
        self.app.router.add_post('/api/show/play',      self._rest_show_play)
        self.app.router.add_post('/api/show/stop',      self._rest_show_stop)
        self.app.router.add_post('/api/estop',          self._rest_estop)
        self.app.router.add_post('/api/motors',         self._rest_motors)
        self.app.router.add_post('/api/led',            self._rest_led)
        self.app.router.add_get('/api/servos',          self._rest_servos)
        self.app.router.add_get('/health',              self._rest_health)

        # CORS headers
        self.app.middlewares.append(self._cors_middleware)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self.logger.info(f"[WS] Servidor ativo em http://{self.host}:{self.port}")

        # Loop de broadcast
        await self._broadcast_loop()

    @web.middleware
    async def _cors_middleware(self, request, handler):
        if request.method == "OPTIONS":
            return web.Response(headers={
                "Access-Control-Allow-Origin":  "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            })
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    async def _ws_handler(self, request):
        """Handler de WebSocket."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        client_ip = request.remote
        self.ws_clients.add(ws)
        self.total_connections += 1
        self.logger.info(f"[WS] Cliente conectado: {client_ip} ({len(self.ws_clients)} total)")

        # Mensagem de boas-vindas
        await ws.send_str(WSMessage(
            type=MessageType.HELLO.value,
            data={"version": "3.0", "name": "CyberFun", "uptime": time.time() - self.start_time}
        ).to_json())

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, msg.data)
                    self.total_messages += 1
                elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                    break
        except Exception as e:
            self.logger.error(f"[WS] Erro cliente {client_ip}: {e}")
        finally:
            self.ws_clients.discard(ws)
            self.logger.info(f"[WS] Cliente desconectado: {client_ip}")

        return ws

    async def _handle_ws_message(self, ws, raw: str):
        """Processa mensagem WebSocket recebida."""
        try:
            msg = json.loads(raw)
            cmd_type = msg.get("type", "")
            data     = msg.get("data", {})

            if cmd_type == "CMD":
                command = data.get("command", "")
                params  = data.get("params", {})
                result  = self.cmd_handler.handle(command, params)
                await ws.send_str(WSMessage(type="RESULT", data={"command": command, **result}).to_json())

            elif cmd_type == "PING":
                await ws.send_str(WSMessage(type="PONG", data={"ts": time.time()}).to_json())

        except json.JSONDecodeError:
            await ws.send_str(WSMessage(type="ERROR", data={"error": "JSON inválido"}).to_json())
        except Exception as e:
            await ws.send_str(WSMessage(type="ERROR", data={"error": str(e)}).to_json())

    async def _broadcast_loop(self):
        """Loop de broadcast de eventos para todos os clientes."""
        while self.running:
            try:
                msg = await asyncio.wait_for(self.broadcast_queue.get(), timeout=1.0)
                if self.ws_clients:
                    dead = set()
                    for ws in self.ws_clients:
                        try:
                            await ws.send_str(msg)
                        except Exception:
                            dead.add(ws)
                    self.ws_clients -= dead
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                self.logger.error(f"[WS] Erro broadcast: {e}")

    def broadcast(self, msg_type: str, data: dict):
        """Envia evento para todos os clientes conectados."""
        if self.loop and self.broadcast_queue:
            msg = WSMessage(type=msg_type, data=data).to_json()
            asyncio.run_coroutine_threadsafe(
                self.broadcast_queue.put(msg), self.loop
            )

    # ==================== REST HANDLERS ====================

    async def _rest_status(self, request):
        result = self.cmd_handler.handle("status", {})
        return web.json_response(result)

    async def _rest_servo(self, request):
        data = await request.json()
        result = self.cmd_handler.handle("servo", data)
        return web.json_response(result)

    async def _rest_expression(self, request):
        data = await request.json()
        result = self.cmd_handler.handle("expression", data)
        return web.json_response(result)

    async def _rest_speak(self, request):
        data = await request.json()
        result = self.cmd_handler.handle("speak", data)
        return web.json_response(result)

    async def _rest_chat(self, request):
        data = await request.json()
        result = self.cmd_handler.handle("chat", data)
        return web.json_response(result)

    async def _rest_show_play(self, request):
        data = await request.json() if request.content_length else {}
        result = self.cmd_handler.handle("show_play", data)
        return web.json_response(result)

    async def _rest_show_stop(self, request):
        result = self.cmd_handler.handle("show_stop", {})
        return web.json_response(result)

    async def _rest_estop(self, request):
        result = self.cmd_handler.handle("estop", {})
        return web.json_response(result)

    async def _rest_motors(self, request):
        data = await request.json()
        result = self.cmd_handler.handle("motors", data)
        return web.json_response(result)

    async def _rest_led(self, request):
        data = await request.json()
        result = self.cmd_handler.handle("led", data)
        return web.json_response(result)

    async def _rest_servos(self, request):
        status = {}
        if self.kernel_ref:
            status = self.kernel_ref.hal.get_status().get("servos", {})
        return web.json_response(status)

    async def _rest_health(self, request):
        return web.json_response({"status": "ok", "uptime": time.time() - self.start_time})

    def get_server_stats(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "connected_clients": len(self.ws_clients),
            "total_connections": self.total_connections,
            "total_messages": self.total_messages,
            "uptime_s": round(time.time() - self.start_time, 1),
        }

    def stop(self):
        self.running = False
        if self.runner:
            asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop)
        self.logger.info("[WS] Servidor parado")

