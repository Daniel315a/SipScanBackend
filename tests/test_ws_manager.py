"""Unit tests for _WSManager in routes/receipts.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, patch

# Patch heavy imports before loading the module
_PATCHES = [
    patch("repositories.db.get_session"),
    patch("repositories.db.get_sessionmaker"),
    patch("services.receipt_service.create"),
    patch("services.llm_service.LLMService"),
    patch("services.llm_service.render_template"),
]

for p in _PATCHES:
    p.start()

from routes.receipts import _WSManager  # noqa: E402

for p in _PATCHES:
    p.stop()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ws():
    return AsyncMock()


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_calls_accept():
    """Accepts the WebSocket on connect."""
    manager = _WSManager()
    ws = _ws()
    await manager.connect(ws, "900123456")
    ws.accept.assert_called_once()


@pytest.mark.asyncio
async def test_connect_stores_nit():
    """Associates the NIT with the WebSocket."""
    manager = _WSManager()
    ws = _ws()
    await manager.connect(ws, "900123456")
    assert manager._clients[ws] == "900123456"


@pytest.mark.asyncio
async def test_connect_multiple_clients_different_nits():
    """Each connection stores its own NIT independently."""
    manager = _WSManager()
    ws1, ws2 = _ws(), _ws()
    await manager.connect(ws1, "111")
    await manager.connect(ws2, "222")
    assert manager._clients[ws1] == "111"
    assert manager._clients[ws2] == "222"


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

def test_disconnect_removes_client():
    """Removes the WebSocket from the internal map."""
    manager = _WSManager()
    ws = _ws()
    manager._clients[ws] = "900"
    manager.disconnect(ws)
    assert ws not in manager._clients


def test_disconnect_unknown_client_does_not_raise():
    """Disconnecting an unknown client is a no-op."""
    manager = _WSManager()
    manager.disconnect(_ws())  # should not raise


# ---------------------------------------------------------------------------
# broadcast — routing by NIT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_sends_to_matching_nit():
    """Sends the message only to the client with the matching NIT."""
    manager = _WSManager()
    ws = _ws()
    manager._clients[ws] = "900"
    await manager.broadcast("900", {"event": "test"})
    ws.send_json.assert_called_once_with({"event": "test"})


@pytest.mark.asyncio
async def test_broadcast_does_not_send_to_other_nits():
    """Does not deliver the message to clients with a different NIT."""
    manager = _WSManager()
    ws_a, ws_b = _ws(), _ws()
    manager._clients[ws_a] = "111"
    manager._clients[ws_b] = "222"
    await manager.broadcast("111", {"event": "test"})
    ws_b.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_matching_nit():
    """Delivers to every client sharing the same NIT."""
    manager = _WSManager()
    ws1, ws2, ws3 = _ws(), _ws(), _ws()
    manager._clients[ws1] = "900"
    manager._clients[ws2] = "900"
    manager._clients[ws3] = "999"
    await manager.broadcast("900", {"event": "test"})
    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()
    ws3.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_no_matching_nit_does_nothing():
    """Does nothing when no client is connected for the given NIT."""
    manager = _WSManager()
    ws = _ws()
    manager._clients[ws] = "111"
    await manager.broadcast("999", {"event": "test"})
    ws.send_json.assert_not_called()


# ---------------------------------------------------------------------------
# broadcast — dead-client cleanup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_drops_client_on_send_error():
    """Removes a client from the map when send_json raises."""
    manager = _WSManager()
    ws = _ws()
    ws.send_json.side_effect = Exception("connection lost")
    manager._clients[ws] = "900"
    await manager.broadcast("900", {"event": "test"})
    assert ws not in manager._clients


@pytest.mark.asyncio
async def test_broadcast_continues_after_failed_client():
    """Delivers to healthy clients even when one fails."""
    manager = _WSManager()
    bad_ws, good_ws = _ws(), _ws()
    bad_ws.send_json.side_effect = Exception("disconnected")
    manager._clients[bad_ws] = "900"
    manager._clients[good_ws] = "900"
    await manager.broadcast("900", {"event": "test"})
    good_ws.send_json.assert_called_once()
    assert bad_ws not in manager._clients
