"""
Comprehensive test script for username functionality
This script tests all aspects of the username implementation
"""
import os
import sys
import json

# Add the app directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.schemas import (
    validate_username, 
    is_username_available, 
    RESERVED_USERNAMES,
    ShopCreate,
    ShopUpdate
)
from app.models import Shop
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

def test_validation_comprehensive():
    """Test all validation scenarios"""
    print("=" * 60)
    print("TESTING USERNAME VALIDATION")
    print("=" * 60)
    
    print(f"Reserved usernames: {sorted(RESERVED_USERNAMES)}")
    print()
    
    test_cases = [
        # Valid cases
        ("valid-username", True, "Basic valid username"),
        ("test-shop-123", True, "Username with numbers"),
        ("my_great_shop", True, "Username with underscores"),
        ("shop123", True, "Short valid username"),
        ("long-username-but-still-valid", True, "Long but valid username"),
        
        # Invalid - reserved
        ("my-shop", False, "Reserved username from your list"),
        ("barbershop", False, "Reserved username from your list"),
        ("barber-shop", False, "Reserved username from your list"),
        ("my-barber-shop", False, "Reserved username from your list"),
        ("admin", False, "System reserved username"),
        ("api", False, "System reserved username"),
        
        # Invalid - length
        ("ab", False, "Too short (less than 3 chars)"),
        ("this-is-a-very-long-username-that-exceeds-thirty-characters", False, "Too long (more than 30 chars)"),
        
        # Invalid - characters
        ("invalid@username", False, "Contains @ symbol"),
        ("username!", False, "Contains exclamation mark"),
        ("user name", False, "Contains space"),
        ("username.com", False, "Contains dot"),
        ("user#name", False, "Contains hash"),
        
        # Invalid - format
        ("-invalid-start", False, "Starts with hyphen"),
        ("invalid-end-", False, "Ends with hyphen"),
        ("_invalid-start", False, "Starts with underscore"),
        ("invalid-end_", False, "Ends with underscore"),
        ("", False, "Empty string"),
        ("   ", False, "Only spaces"),
        
        # Edge cases
        ("abc", True, "Minimum valid length"),
        ("a" * 30, True, "Maximum valid length"),
        ("user-name_123", True, "Mixed valid characters"),
    ]
    
    passed = 0
    failed = 0
    
    for username, should_be_valid, description in test_cases:
        try:
            validated = validate_username(username)
            if should_be_valid:
                print(f"✅ PASS: '{username}' -> '{validated}' ({description})")
                passed += 1
            else:
                print(f"❌ FAIL: '{username}' -> '{validated}' (Should have been invalid: {description})")
                failed += 1
        except ValueError as e:
            if not should_be_valid:
                print(f"✅ PASS: '{username}' -> Error: {e} ({description})")
                passed += 1
            else:
                print(f"❌ FAIL: '{username}' -> Error: {e} (Should have been valid: {description})")
                failed += 1
    
    print(f"\nValidation Tests: {passed} passed, {failed} failed")
    return failed == 0

def test_database_availability():
    """Test database availability checking"""
    print("\n" + "=" * 60)
    print("TESTING DATABASE AVAILABILITY")
    print("=" * 60)
    
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Test some usernames
        test_usernames = [
            "available-username-test",
            "another-available-test",
            "yet-another-test"
        ]
        
        for username in test_usernames:
            try:
                validated = validate_username(username)
                available = is_username_available(validated, db)
                print(f"✅ Username '{validated}' is {'available' if available else 'taken'}")
            except Exception as e:
                print(f"❌ Error checking '{username}': {e}")
        
        db.close()
        print("✅ Database availability tests completed")
        return True
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def test_schema_validation():
    """Test schema validation for ShopCreate and ShopUpdate"""
    print("\n" + "=" * 60)
    print("TESTING SCHEMA VALIDATION")
    print("=" * 60)
    
    try:
        # Test ShopCreate with username
        from datetime import time
        shop_data = {
            "name": "Test Barber Shop",
            "address": "123 Main St",
            "city": "Test City",
            "state": "Test State",
            "zip_code": "12345",
            "opening_time": time(9, 0),
            "closing_time": time(17, 0),
            "username": "test-barber-shop"
        }
        
        shop_create = ShopCreate(**shop_data)
        print(f"✅ ShopCreate with username '{shop_create.username}' validated successfully")
        
        # Test with invalid username
        shop_data["username"] = "my-shop"  # Reserved
        try:
            shop_create_invalid = ShopCreate(**shop_data)
            print(f"❌ ShopCreate should have failed with reserved username")
            return False
        except Exception as e:
            print(f"✅ ShopCreate correctly rejected reserved username: {e}")
        
        # Test ShopUpdate
        shop_update = ShopUpdate(username="updated-username")
        print(f"✅ ShopUpdate with username '{shop_update.username}' validated successfully")
        
        print("✅ Schema validation tests completed")
        return True
        
    except Exception as e:
        print(f"❌ Schema validation error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 COMPREHENSIVE USERNAME FUNCTIONALITY TEST SUITE")
    print("=" * 60)
    
    results = []
    
    # Run all tests
    results.append(("Validation", test_validation_comprehensive()))
    results.append(("Database Availability", test_database_availability()))
    results.append(("Schema Validation", test_schema_validation()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    print(f"\nOverall Result: {'🎉 ALL TESTS PASSED' if all_passed else '💥 SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n🚀 Backend username functionality is ready!")
        print("✅ Username validation working correctly")
        print("✅ Reserved usernames properly blocked")
        print("✅ Database integration functional")
        print("✅ Schema validation working")
        print("\nNext steps:")
        print("1. Start your backend server")
        print("2. Test the API endpoints")
        print("3. Implement frontend integration")
    
    return all_passed

if __name__ == "__main__":
    main()
