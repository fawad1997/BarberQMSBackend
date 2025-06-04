"""
Direct test of username validation functions
"""
import os
import sys

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app'))

from app.schemas import validate_username, RESERVED_USERNAMES

def test_username_validation():
    """Test the username validation function directly"""
    print("Testing username validation function...")
    print(f"Reserved usernames: {RESERVED_USERNAMES}")
    print()
    
    test_cases = [
        # Valid usernames
        ("valid-username", True),
        ("test-shop-123", True),
        ("my_great_shop", True),
        ("shop123", True),
        
        # Invalid - reserved
        ("my-shop", False),
        ("barbershop", False),
        ("barber-shop", False),
        ("my-barber-shop", False),
        ("admin", False),
        
        # Invalid - format issues
        ("ab", False),  # Too short
        ("this-is-a-very-long-username-that-exceeds-thirty-characters", False),  # Too long
        ("invalid@username", False),  # Invalid characters
        ("username!", False),  # Invalid characters
        ("-invalid-start", False),  # Starts with hyphen
        ("invalid-end-", False),  # Ends with hyphen
        ("_invalid-start", False),  # Starts with underscore
        ("invalid-end_", False),  # Ends with underscore
        ("", False),  # Empty
    ]
    
    for username, should_be_valid in test_cases:
        try:
            validated = validate_username(username)
            if should_be_valid:
                print(f"✓ '{username}' -> '{validated}' (Valid as expected)")
            else:
                print(f"✗ '{username}' -> '{validated}' (Should have been invalid!)")
        except ValueError as e:
            if not should_be_valid:
                print(f"✓ '{username}' -> Error: {e} (Invalid as expected)")
            else:
                print(f"✗ '{username}' -> Error: {e} (Should have been valid!)")

if __name__ == "__main__":
    test_username_validation()
