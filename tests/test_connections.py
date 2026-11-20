from fastapi.testclient import TestClient

from safesound import server


def first_notice(ws, limit=5):
    for _ in range(limit):
        message = ws.receive_json()
        if message["type"] == "notice":
            return message
    return None


def test_second_connection_is_warned():
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as first:
        assert first.receive_json()["type"] != "notice"
        with client.websocket_connect("/ws") as second:
            notice = first_notice(second)
            assert notice is not None
            assert "already listening" in notice["message"]
    assert server.live_connections["count"] == 0
