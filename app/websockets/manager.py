from fastapi import WebSocket
from typing import Dict, List, Set, Any
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Dictionary to store active connections by shop_id
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Keep track of which shops have active connections
        self.active_shops: Set[str] = set()
        
    async def connect(self, websocket: WebSocket, shop_id: str):
        """Connect a new client to a shop's queue updates"""
        await websocket.accept()
        if shop_id not in self.active_connections:
            self.active_connections[shop_id] = []
        self.active_connections[shop_id].append(websocket)
        self.active_shops.add(shop_id)
        logger.info(f"Client connected to shop {shop_id}. Total connections: {len(self.active_connections[shop_id])}")
        
    def disconnect(self, websocket: WebSocket, shop_id: str):
        """Disconnect a client from a shop's queue updates"""
        if shop_id in self.active_connections:
            if websocket in self.active_connections[shop_id]:
                self.active_connections[shop_id].remove(websocket)
                logger.info(f"Client disconnected from shop {shop_id}. Remaining connections: {len(self.active_connections[shop_id])}")
            
            # Clean up empty lists
            if len(self.active_connections[shop_id]) == 0:
                del self.active_connections[shop_id]
                self.active_shops.remove(shop_id)
    
    async def broadcast_to_shop(self, shop_id: str, data: Any):
        """Send data to all connected clients for a specific shop"""
        if shop_id in self.active_connections:
            disconnected_websockets = []
            for websocket in self.active_connections[shop_id]:
                try:
                    await websocket.send_json(data)
                except Exception as e:
                    logger.error(f"Error sending data to client: {str(e)}")
                    disconnected_websockets.append(websocket)
            
            # Clean up any disconnected websockets
            for websocket in disconnected_websockets:
                self.disconnect(websocket, shop_id)
    
    def get_shop_connection_count(self, shop_id: str) -> int:
        """Get the number of connections for a specific shop"""
        if shop_id in self.active_connections:
            return len(self.active_connections[shop_id])
        return 0
    
    def get_active_shops(self) -> List[str]:
        """Get a list of all shop IDs with active connections"""
        return list(self.active_shops)

# Create a global instance of the connection manager
manager = ConnectionManager() 