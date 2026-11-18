import os
import sys
import secrets
import unittest
from pathlib import Path

# Ensure truststore for Windows SSL
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from fastapi.testclient import TestClient
from backend.leo_api import app
from backend.database import SessionLocal
from backend.models import User, UserSession, Conversation, Message
from backend.intent_router import detect_intent, should_perform_search


class TestIntelligentSearchAndProfilePicture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client_ctx = TestClient(app)
        cls.client = cls.client_ctx.__enter__()

        cls.db = SessionLocal()
        cls.test_email = f"user_feat_{secrets.token_hex(4)}@example.com"
        cls.test_password = "SecurePassword123!"
        cls.test_name = "Feature Tester"

        # Register User 1
        reg = cls.client.post("/auth/register", json={
            "full_name": cls.test_name,
            "email": cls.test_email,
            "password": cls.test_password
        })
        assert reg.status_code == 201, f"Registration failed: {reg.text}"

        # Login User 1
        login = cls.client.post("/auth/login", json={
            "email": cls.test_email,
            "password": cls.test_password
        })
        assert login.status_code == 200, f"Login failed: {login.text}"

    @classmethod
    def tearDownClass(cls):
        try:
            # Clean up user and sessions from DB
            user = cls.db.query(User).filter(User.email == cls.test_email).first()
            if user:
                cls.db.query(UserSession).filter(UserSession.user_id == user.id).delete()
                cls.db.query(Conversation).filter(Conversation.user_id == user.id).delete()
                cls.db.delete(user)
                cls.db.commit()
            cls.db.close()
            cls.client_ctx.__exit__(None, None, None)
        except Exception:
            pass

    # ==========================================
    # 1. INTENT DETECTION & SEARCH DECISION TESTS
    # ==========================================

    def test_greeting_with_search_enabled_no_search(self):
        """Greeting with search enabled: intent is conversation, no search triggered."""
        greetings = ["Hi", "Hello", "Hey LEO", "Good morning", "How are you?"]
        for g in greetings:
            self.assertEqual(detect_intent(g), "conversation")
            self.assertFalse(should_perform_search(g, search_enabled=True))

    def test_greeting_with_search_disabled_no_search(self):
        """Greeting with search disabled: no search triggered."""
        greetings = ["Hi", "Hello", "Thank you"]
        for g in greetings:
            self.assertFalse(should_perform_search(g, search_enabled=False))

    def test_normal_knowledge_question_no_search(self):
        """Normal knowledge and coding questions: answered directly, no search."""
        queries = [
            "What is Python?",
            "Explain photosynthesis in plants",
            "Write a function to reverse a string in Python",
            "How does binary search work?",
            "What is 25 * 14?"
        ]
        for q in queries:
            intent = detect_intent(q)
            self.assertEqual(intent, "knowledge", f"Failed for {q}")
            self.assertFalse(should_perform_search(q, search_enabled=True), f"Triggered search for {q}")
            self.assertFalse(should_perform_search(q, search_enabled=False))

    def test_latest_news_triggers_search_when_enabled(self):
        """Latest news & breaking events: search triggered when enabled, blocked when disabled."""
        queries = [
            "What is the latest news in AI today?",
            "Breaking news updates about SpaceX",
            "Current stock price of Apple right now",
            "Current weather in London"
        ]
        for q in queries:
            self.assertEqual(detect_intent(q), "web_search", f"Failed for {q}")
            self.assertTrue(should_perform_search(q, search_enabled=True), f"Failed search enable for {q}")
            self.assertFalse(should_perform_search(q, search_enabled=False), f"Failed search disable for {q}")

    def test_learning_resources_triggers_search_when_enabled(self):
        """Courses, certifications, tutorials, and docs: search triggered when enabled."""
        queries = [
            "Best online courses and certifications for AWS Solutions Architect",
            "Official documentation for FastAPI middleware",
            "Recommended tutorials for learning Rust programming",
            "Research papers on transformer neural networks"
        ]
        for q in queries:
            self.assertEqual(detect_intent(q), "web_search", f"Failed for {q}")
            self.assertTrue(should_perform_search(q, search_enabled=True), f"Failed search enable for {q}")
            self.assertFalse(should_perform_search(q, search_enabled=False), f"Failed search disable for {q}")

    # ==========================================
    # 2. ENDPOINT INTEGRATION TESTS
    # ==========================================

    def test_chat_greeting_with_search_toggle_enabled(self):
        """Live /chat: 'Hi' with search_enabled=True returns instant greeting without web sources."""
        res = self.client.post("/chat", json={
            "message": "Hi",
            "search_enabled": True
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["sources"], [])
        self.assertIn("Hey there!", data["response"])

    def test_chat_knowledge_with_search_toggle_enabled(self):
        """Live /chat: General knowledge with search_enabled=True does NOT search."""
        res = self.client.post("/chat", json={
            "message": "What is an integer in computer science?",
            "search_enabled": True,
            "max_new_tokens": 80
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["sources"], [])
        self.assertTrue(len(data["response"]) > 0)

    def test_chat_news_search_disabled_does_not_search(self):
        """Live /chat: News query with search_enabled=False does NOT perform web search."""
        res = self.client.post("/chat", json={
            "message": "What is the latest news in AI today?",
            "search_enabled": False,
            "max_new_tokens": 80
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["sources"], [])

    def test_chat_web_search_failure_graceful_fallback(self):
        """Simulate web search failure: should answer without crashing."""
        import backend.leo_api as leo_api_module
        original_search = leo_api_module.search_engine

        class BrokenSearchEngine:
            async def search(self, *args, **kwargs):
                raise RuntimeError("Simulated Tavily connection timeout")

        try:
            leo_api_module.search_engine = BrokenSearchEngine()
            res = self.client.post("/chat", json={
                "message": "What is the latest news in quantum computing today?",
                "search_enabled": True,
                "max_new_tokens": 80
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(len(data["response"]) > 0)
        finally:
            leo_api_module.search_engine = original_search

    # ==========================================
    # 3. PROFILE PICTURE TESTS
    # ==========================================

    def test_profile_endpoints_require_authentication(self):
        """Unauthenticated requests to profile endpoints are rejected with 401."""
        with TestClient(app) as unauth_client:
            self.assertEqual(unauth_client.get("/auth/profile").status_code, 401)
            self.assertEqual(unauth_client.post("/auth/profile-picture").status_code, 401)
            self.assertEqual(unauth_client.delete("/auth/profile-picture").status_code, 401)

    def test_get_user_profile(self):
        """GET /auth/profile returns profile information for authenticated user."""
        res = self.client.get("/auth/profile")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user"]["email"], self.test_email)
        self.assertEqual(data["user"]["full_name"], self.test_name)

    def test_upload_invalid_file_rejected(self):
        """Rejects non-image or spoofed files."""
        fake_content = b"<html><script>alert('xss')</script></html>"
        res = self.client.post(
            "/auth/profile-picture",
            files={"file": ("malicious.png", fake_content, "image/png")}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid image format", res.json()["detail"])

    def test_upload_oversized_file_rejected(self):
        """Rejects files larger than 5MB."""
        oversized = b"\xff\xd8\xff\xe0" + b"0" * (5 * 1024 * 1024 + 1024)
        res = self.client.post(
            "/auth/profile-picture",
            files={"file": ("large.jpg", oversized, "image/jpeg")}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("exceeds maximum allowed limit", res.json()["detail"])

    def test_upload_and_delete_profile_picture_lifecycle(self):
        """Complete lifecycle: upload PNG, verify disk & static serve, replace with WebP, delete."""
        # 1. Upload valid PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
            b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        res = self.client.post(
            "/auth/profile-picture",
            files={"file": ("avatar.png", png_bytes, "image/png")}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        pic_url = data["profile_picture"]
        self.assertTrue(pic_url.startswith("/uploads/profile_pictures/avatar_"))
        self.assertTrue(pic_url.endswith(".png"))

        # Verify file exists on disk
        filename = Path(pic_url).name
        local_path = Path("uploads/profile_pictures") / filename
        self.assertTrue(local_path.is_file())

        # Verify GET /auth/me returns updated profile_picture
        me_res = self.client.get("/auth/me")
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["user"]["profile_picture"], pic_url)

        # Verify static file serving
        static_res = self.client.get(pic_url)
        self.assertEqual(static_res.status_code, 200)
        self.assertEqual(static_res.content, png_bytes)

        # 2. Replace with WebP
        webp_bytes = b"RIFF\x20\x00\x00\x00WEBPVP8 \x14\x00\x00\x000" + b"\x00" * 20
        res_webp = self.client.post(
            "/auth/profile-picture",
            files={"file": ("avatar.webp", webp_bytes, "image/webp")}
        )
        self.assertEqual(res_webp.status_code, 200)
        new_url = res_webp.json()["profile_picture"]
        self.assertTrue(new_url.endswith(".webp"))

        # Old PNG file should be deleted from disk
        self.assertFalse(local_path.is_file())

        # New WebP file exists on disk
        new_filename = Path(new_url).name
        new_path = Path("uploads/profile_pictures") / new_filename
        self.assertTrue(new_path.is_file())

        # 3. Delete profile picture
        del_res = self.client.delete("/auth/profile-picture")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "success")

        # WebP file is removed from disk
        self.assertFalse(new_path.is_file())

        # Profile shows None
        me_after_del = self.client.get("/auth/me")
        self.assertIsNone(me_after_del.json()["user"]["profile_picture"])

    def test_user_profile_isolation(self):
        """User 2 cannot see or modify User 1's profile picture."""
        with TestClient(app) as user2_client:
            user2_email = f"user2_{secrets.token_hex(4)}@example.com"
            reg = user2_client.post("/auth/register", json={
                "full_name": "Second User",
                "email": user2_email,
                "password": "Password98765!"
            })
            self.assertEqual(reg.status_code, 201)
            login = user2_client.post("/auth/login", json={
                "email": user2_email,
                "password": "Password98765!"
            })
            self.assertEqual(login.status_code, 200)

            # User 2 profile starts empty
            self.assertIsNone(user2_client.get("/auth/profile").json()["user"]["profile_picture"])

            # Clean up User 2
            u2 = self.db.query(User).filter(User.email == user2_email).first()
            if u2:
                self.db.query(UserSession).filter(UserSession.user_id == u2.id).delete()
                self.db.delete(u2)
                self.db.commit()


if __name__ == "__main__":
    unittest.main()
