"""Тесты для worker.processor: роутинг suggested_role в ассистент."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import IncomingMessage
from worker.processor import process_message


@patch("worker.processor.set_active_node")
@patch("worker.processor.universal_assistant")
@patch("worker.processor.rag_search")
@patch("worker.processor.add_chunk")
@patch("worker.processor.get_embedding")
@patch("worker.processor.create_edge")
@patch("worker.processor.create_node")
@patch("worker.processor.classify_topic")
@patch("worker.processor.get_last_nodes")
@patch("worker.processor.extract_theme")
def test_suggested_role_passed_to_assistant(
    mock_extract,
    mock_last_nodes,
    mock_classify,
    mock_create_node,
    mock_create_edge,
    mock_embedding,
    mock_add_chunk,
    mock_rag_search,
    mock_assistant,
    mock_set_active,
):
    """suggested_role из extract_theme передаётся в universal_assistant."""
    mock_extract.return_value = {
        "context_type": "project",
        "theme": "Проверь мой план",
        "key_parts": "",
        "action_type": "request",
        "parent_hint": None,
        "project_switch": False,
        "suggested_role": "critic",
    }
    mock_last_nodes.return_value = []
    mock_classify.return_value = (None, "continuation")
    mock_create_node.return_value = "node-123"
    mock_embedding.return_value = [0.0] * 1536
    mock_rag_search.return_value = []
    mock_assistant.return_value = "Вот критика..."

    incoming = IncomingMessage(chat_id=1, user_id=1, text="Проверь мой план", message_id=42)
    out = process_message(incoming)

    mock_assistant.assert_called_once()
    call_kwargs = mock_assistant.call_args[1]
    assert call_kwargs.get("role") == "critic"
    assert out.text == "Вот критика..."


@patch("worker.processor.run_planner")
@patch("worker.processor.universal_assistant")
def test_tools_empty_query(mock_assistant, mock_planner):
    """Команда /tools без аргумента — подсказка."""
    mock_planner.return_value = None
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/tools", message_id=1)
    out = process_message(incoming)
    assert "запрос" in out.text.lower()
    mock_planner.assert_not_called()


@patch("worker.processor.get_last_nodes")
@patch("worker.processor.universal_assistant")
@patch("worker.processor.run_planner")
def test_tools_uses_planner_fallback(mock_planner, mock_assistant, mock_last_nodes):
    """/tools <query>: planner возвращает None — fallback на universal_assistant."""
    mock_planner.return_value = None
    mock_assistant.return_value = "Fallback ответ"
    mock_last_nodes.return_value = []
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/tools прочитай файл", message_id=1)
    out = process_message(incoming)
    mock_planner.assert_called_once()
    mock_assistant.assert_called_once()
    assert out.text == "Fallback ответ"


@patch("worker.processor.get_last_nodes")
@patch("worker.processor.run_planner")
def test_tools_planner_success(mock_planner, mock_last_nodes):
    """/tools <query>: planner возвращает ответ — его отдаём."""
    mock_planner.return_value = "Результат из MCP"
    mock_last_nodes.return_value = []
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/tools list /tmp", message_id=1)
    out = process_message(incoming)
    assert out.text == "Результат из MCP"
    mock_planner.assert_called_once()


@patch("worker.processor.USE_PLANNER_AUTO", True)
@patch("worker.processor.get_last_nodes")
@patch("worker.processor.universal_assistant")
@patch("worker.processor.run_planner")
def test_planner_auto_tools_request(mock_planner, mock_assistant, mock_last_nodes):
    """USE_PLANNER_AUTO: «прочитай файл X» → planner без /tools."""
    mock_planner.return_value = "Содержимое файла..."
    mock_last_nodes.return_value = []
    incoming = IncomingMessage(chat_id=1, user_id=1, text="прочитай файл /tmp/readme.txt", message_id=1)
    out = process_message(incoming)
    mock_planner.assert_called_once()
    mock_assistant.assert_not_called()
    assert out.text == "Содержимое файла..."


@patch("worker.processor.USE_PLANNER_AUTO", True)
@patch("worker.processor.universal_assistant")
@patch("worker.processor.rag_search")
@patch("worker.processor.add_chunk")
@patch("worker.processor.get_embedding")
@patch("worker.processor.set_active_node")
@patch("worker.processor.create_edge")
@patch("worker.processor.create_node")
@patch("worker.processor.classify_topic")
@patch("worker.processor.get_last_nodes")
@patch("worker.processor.extract_theme")
@patch("worker.processor.run_planner")
def test_planner_auto_fallback(
    mock_planner, mock_extract, mock_last_nodes, mock_classify,
    mock_create_node, mock_create_edge, mock_set_active,
    mock_embedding, mock_add_chunk, mock_rag_search, mock_assistant,
):
    """USE_PLANNER_AUTO: planner возвращает None → fallback universal_assistant."""
    mock_planner.return_value = None
    mock_extract.return_value = {
        "context_type": "project",
        "theme": "прочитай файл",
        "key_parts": "",
        "action_type": "new_thought",
        "parent_hint": None,
        "project_switch": False,
        "suggested_role": "universal",
    }
    mock_last_nodes.return_value = []
    mock_classify.return_value = (None, "continuation")
    mock_create_node.return_value = "node-1"
    mock_embedding.return_value = [0.0] * 1536
    mock_rag_search.return_value = []
    mock_assistant.return_value = "Fallback"

    incoming = IncomingMessage(chat_id=1, user_id=1, text="прочитай файл /tmp/x.txt", message_id=1)
    out = process_message(incoming)

    mock_planner.assert_called_once()
    mock_assistant.assert_called_once()
    assert out.text == "Fallback"


@patch("worker.processor.get_map")
def test_map_returns_text(mock_get_map):
    """Команда /map возвращает непустой текст."""
    mock_get_map.return_value = ([], [])
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/map", message_id=1)
    out = process_message(incoming)
    assert out.text
    assert "Карта пуста" in out.text


@patch("worker.processor.get_last_nodes")
def test_del_last_empty(mock_last_nodes):
    """Команда /del last при пустой карте."""
    mock_last_nodes.return_value = []
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/del last", message_id=1)
    out = process_message(incoming)
    assert "Нет записей" in out.text


@patch("worker.processor.get_active_node")
def test_topic_no_active(mock_get_active):
    """Команда /topic при отсутствии активной темы."""
    mock_get_active.return_value = None
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/topic", message_id=1)
    out = process_message(incoming)
    assert "Активная тема не задана" in out.text


@patch("worker.processor.get_active_node")
def test_topic_with_active(mock_get_active):
    """Команда /topic возвращает активную тему."""
    from shared.graph import Node
    mock_node = Node(id="a1", user_id=1, content="full", summary="План тренировок", source_message_id=None, created_at="", updated_at="")
    mock_get_active.return_value = mock_node
    incoming = IncomingMessage(chat_id=1, user_id=1, text="/topic", message_id=1)
    out = process_message(incoming)
    assert "План тренировок" in out.text
    assert "Активная тема" in out.text


@patch("worker.processor.USE_PLANNER_AUTO", False)
@patch("worker.processor.create_node")
@patch("worker.processor.universal_assistant")
@patch("worker.processor.get_last_nodes")
@patch("worker.processor.extract_theme")
def test_chitchat_skips_node_creation(mock_extract, mock_last_nodes, mock_assistant, mock_create_node):
    """context_type=chitchat: не создаётся узел, только ответ."""
    mock_extract.return_value = {
        "context_type": "chitchat",
        "theme": "привет",
        "key_parts": "",
        "action_type": "new_thought",
        "parent_hint": None,
        "project_switch": False,
        "suggested_role": "universal",
    }
    mock_last_nodes.return_value = []
    mock_assistant.return_value = "Привет!"

    incoming = IncomingMessage(chat_id=1, user_id=1, text="Привет!", message_id=1)
    out = process_message(incoming)

    mock_create_node.assert_not_called()
    assert out.text == "Привет!"


@patch("worker.processor.USE_PLANNER_AUTO", False)
@patch("worker.processor.universal_assistant")
@patch("worker.processor.rag_search")
@patch("worker.processor.add_chunk")
@patch("worker.processor.get_embedding")
@patch("worker.processor.set_active_node")
@patch("worker.processor.create_edge")
@patch("worker.processor.create_node")
@patch("worker.processor.classify_topic")
@patch("worker.processor.get_last_nodes")
@patch("worker.processor.extract_theme")
def test_project_switch_creates_root(
    mock_extract, mock_last_nodes, mock_classify, mock_create_node, mock_create_edge,
    mock_set_active, mock_embedding, mock_add_chunk, mock_rag_search, mock_assistant,
):
    """project_switch=true: parent=None, создаётся корень без ребра."""
    mock_extract.return_value = {
        "context_type": "project",
        "theme": "Новый проект X",
        "key_parts": "",
        "action_type": "new_thought",
        "parent_hint": None,
        "project_switch": True,
        "suggested_role": "universal",
    }
    mock_last_nodes.return_value = [MagicMock(id="old", summary="Старая тема", content="Старая тема")]
    mock_classify.return_value = ("old", "continuation")  # classify вернул бы parent, но project_switch перебивает
    mock_create_node.return_value = "new-node-123"
    mock_embedding.return_value = [0.0] * 1536
    mock_rag_search.return_value = []
    mock_assistant.return_value = "Ок."

    incoming = IncomingMessage(chat_id=1, user_id=1, text="Давай теперь про проект X", message_id=1)
    out = process_message(incoming)

    mock_create_edge.assert_not_called()
    mock_set_active.assert_called_once_with(1, "new-node-123")
