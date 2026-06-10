import unittest
from datetime import datetime
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User, Message
from main import app

from sqlalchemy.pool import StaticPool

# Set up an isolated in-memory database for testing
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Apply the dependency overrides
app.dependency_overrides[get_db] = override_get_db

class TestChatApplication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create all tables in the in-memory database
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        # Clear database records between tests to ensure clean state
        db = TestingSessionLocal()
        db.query(Message).delete()
        db.query(User).delete()
        db.commit()
        db.close()

    def test_user_registration_and_validation(self):
        # 1. Successful signup
        response = self.client.post(
            "/register",
            json={"username": "alice_test", "password": "securepassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["username"], "alice_test")
        self.assertIn("id", response.json())

        # 2. Duplicate signup should fail
        response = self.client.post(
            "/register",
            json={"username": "alice_test", "password": "anotherpassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Password length check (must be >= 12 characters)
        response = self.client.post(
            "/register",
            json={"username": "bob_test", "password": "short"}
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 4. Username regex validation (e.g. no special symbols like @ or $)
        response = self.client.post(
            "/register",
            json={"username": "bob$test", "password": "securepassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_user_login_and_jwt_issuance(self):
        # Register test user
        self.client.post(
            "/register",
            json={"username": "alice_test", "password": "securepassword123"}
        )

        # 1. Correct credentials login
        response = self.client.post(
            "/login",
            json={"username": "alice_test", "password": "securepassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access_token", response.json())
        self.assertEqual(response.json()["token_type"], "bearer")

        # 2. Incorrect password login
        response = self.client.post(
            "/login",
            json={"username": "alice_test", "password": "wrongpassword123"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["detail"], "Invalid username or password")

    def test_unauthenticated_api_access(self):
        # Accessing protected endpoint without token should return 401 Unauthorized
        response = self.client.get("/users")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authorized_user_deletion_and_idor(self):
        # Register user A and user B
        res_a = self.client.post("/register", json={"username": "usera", "password": "securepassword123"})
        res_b = self.client.post("/register", json={"username": "userb", "password": "securepassword123"})
        
        user_a_id = res_a.json()["id"]
        user_b_id = res_b.json()["id"]

        # Log in as user A
        login_res = self.client.post("/login", json={"username": "usera", "password": "securepassword123"})
        token_a = login_res.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # 1. User A tries to delete user B (IDOR attempt) -> 403 Forbidden
        response = self.client.delete(f"/users/{user_b_id}", headers=headers_a)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. User A deletes User A (Self-deletion) -> 200 OK
        response = self.client.delete(f"/users/{user_a_id}", headers=headers_a)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_revocation(self):
        # Register and login
        self.client.post("/register", json={"username": "alice_test", "password": "securepassword123"})
        login_res = self.client.post("/login", json={"username": "alice_test", "password": "securepassword123"})
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Verify token works
        response = self.client.get("/users", headers=headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Log out
        logout_res = self.client.post("/logout", headers=headers)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Token must now be rejected
        response = self.client.get("/users", headers=headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_message_management_and_idor(self):
        # Register and login Alice and Bob
        res_alice = self.client.post("/register", json={"username": "alice", "password": "securepassword123"})
        res_bob = self.client.post("/register", json={"username": "bob", "password": "securepassword123"})
        alice_id = res_alice.json()["id"]
        bob_id = res_bob.json()["id"]

        # Login Alice
        login_alice = self.client.post("/login", json={"username": "alice", "password": "securepassword123"})
        token_alice = login_alice.json()["access_token"]
        headers_alice = {"Authorization": f"Bearer {token_alice}"}

        # Login Bob
        login_bob = self.client.post("/login", json={"username": "bob", "password": "securepassword123"})
        token_bob = login_bob.json()["access_token"]
        headers_bob = {"Authorization": f"Bearer {token_bob}"}

        # Create a message manually in the DB or simulate conversation
        db = TestingSessionLocal()
        msg1 = Message(sender_id=alice_id, receiver_id=bob_id, content="Hi Bob!")
        msg2 = Message(sender_id=bob_id, receiver_id=alice_id, content="Hello Alice")
        db.add_all([msg1, msg2])
        db.commit()
        db.refresh(msg1)
        db.refresh(msg2)
        db.close()

        # 1. Alice gets messages with Bob -> 200 OK
        response = self.client.get(f"/messages/{bob_id}", headers=headers_alice)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(response.json()[0]["content"], "Hi Bob!")

        # 2. Bob tries to delete Alice's message (IDOR attempt) -> 403 Forbidden
        response = self.client.delete(f"/messages/{msg1.id}", headers=headers_bob)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Alice deletes her own message -> 200 OK
        response = self.client.delete(f"/messages/{msg1.id}", headers=headers_alice)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_websocket_authentication_and_chat(self):
        # Register Alice and Bob
        res_alice = self.client.post("/register", json={"username": "alice", "password": "securepassword123"})
        res_bob = self.client.post("/register", json={"username": "bob", "password": "securepassword123"})
        bob_id = res_bob.json()["id"]

        # Log in Alice
        login_alice = self.client.post("/login", json={"username": "alice", "password": "securepassword123"})
        token_alice = login_alice.json()["access_token"]

        # Log in Bob
        login_bob = self.client.post("/login", json={"username": "bob", "password": "securepassword123"})
        token_bob = login_bob.json()["access_token"]

        # Connect Alice WS and Bob WS using TestClient's websocket_connect
        with self.client.websocket_connect(f"/ws?token={token_alice}") as ws_alice:
            with self.client.websocket_connect(f"/ws?token={token_bob}") as ws_bob:
                # Alice sends message to Bob
                ws_alice.send_json({"receiver_id": bob_id, "content": "Hello Bob via WS!"})
                
                # Bob should receive the message in real time
                bob_received = ws_bob.receive_json()
                self.assertEqual(bob_received["type"], "message")
                self.assertEqual(bob_received["data"]["content"], "Hello Bob via WS!")
                self.assertEqual(bob_received["data"]["sender_id"], res_alice.json()["id"])
                
                # Alice should receive a receipt
                alice_receipt = ws_alice.receive_json()
                self.assertEqual(alice_receipt["type"], "receipt")
                self.assertEqual(alice_receipt["data"]["content"], "Hello Bob via WS!")

if __name__ == "__main__":
    unittest.main()
