from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.websockets.manager import manager
from app.websockets.utils import get_queue_display_data
from typing import Dict, Any
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/queue/{shop_id}")
async def queue_websocket(websocket: WebSocket, shop_id: str, db: Session = Depends(get_db)):
    """WebSocket endpoint for receiving real-time queue updates for a specific shop."""
    try:
        # Get the queue display data for the shop
        queue_data = get_queue_display_data(db, int(shop_id))
        if not queue_data:
            await websocket.close(code=4004, reason="Shop not found")
            return
            
        # Accept the connection
        await manager.connect(websocket, shop_id)
        
        # Send initial queue data
        await websocket.send_json(queue_data)
        
        try:
            # Keep the websocket connection alive and handle disconnections
            while True:
                data = await websocket.receive_text()
                # We're not processing any incoming messages, just keeping the connection alive
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            manager.disconnect(websocket, shop_id)
        
    except Exception as e:
        logger.error(f"WebSocket error for shop {shop_id}: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Server error")
        except:
            pass  # In case the websocket is already closed 