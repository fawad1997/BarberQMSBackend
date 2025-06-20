# main.py
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from app.routers import (
    auth,
    users,
    business_owners,
    employees,
    admin,
    appointments,
    queue,
    feedback,
    unregistered_users,
    sso_routes,
    public,
    shop_owners
)
from app.websockets.router import router as websocket_router  # Import the router object, not the module
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db, engine
import uvicorn
from dotenv import load_dotenv
import os
import logging
import asyncio
from fastapi.responses import FileResponse
from app import models

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Barbershop Queue System API",
    description="API for the Barbershop Queue System",
    version="1.0.0",
    # Configure FastAPI to not redirect trailing slashes
    # This means /shops and /shops/ will be treated as separate routes
    # and won't cause automatic redirects
    redirect_slashes=False
)

load_dotenv()

# Create a list of allowed origins
origins = [
    "http://localhost:8080",
    "http://localhost:8000",
    "http://localhost:3000",  # Add Next.js development server
    "https://walkinonline.com",
    "https://www.walkinonline.com",
    "https://walkinonline.app",
    "https://www.walkinonline.app",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:3000",
    "*"
]

# Update the CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Add middleware to handle WebSocket CORS
@app.middleware("http")
async def process_ws_cors(request: Request, call_next):
    """Middleware to handle WebSocket CORS headers"""
    # Check if it's a WebSocket upgrade request
    if request.headers.get("upgrade", "").lower() == "websocket":
        logger.debug(f"WebSocket upgrade request to: {request.url.path}")
        
        # Process the request
        response = await call_next(request)
        
        # Set required CORS headers for WebSockets
        if "*" in origins:
            # If wildcard is allowed, use the Origin header or fall back to *
            response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
        elif request.headers.get("origin") in origins:
            # If the origin is in our allowed list, echo it back
            response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin")
            
        # Allow credentials (important for authenticated WebSockets)
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
        
    return await call_next(request)

# Start the queue refresh background task
@app.on_event("startup")
async def start_queue_refresh_task():
    """Start the background task for queue refreshes on startup"""
    from app.websockets.tasks import periodic_queue_refresh
    asyncio.create_task(periodic_queue_refresh())
    logger.info("Queue refresh background task started")

# database initialization
@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized")
    logger.info(f"WebSocket routes available at: {[route.path for route in app.routes if str(route.path).startswith('/ws/')]}")
    models.Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth.router)
app.include_router(sso_routes.router)
app.include_router(users.router)
app.include_router(business_owners.router)
app.include_router(employees.router)
app.include_router(admin.router)
app.include_router(appointments.router)
app.include_router(queue.router)
app.include_router(feedback.router)
app.include_router(unregistered_users.router)
app.include_router(shop_owners.router)  # Add the shop owners router
app.include_router(public.router)
app.include_router(websocket_router)  # Include WebSocket router

@app.get("/")
def read_root():
    return {"message": "Welcome to the Barbershop Queue System API"}

@app.get("/favicon.ico")
async def favicon():
    """Serve the favicon.ico file"""
    favicon_path = os.path.join("static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    else:
        # Return a 404 if favicon not found
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Favicon not found")



if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, reload=True)
