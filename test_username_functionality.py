"""
Test script to verify username functionality in the backend
"""
import os
import sys
import requests
import json

# Test the username availability endpoint
def test_username_availability():
    base_url = "http://localhost:4000"  # Adjust if your backend runs on different port
    
    # Test cases
    test_usernames = [
        "valid-username",
        "my-shop",  # Reserved
        "admin",    # Reserved
        "test-shop-123",
        "ab",       # Too short
        "this-is-a-very-long-username-that-exceeds-thirty-characters",  # Too long
        "invalid@username",  # Invalid characters
    ]
    
    print("Testing username availability endpoint...")
    
    for username in test_usernames:
        try:
            response = requests.get(f"{base_url}/shop-owners/check-username/{username}")
            if response.status_code == 200:
                result = response.json()
                print(f"✓ '{username}': {result['message']} (Available: {result['available']})")
            else:
                print(f"✗ '{username}': Error {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"✗ Connection error for '{username}': {e}")

if __name__ == "__main__":
    test_username_availability()
