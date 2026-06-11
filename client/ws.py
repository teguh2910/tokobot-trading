import json
import threading
import time
import logging
from typing import Callable, Optional
from config import config

try:
    import websocket
except ImportError:
    websocket = None

logger = logging.getLogger("tokobot.ws")


class TokocryptoWebSocket:
    WS_URL = "wss://stream-cloud.tokocrypto.site/stream"

    def __init__(self):
        self.ws: Optional[websocket.WebSocketApp] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.listen_key: str = ""
        self.callbacks: dict = {}
        self.subscribed_streams: list = []

    def on_message(self, callback: Callable, stream: str = None):
        key = stream or "default"
        self.callbacks[key] = callback

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "stream" in data and "data" in data:
                stream_name = data["stream"]
                cb = self.callbacks.get(stream_name) or self.callbacks.get("default")
                if cb:
                    cb(data["data"])
            elif "e" in data:
                cb = self.callbacks.get("default")
                if cb:
                    cb(data)
        except Exception as e:
            logger.error(f"WS message error: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WS error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"WS closed: {close_status_code} - {close_msg}")
        self.running = False
        if self.listen_key:
            logger.warning("User data stream closed, attempting reconnect...")
            self._reconnect()

    def _on_open(self, ws):
        logger.info("WS connected")
        self.running = True
        if self.subscribed_streams:
            self._send_subscribe(self.subscribed_streams)

    def _send_subscribe(self, streams: list):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            msg = json.dumps({
                "method": "SUBSCRIBE",
                "params": streams,
                "id": 1
            })
            self.ws.send(msg)

    def connect(self, streams: list = None):
        if websocket is None:
            logger.error("websocket-client not installed")
            return

        self.subscribed_streams = streams or []
        self.ws = websocket.WebSocketApp(
            self.WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()

    def subscribe_user_data(self, listen_key: str):
        self.listen_key = listen_key
        user_stream = f"wss://stream-cloud.tokocrypto.site/ws/{listen_key}"
        if websocket is None:
            return

        def on_user_msg(ws, message):
            try:
                data = json.loads(message)
                cb = self.callbacks.get("user_data") or self.callbacks.get("default")
                if cb:
                    cb(data)
            except Exception as e:
                logger.error(f"User data WS error: {e}")

        self.ws_user = websocket.WebSocketApp(
            user_stream,
            on_message=on_user_msg,
            on_error=self._on_error,
            on_close=lambda ws, code, msg: logger.info(f"User data WS closed: {code}")
        )
        self.user_thread = threading.Thread(target=self.ws_user.run_forever, daemon=True)
        self.user_thread.start()

    def _reconnect(self, delay: int = 5):
        time.sleep(delay)
        logger.info("Reconnecting WS...")
        self.connect(self.subscribed_streams)

    def close(self):
        self.running = False
        if self.ws:
            self.ws.close()
        if hasattr(self, "ws_user") and self.ws_user:
            self.ws_user.close()
