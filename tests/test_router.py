"""Тесты для shared.router."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.router import route_request, _route_via_keywords


def test_route_tools_request_keywords():
    """Ключевые слова → tools_request."""
    assert _route_via_keywords("прочитай /tmp/readme.txt") == "tools_request"
    assert _route_via_keywords("прочти файл config.yaml") == "tools_request"
    assert _route_via_keywords("посмотри папку /var/log") == "tools_request"
    assert _route_via_keywords("list dir /home") == "tools_request"
    assert _route_via_keywords("запиши в файл /tmp/out.txt") == "tools_request"
    assert _route_via_keywords("создай файл test.txt") == "tools_request"


def test_route_new_thought():
    """Обычная мысль → new_thought."""
    assert _route_via_keywords("Мне пришла идея о проекте") == "new_thought"
    assert _route_via_keywords("Добавь напоминание на завтра") == "new_thought"


def test_route_chitchat():
    """Короткие приветствия → chitchat."""
    assert _route_via_keywords("привет") == "chitchat"
    assert _route_via_keywords("спасибо") == "chitchat"
    assert _route_via_keywords("ок") == "chitchat"


def test_route_request_default():
    """route_request с дефолтным роутером (keywords)."""
    assert route_request("прочитай файл X") == "tools_request"
    assert route_request("Идея по улучшению") == "new_thought"
