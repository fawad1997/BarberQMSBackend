import asyncio
import logging
from datetime import datetime
from app.websockets.manager import manager
from app.websockets.utils import get_queue_display_data
from app.database import SessionLocal
import traceback

logger = logging.getLogger(__name__)

# Queue refresh interval in seconds
QUEUE_REFRESH_INTERVAL = 30

async def periodic_queue_refresh():
    """Background task to periodically refresh queue data for all shops with active connections"""
    while True:
        try:
            # Get a database session
            db = SessionLocal()
            
            # For each shop with active connections
            for shop_id in manager.get_active_shops():
                try:
                    shop_id_int = int(shop_id)
                    queue_data = get_queue_display_data(db, shop_id_int)
                    if queue_data:
                        await manager.broadcast_to_shop(shop_id, queue_data)
                        logger.debug(f"Refreshed queue data for shop {shop_id} with {manager.get_shop_connection_count(shop_id)} clients")
                except Exception as e:
                    logger.error(f"Error updating queue for shop {shop_id}: {str(e)}")
                    logger.error(traceback.format_exc())
            
            # Close the database session
            db.close()
        except Exception as e:
            logger.error(f"Error in periodic queue refresh: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Wait for the next refresh interval
        await asyncio.sleep(QUEUE_REFRESH_INTERVAL) 