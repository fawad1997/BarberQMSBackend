from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
from app.database import get_db
from app import models, schemas
from app.core.auth import get_current_user
from app.schemas import (
    WorkScheduleCreate, WorkScheduleResponse, WorkScheduleBase,
    ScheduleBreakCreate, ScheduleBreakResponse,
    EmployeeScheduleCreate, EmployeeScheduleResponse,
    ScheduleOverrideCreate, ScheduleOverrideResponse
)

router = APIRouter(
    prefix="/schedules",
    tags=["schedules"]
)

# Work Schedule Endpoints
@router.post("/work-schedules", response_model=WorkScheduleResponse)
async def create_work_schedule(
    schedule: WorkScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create a new work schedule for a shop"""
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == schedule.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this shop")
    
    db_schedule = models.WorkSchedule(**schedule.model_dump(exclude={'breaks'}))
    db.add(db_schedule)
    db.flush()  # Get the ID without committing
    
    # Create breaks if provided
    if schedule.breaks:
        for break_data in schedule.breaks:
            db_break = models.ScheduleBreak(
                work_schedule_id=db_schedule.id,
                **break_data.model_dump()
            )
            db.add(db_break)
    
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

@router.get("/work-schedules/{shop_id}", response_model=List[WorkScheduleResponse])
async def get_shop_work_schedules(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all work schedules for a shop"""
    # Verify user has permission to view the shop
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop or (shop.owner_id != current_user.id and current_user.role != "ADMIN"):
        raise HTTPException(status_code=403, detail="Not authorized to view this shop's schedules")
    
    schedules = db.query(models.WorkSchedule).filter(
        models.WorkSchedule.shop_id == shop_id
    ).all()
    return schedules

@router.put("/work-schedules/{schedule_id}", response_model=WorkScheduleResponse)
async def update_work_schedule(
    schedule_id: int,
    schedule: WorkScheduleBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update a work schedule"""
    db_schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Work schedule not found")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == db_schedule.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this schedule")
    
    for key, value in schedule.model_dump(exclude_unset=True).items():
        setattr(db_schedule, key, value)
    
    db.commit()
    db.refresh(db_schedule)
    return db_schedule

@router.delete("/work-schedules/{schedule_id}")
async def delete_work_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Delete a work schedule"""
    db_schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Work schedule not found")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == db_schedule.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this schedule")
    
    db.delete(db_schedule)
    db.commit()
    return {"message": "Work schedule deleted successfully"}

# Schedule Break Endpoints
@router.post("/work-schedules/{schedule_id}/breaks", response_model=ScheduleBreakResponse)
async def create_schedule_break(
    schedule_id: int,
    break_data: ScheduleBreakCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Add a break to a work schedule"""
    db_schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Work schedule not found")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == db_schedule.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this schedule")
    
    db_break = models.ScheduleBreak(
        work_schedule_id=schedule_id,
        **break_data.model_dump()
    )
    db.add(db_break)
    db.commit()
    db.refresh(db_break)
    return db_break

@router.get("/work-schedules/{schedule_id}/breaks", response_model=List[ScheduleBreakResponse])
async def get_schedule_breaks(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all breaks for a work schedule"""
    db_schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == schedule_id).first()
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Work schedule not found")
    
    # Verify user has permission to view the shop
    shop = db.query(models.Shop).filter(models.Shop.id == db_schedule.shop_id).first()
    if not shop or (shop.owner_id != current_user.id and current_user.role != "ADMIN"):
        raise HTTPException(status_code=403, detail="Not authorized to view this schedule")
    
    breaks = db.query(models.ScheduleBreak).filter(
        models.ScheduleBreak.work_schedule_id == schedule_id
    ).all()
    return breaks

@router.put("/breaks/{break_id}", response_model=ScheduleBreakResponse)
async def update_schedule_break(
    break_id: int,
    break_data: ScheduleBreakCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update a schedule break"""
    db_break = db.query(models.ScheduleBreak).filter(models.ScheduleBreak.id == break_id).first()
    if not db_break:
        raise HTTPException(status_code=404, detail="Schedule break not found")
    
    # Verify user has permission to manage the shop
    schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == db_break.work_schedule_id).first()
    shop = db.query(models.Shop).filter(models.Shop.id == schedule.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this break")
    
    for key, value in break_data.model_dump(exclude_unset=True).items():
        setattr(db_break, key, value)
    
    db.commit()
    db.refresh(db_break)
    return db_break

@router.delete("/breaks/{break_id}")
async def delete_schedule_break(
    break_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Delete a schedule break"""
    db_break = db.query(models.ScheduleBreak).filter(models.ScheduleBreak.id == break_id).first()
    if not db_break:
        raise HTTPException(status_code=404, detail="Schedule break not found")
    
    # Verify user has permission to manage the shop
    schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == db_break.work_schedule_id).first()
    shop = db.query(models.Shop).filter(models.Shop.id == schedule.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this break")
    
    db.delete(db_break)
    db.commit()
    return {"message": "Schedule break deleted successfully"}

# Employee Schedule Endpoints
@router.post("/employee-schedules", response_model=EmployeeScheduleResponse)
async def assign_schedule_to_employee(
    assignment: EmployeeScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Assign a work schedule to an employee (barber)"""
    # Verify the barber exists and belongs to the shop
    barber = db.query(models.Barber).filter(models.Barber.id == assignment.employee_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Verify the work schedule exists and belongs to the same shop
    schedule = db.query(models.WorkSchedule).filter(models.WorkSchedule.id == assignment.work_schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Work schedule not found")
    
    if barber.shop_id != schedule.shop_id:
        raise HTTPException(status_code=400, detail="Barber and schedule must belong to the same shop")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == barber.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this shop's schedules")
    
    # Check if assignment already exists
    existing = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == assignment.employee_id,
        models.EmployeeSchedule.work_schedule_id == assignment.work_schedule_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Schedule already assigned to this employee")
    
    db_assignment = models.EmployeeSchedule(**assignment.model_dump())
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return db_assignment

@router.get("/employee-schedules/{employee_id}", response_model=List[EmployeeScheduleResponse])
async def get_employee_schedules(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get all schedules assigned to an employee"""
    barber = db.query(models.Barber).filter(models.Barber.id == employee_id).first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    
    # Verify user has permission to view the shop
    shop = db.query(models.Shop).filter(models.Shop.id == barber.shop_id).first()
    if not shop or (shop.owner_id != current_user.id and current_user.role != "ADMIN"):
        raise HTTPException(status_code=403, detail="Not authorized to view this employee's schedules")
    
    assignments = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == employee_id
    ).all()
    return assignments

@router.delete("/employee-schedules/{employee_id}/{schedule_id}")
async def remove_employee_schedule(
    employee_id: int,
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Remove a schedule assignment from an employee"""
    assignment = db.query(models.EmployeeSchedule).filter(
        models.EmployeeSchedule.employee_id == employee_id,
        models.EmployeeSchedule.work_schedule_id == schedule_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Schedule assignment not found")
    
    # Verify user has permission to manage the shop
    barber = db.query(models.Barber).filter(models.Barber.id == employee_id).first()
    shop = db.query(models.Shop).filter(models.Shop.id == barber.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this employee's schedules")
    
    db.delete(assignment)
    db.commit()
    return {"message": "Schedule assignment removed successfully"}

# Schedule Override Endpoints
@router.post("/overrides", response_model=ScheduleOverrideResponse)
async def create_schedule_override(
    override: ScheduleOverrideCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create a schedule override"""
    # Verify the barber exists if specified
    if override.barber_id:
        barber = db.query(models.Barber).filter(models.Barber.id == override.barber_id).first()
        if not barber:
            raise HTTPException(status_code=404, detail="Barber not found")
        if barber.shop_id != override.shop_id:
            raise HTTPException(status_code=400, detail="Barber must belong to the specified shop")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == override.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this shop's schedules")
    
    db_override = models.ScheduleOverride(**override.model_dump())
    db.add(db_override)
    db.commit()
    db.refresh(db_override)
    return db_override

@router.get("/overrides", response_model=List[ScheduleOverrideResponse])
async def get_schedule_overrides(
    shop_id: int,
    barber_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get schedule overrides with optional filters"""
    # Verify user has permission to view the shop
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop or (shop.owner_id != current_user.id and current_user.role != "ADMIN"):
        raise HTTPException(status_code=403, detail="Not authorized to view this shop's overrides")
    
    query = db.query(models.ScheduleOverride).filter(models.ScheduleOverride.shop_id == shop_id)
    
    if barber_id:
        query = query.filter(models.ScheduleOverride.barber_id == barber_id)
    if start_date:
        query = query.filter(models.ScheduleOverride.start_date >= start_date)
    if end_date:
        query = query.filter(models.ScheduleOverride.end_date <= end_date)
    
    overrides = query.all()
    return overrides

@router.put("/overrides/{override_id}", response_model=ScheduleOverrideResponse)
async def update_schedule_override(
    override_id: int,
    override: ScheduleOverrideCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update a schedule override"""
    db_override = db.query(models.ScheduleOverride).filter(models.ScheduleOverride.id == override_id).first()
    if not db_override:
        raise HTTPException(status_code=404, detail="Schedule override not found")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == db_override.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this override")
    
    for key, value in override.model_dump(exclude_unset=True).items():
        setattr(db_override, key, value)
    
    db.commit()
    db.refresh(db_override)
    return db_override

@router.delete("/overrides/{override_id}")
async def delete_schedule_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Delete a schedule override"""
    db_override = db.query(models.ScheduleOverride).filter(models.ScheduleOverride.id == override_id).first()
    if not db_override:
        raise HTTPException(status_code=404, detail="Schedule override not found")
    
    # Verify user has permission to manage the shop
    shop = db.query(models.Shop).filter(models.Shop.id == db_override.shop_id).first()
    if not shop or shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this override")
    
    db.delete(db_override)
    db.commit()
    return {"message": "Schedule override deleted successfully"} 