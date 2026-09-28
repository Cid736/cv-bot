import os
import unittest
from unittest.mock import patch

os.environ.setdefault("GROQ_API_KEY", "test-key")

import app


class AppBehaviorTests(unittest.TestCase):
    def setUp(self):
        app.sessions.clear()
        app._rate_log.clear()
        app._suggest_rate_log.clear()

    def test_rate_limit_store_evicts_old_ip_at_capacity(self):
        with patch.object(app, "MAX_RATE_IPS", 2):
            for ip in ("ip-1", "ip-2", "ip-3"):
                self.assertTrue(app._rate_ok(ip))

        self.assertEqual(len(app._rate_log), 2)
        self.assertNotIn("ip-1", app._rate_log)
        self.assertIn("ip-2", app._rate_log)
        self.assertIn("ip-3", app._rate_log)

    def test_existing_session_does_not_evict_another_session(self):
        for index in range(app.MAX_SESSIONS):
            app.sessions[f"{index:024x}"] = []
        oldest_session = next(iter(app.sessions))
        existing_session = f"{1:024x}"

        with patch.object(app, "_groq_chat", return_value="ok"):
            response = app.app.test_client().post(
                "/chat",
                json={"question": "hello", "session_id": existing_session},
                environ_base={"REMOTE_ADDR": "test-client"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(app.sessions), app.MAX_SESSIONS)
        self.assertIn(oldest_session, app.sessions)
        self.assertIn(existing_session, app.sessions)

    def test_endpoints_reject_malformed_json_payloads(self):
        client = app.app.test_client()
        for payload in (["not", "an", "object"], {"question": None}, {"question": 42}):
            with self.subTest(endpoint="/chat", payload=payload):
                response = client.post('/chat', json=payload)
                self.assertEqual(response.status_code, 400)

        for payload in (["not", "an", "object"], {"question": 42, "answer": "ok"}):
            with self.subTest(endpoint="/suggest", payload=payload):
                response = client.post('/suggest', json=payload)
                self.assertEqual(response.status_code, 400)

    def test_suggestions_use_the_same_language_detection_as_chat(self):
        captured = {}

        def fake_groq_chat(messages, temperature):
            captured["prompt"] = messages[0]["content"]
            captured["temperature"] = temperature
            return '["One?", "Two?", "Three?"]'

        with patch.object(app, "_groq_chat", side_effect=fake_groq_chat):
            response = app.app.test_client().post(
                "/suggest",
                json={
                    "question": "Which Cloud & DevOps projects have you deployed?",
                    "answer": "Eric deployed services to Google Cloud Run.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("in English.", captured["prompt"])
        self.assertEqual(captured["temperature"], 0.3)


if __name__ == "__main__":
    unittest.main()