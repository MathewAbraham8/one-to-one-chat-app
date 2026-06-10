import logging
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Maps user_id (int) to a list of active WebSocket connections
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logging.info(f"User {user_id} connected. Total active connections: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                logging.info(f"User {user_id} disconnected.")
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_to_user(self, user_id: int, data: dict):
        """
        Send payload to a specific user if they are online.
        """
        connections = self.active_connections.get(user_id, [])
        for connection in connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                logging.error(f"Error sending message to user {user_id}: {str(e)}")

# Singleton connection manager
manager = ConnectionManager()
