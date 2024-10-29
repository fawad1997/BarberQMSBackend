# main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routers import (
    auth,
    users,
    shop_owners,
    barbers,
    admin,
    appointments,
    queue,
    feedback,
    unregistered_users
)

app = FastAPI(title="Barbershop Queue System API")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(shop_owners.router)
app.include_router(barbers.router)
app.include_router(admin.router)
app.include_router(appointments.router)
app.include_router(queue.router)
app.include_router(feedback.router)
app.include_router(unregistered_users.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Barbershop Queue System API"}

