# tests/test_main.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_root_endpoint():
    """Test if your main endpoint works - adjust this based on your actual endpoints"""
    # If you have a root endpoint, test it
    # response = client.get("/")
    # assert response.status_code == 200
    
    # For now, just test that the app initializes
    assert app is not None