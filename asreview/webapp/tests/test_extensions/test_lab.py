import signal
from unittest.mock import Mock

import pytest

from asreview.webapp._entry_points import lab
from asreview.webapp._task_manager import task_manager


@pytest.fixture
def mock_env_lab_testing(monkeypatch):
    monkeypatch.setenv("ASREVIEW_LAB_TESTING", "true")


def test_authentication_parameter(mock_env_lab_testing):
    app = lab.lab_entry_point(["--enable-auth"])
    assert app.config.get("AUTHENTICATION")


def test_without_authentication_parameter(mock_env_lab_testing):
    app = lab.lab_entry_point([])
    assert app.config.get("AUTHENTICATION") is False


def test_http_shutdown_stops_workers_before_closing_sockets(monkeypatch):
    calls = []
    server = Mock()
    socket_map = {1: Mock()}
    server.task_dispatcher.shutdown.side_effect = lambda **kwargs: calls.append(
        "workers"
    )
    monkeypatch.setattr(
        lab.wasyncore, "close_all", lambda sockets: calls.append("sockets")
    )
    lab._close_http_server(server, socket_map)
    assert calls == ["workers", "sockets"]
    server.task_dispatcher.shutdown.assert_called_once_with(timeout=30)


def test_http_loop_stops_before_socket_cleanup(monkeypatch):
    server = Mock()
    socket_map = {1: Mock()}
    stopping = False

    def poll(**kwargs):
        nonlocal stopping
        assert kwargs["map"] is socket_map
        assert kwargs["count"] == 1
        stopping = True

    loop = Mock(side_effect=poll)
    monkeypatch.setattr(lab.wasyncore, "loop", loop)
    lab._serve_until_shutdown(server, socket_map, lambda: stopping)
    loop.assert_called_once()
    server.close.assert_not_called()


@pytest.mark.parametrize("managed", [False, True])
def test_task_manager_defers_session_cleanup_until_loop_exit(monkeypatch, managed):
    # The signal arrives during accept, immediately before the timeout handler.
    # The session must survive the signal and no more queue work should run.
    from threading import Event

    manager = task_manager.TaskManager.__new__(task_manager.TaskManager)
    manager.host = "localhost"
    manager.port = 5101
    manager.server_socket = Mock()
    manager.session = Mock()
    manager.client_thread = None
    manager.client_conn = None
    manager._client_connections = []
    manager._bind_server_socket = Mock(return_value=True)
    manager._process_buffer = Mock()
    manager.pop_waiting_queue = Mock()
    session = manager.session
    shutdown_event = Event() if managed else None
    handlers = {}

    def register(sig, handler):
        previous = handlers.get(sig, signal.SIG_DFL)
        handlers[sig] = handler
        return previous

    monkeypatch.setattr(task_manager.signal, "signal", register)

    def interrupt_accept():
        handlers[signal.SIGINT](signal.SIGINT, None)
        assert manager.session is session
        session.close.assert_not_called()
        if managed:
            shutdown_event.set()
        raise TimeoutError

    manager.server_socket.accept.side_effect = interrupt_accept
    manager.start_manager(mp_shutdown_event=shutdown_event)
    manager._process_buffer.assert_not_called()
    manager.pop_waiting_queue.assert_not_called()
    session.close.assert_called_once()
    assert manager.session is None
    assert manager.server_socket is None
