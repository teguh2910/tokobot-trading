import hashlib
import hmac
import time
from urllib.parse import urlencode
from config import config


def generate_signature(params: dict, secret_key: str = None) -> str:
    sk = secret_key or config.SECRET_KEY
    query_string = urlencode(params)
    signature = hmac.new(
        sk.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature


def signed_params(params: dict = None, recv_window: int = None) -> dict:
    if params is None:
        params = {}
    params["timestamp"] = int(time.time() * 1000)
    if recv_window is not None:
        params["recvWindow"] = recv_window
    params["signature"] = generate_signature(params)
    return params
