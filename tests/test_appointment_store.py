from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from orchestrator.services.appointment_store import CalendarRef, get_calendar_ref

TZ = ZoneInfo("Asia/Kolkata")


def _pool_mock(fetchrow_return) -> MagicMock:
    """Return a pool mock whose acquire() works as an async context manager."""
    fake_conn = AsyncMock()
    fake_conn.fetchrow = AsyncMock(return_value=fetchrow_return)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


@pytest.mark.asyncio
async def test_get_calendar_ref_no_pool_returns_none():
    with patch("orchestrator.services.appointment_store.get_pool", return_value=None):
        assert await get_calendar_ref("call-1") is None


@pytest.mark.asyncio
async def test_get_calendar_ref_no_row_returns_none():
    pool = _pool_mock(None)
    with patch("orchestrator.services.appointment_store.get_pool", return_value=pool):
        assert await get_calendar_ref("call-1") is None


@pytest.mark.asyncio
async def test_get_calendar_ref_returns_stored_reference():
    end = datetime(2026, 7, 9, 14, 15, tzinfo=TZ)
    row = {
        "calendar_provider": "cal_com",
        "calendar_event_id": "999",
        "calendar_event_url": "https://cal.com/booking/abc123",
        "end_time": end,
    }
    pool = _pool_mock(row)
    with patch("orchestrator.services.appointment_store.get_pool", return_value=pool):
        ref = await get_calendar_ref("call-1")

    assert ref == CalendarRef(
        provider="cal_com",
        event_id="999",
        event_url="https://cal.com/booking/abc123",
        end_time=end,
    )
