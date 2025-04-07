# WebSocket Implementation for Barber Shop Queue System

This module implements real-time queue updates for barber shop customers using WebSockets.

## Overview

The WebSocket implementation provides real-time updates of the queue status to all connected clients. Whenever the queue changes, all connected clients receive the updated queue information.

## Key Components

### Connection Manager

`app/websockets/manager.py` contains the `ConnectionManager` class that manages WebSocket connections:

- Tracks active connections by shop ID
- Handles client connection/disconnection
- Broadcasts updates to connected clients
- Manages connection state

### WebSocket Router

`app/websockets/router.py` contains the WebSocket endpoint:

- `/ws/queue/{shop_id}` - Connect to get real-time updates for a specific shop's queue

### Queue Data Utilities

`app/websockets/utils.py` contains utility functions:

- `get_queue_display_data()` - Gets the current queue data for a shop
- `broadcast_queue_update()` - Broadcasts queue updates to all connected clients

### Background Tasks

`app/websockets/tasks.py` contains background tasks:

- `periodic_queue_refresh()` - Periodically refreshes queue data for all shops with active connections

## Example Usage

### Frontend Connection

```javascript
// Connect to WebSocket server
const ws = new WebSocket(`ws://your-api-domain/ws/queue/${shopId}`);

// Handle connection open
ws.onopen = () => {
  console.log('Connected to queue updates');
};

// Handle incoming messages
ws.onmessage = (event) => {
  const queueData = JSON.parse(event.data);
  // Update UI with queue data
  updateQueueDisplay(queueData);
};

// Handle errors
ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

// Handle connection close
ws.onclose = () => {
  console.log('Disconnected from queue updates');
};
```

### Testing WebSocket Connection

You can use the provided test script to verify WebSocket functionality:

```bash
python websocket_test.py <shop_id>
```

## Updates Broadcast Timing

Queue updates are broadcast in these scenarios:

1. When a customer joins the queue
2. When a customer leaves the queue
3. When an appointment is created
4. When an appointment status changes (starts/completes/cancels)
5. Every 30 seconds via periodic background refresh

## Authentication and Security

The current implementation does not include authentication for WebSocket connections. In production, consider adding authentication:

1. Use token validation in the WebSocket endpoint
2. Implement rate limiting for connections
3. Restrict which origins can connect
 