from typing import Dict, List, Optional, Set
from fastapi import WebSocket
import logging
import json
from app import schemas
from pydantic import ValidationError


logger = logging.getLogger(__name__)

# Connection managers for different types of WebSocket connections
class ConnectionManager:
    def __init__(self):
        # Mapping of shop_id -> set of active connections
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, shop_id: int):
        """Connect a client to a specific shop's WebSocket channel"""
        await websocket.accept()
        
        if shop_id not in self.active_connections:
            self.active_connections[shop_id] = set()
            
        self.active_connections[shop_id].add(websocket)
        logger.info(f"Client connected to shop {shop_id}. Total connections: {len(self.active_connections[shop_id])}")
        
    def disconnect(self, websocket: WebSocket, shop_id: int):
        """Disconnect a client from a shop's WebSocket channel"""
        if shop_id in self.active_connections:
            try:
                self.active_connections[shop_id].remove(websocket)
                logger.info(f"Client disconnected from shop {shop_id}. Remaining: {len(self.active_connections[shop_id])}")
                
                # Clean up empty sets
                if len(self.active_connections[shop_id]) == 0:
                    del self.active_connections[shop_id]
            except KeyError:
                logger.warning(f"Failed to remove websocket for shop {shop_id}: connection not found")
                
    async def broadcast_queue_update(self, shop_id: int, queue_items: List[schemas.QueueEntryResponse]):
        """Broadcast queue updates to all clients connected to a shop"""
        if shop_id not in self.active_connections:
            logger.debug(f"No active connections for shop {shop_id}")
            return
            
        message = schemas.QueueUpdateMessage(
            type=schemas.WebSocketMessageType.QUEUE_UPDATE,
            queue_items=queue_items
        )
        
        dead_connections = set()
        
        for connection in self.active_connections[shop_id]:
            try:
                await connection.send_json(message.model_dump())
            except Exception as e:
                logger.error(f"Failed to send message to client: {str(e)}")
                dead_connections.add(connection)
                
        # Remove dead connections
        for dead in dead_connections:
            self.active_connections[shop_id].remove(dead)
            
    async def broadcast_new_entry(self, shop_id: int, queue_item: schemas.QueueEntryResponse):
        """Broadcast new queue entry to all clients connected to a shop"""
        if shop_id not in self.active_connections:
            logger.debug(f"No active connections for shop {shop_id}")
            return
            
        message = schemas.NewEntryMessage(
            type=schemas.WebSocketMessageType.NEW_ENTRY,
            queue_item=queue_item
        )
        
        dead_connections = set()
        
        for connection in self.active_connections[shop_id]:
            try:
                await connection.send_json(message.model_dump())
            except Exception as e:
                logger.error(f"Failed to send message to client: {str(e)}")
                dead_connections.add(connection)
                
        # Remove dead connections
        for dead in dead_connections:
            self.active_connections[shop_id].remove(dead)
            
    async def broadcast_appointment_update(self, shop_id: int, appointments: List[schemas.AppointmentResponse]):
        """Broadcast appointment updates to all clients connected to a shop"""
        if shop_id not in self.active_connections:
            logger.debug(f"No active connections for shop {shop_id}")
            return
            
        message = schemas.AppointmentUpdateMessage(
            type=schemas.WebSocketMessageType.APPOINTMENT_UPDATE,
            appointments=appointments
        )
        
        dead_connections = set()
        
        for connection in self.active_connections[shop_id]:
            try:
                await connection.send_json(message.model_dump())
            except Exception as e:
                logger.error(f"Failed to send message to client: {str(e)}")
                dead_connections.add(connection)
                
        # Remove dead connections
        for dead in dead_connections:
            self.active_connections[shop_id].remove(dead)


# Create separate connection managers for queues and appointments
queue_manager = ConnectionManager()
appointment_manager = ConnectionManager() 