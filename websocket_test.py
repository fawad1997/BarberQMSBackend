import asyncio
import websockets
import json
import sys

async def test_websocket(shop_id):
    uri = f"ws://localhost:8000/ws/queue/{shop_id}"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected successfully!")
            
            # Receive initial queue data
            initial_data = await websocket.recv()
            print(f"\nInitial queue data: {json.dumps(json.loads(initial_data), indent=2)}")
            
            # Keep connection alive and listen for updates
            print("\nListening for queue updates. Press Ctrl+C to exit...")
            while True:
                try:
                    data = await websocket.recv()
                    print(f"\nReceived update at {json.loads(data).get('current_time')}:")
                    print(json.dumps(json.loads(data), indent=2))
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server")
                    break
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python websocket_test.py <shop_id>")
        sys.exit(1)
        
    shop_id = sys.argv[1]
    asyncio.run(test_websocket(shop_id)) 