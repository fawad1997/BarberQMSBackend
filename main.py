# main.py
from fastapi import FastAPI

app = FastAPI(title="Barbershop Queue System API")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Barbershop Queue System API"}
