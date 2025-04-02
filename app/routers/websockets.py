from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.websockets import queue_manager, appointment_manager
import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app import models, schemas
from app.models import QueueStatus, AppointmentStatus

logger = logging.getLogger(__name__)

# Create router without prefix since WebSocket routes need full path
router = APIRouter(tags=["WebSockets"])


async def get_queue_data(shop_id: int, db: Session) -> List[schemas.QueueEntryResponse]:
    """Helper function to get all active queue entries for a shop"""
    # Verify shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        logger.error(f"Shop with ID {shop_id} not found")
        return []

    # Get active queue entries with all required relationships
    entries = (
        db.query(models.QueueEntry)
        .options(
            joinedload(models.QueueEntry.barber).joinedload(models.Barber.user),
            joinedload(models.QueueEntry.service)
        )
        .filter(
            models.QueueEntry.shop_id == shop_id,
            models.QueueEntry.status.in_([
                QueueStatus.CHECKED_IN, 
                QueueStatus.ARRIVED,
                QueueStatus.IN_SERVICE
            ])
        )
        .order_by(models.QueueEntry.position_in_queue)
        .all()
    )
    
    # Process each entry to ensure barber full_name is available if barber exists
    for entry in entries:
        if entry.barber and entry.barber.user:
            # Set the full_name attribute on the barber object
            entry.barber.full_name = entry.barber.user.full_name
    
    return entries


async def get_appointment_data(shop_id: int, db: Session, status: Optional[AppointmentStatus] = None) -> List[schemas.AppointmentResponse]:
    """Helper function to get appointments for a shop with optional status filter"""
    # Verify shop exists
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        logger.error(f"Shop with ID {shop_id} not found")
        return []

    # Build query with efficient loading of related entities
    query = (
        db.query(models.Appointment)
        .options(
            joinedload(models.Appointment.barber),
            joinedload(models.Appointment.service),
            joinedload(models.Appointment.user)
        )
        .filter(models.Appointment.shop_id == shop_id)
    )
    
    # Apply status filter if provided
    if status:
        query = query.filter(models.Appointment.status == status)
    
    # Get appointments ordered by time
    appointments = query.order_by(models.Appointment.appointment_time).all()
    
    return appointments


@router.websocket("/ws/queue/{shop_id}/")
async def websocket_queue_endpoint(websocket: WebSocket, shop_id: int, db: Session = Depends(get_db)):
    """WebSocket endpoint for real-time queue updates"""
    try:
        # Convert path parameter to integer
        shop_id_int = int(shop_id)
        
        # Accept the connection
        await queue_manager.connect(websocket, shop_id_int)
        
        try:
            # Initial data load - send current queue state
            queue_data = await get_queue_data(shop_id_int, db)
            await queue_manager.broadcast_queue_update(shop_id_int, queue_data)
            
            # Listen for messages - currently just keep-alive pings
            while True:
                data = await websocket.receive_text()
                try:
                    # We could process client messages here if needed
                    pass
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {str(e)}")
        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected from queue for shop {shop_id_int}")
        finally:
            # Always ensure we clean up the connection
            queue_manager.disconnect(websocket, shop_id_int)
            
    except ValueError:
        logger.error(f"Invalid shop_id: {shop_id}")
        await websocket.close(code=1008)  # Policy violation
    except Exception as e:
        logger.error(f"Error in queue WebSocket: {str(e)}")
        try:
            await websocket.close(code=1011)  # Internal error
        except:
            pass


@router.websocket("/ws/appointments/{shop_id}/")
async def websocket_appointments_endpoint(websocket: WebSocket, shop_id: int, db: Session = Depends(get_db)):
    """WebSocket endpoint for real-time appointment updates"""
    try:
        # Convert path parameter to integer
        shop_id_int = int(shop_id)
        
        # Accept the connection
        await appointment_manager.connect(websocket, shop_id_int)
        
        try:
            # Initial data load - send current appointments
            appointment_data = await get_appointment_data(shop_id_int, db, AppointmentStatus.SCHEDULED)
            await appointment_manager.broadcast_appointment_update(shop_id_int, appointment_data)
            
            # Listen for messages - currently just keep-alive pings
            while True:
                data = await websocket.receive_text()
                try:
                    # We could process client messages here if needed
                    pass
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {str(e)}")
        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected from appointments for shop {shop_id_int}")
        finally:
            # Always ensure we clean up the connection
            appointment_manager.disconnect(websocket, shop_id_int)
            
    except ValueError:
        logger.error(f"Invalid shop_id: {shop_id}")
        await websocket.close(code=1008)  # Policy violation
    except Exception as e:
        logger.error(f"Error in appointments WebSocket: {str(e)}")
        try:
            await websocket.close(code=1011)  # Internal error
        except:
            pass 