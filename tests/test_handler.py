"""
Tests for WhatsApp inbound handler.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_join_registers_new_supplier():
    """JOIN command should register a new supplier and send welcome."""
    with patch("whatsapp.handler.SessionLocal") as mock_db_class, \
         patch("whatsapp.handler.send_welcome", new_callable=AsyncMock) as mock_send:

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing supplier

        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "JOIN RICE PATIALA")

        mock_send.assert_called_once_with("919876543210", "rice", "patiala")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_help_command():
    """HELP command should send help menu."""
    with patch("whatsapp.handler.SessionLocal") as mock_db_class, \
         patch("whatsapp.handler.send_help_menu", new_callable=AsyncMock) as mock_help:

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "HELP")

        mock_help.assert_called_once_with("919876543210")


@pytest.mark.asyncio
async def test_unknown_command_sends_help():
    """Unknown commands should trigger HELP menu."""
    with patch("whatsapp.handler.SessionLocal") as mock_db_class, \
         patch("whatsapp.handler.send_help_menu", new_callable=AsyncMock) as mock_help:

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "RANDOM STUFF")

        mock_help.assert_called_once()


@pytest.mark.asyncio
async def test_stop_deactivates_supplier():
    """STOP command should set supplier.active = False."""
    with patch("whatsapp.handler.SessionLocal") as mock_db_class:

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_supplier = MagicMock()
        mock_supplier.active = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_supplier

        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "STOP")

        assert mock_supplier.active is False
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_price_command():
    """PRICE command should fetch prices and send them."""
    with patch("whatsapp.handler.SessionLocal") as mock_db_class, \
         patch("whatsapp.handler.fetch_punjab_prices", new_callable=AsyncMock) as mock_prices, \
         patch("whatsapp.handler.send_mandi_prices", new_callable=AsyncMock) as mock_send:

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db

        mock_supplier = MagicMock()
        mock_supplier.categories = "rice,wheat"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_supplier

        mock_prices.return_value = {
            "rice": {"modal": 3200, "change": 50},
            "wheat": {"modal": 2400, "change": -20},
        }

        from whatsapp.handler import handle_inbound
        await handle_inbound("919876543210", "PRICE")

        mock_prices.assert_called_once()
        mock_send.assert_called_once()
