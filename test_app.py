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

        def fake_groq_chat(messages, temperature, **kwargs):
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

    def test_static_fallback_matches_whole_words_and_ignores_accents(self):
        cases = [
            ("¿Cuánta experiencia tienes?", "Spanish", "dos años de experiencia"),
            ("¿Por qué deberíamos contratarte?", "Spanish", "Porque tengo base"),
            ("Cuéntame sobre ti", "Spanish", "Soy Eric C."),
            ("Do you know networking?", "English", "systems & networking"),
            ("How many years of experience?", "English", "Two years"),
        ]
        for question, lang, expected in cases:
            with self.subTest(question=question):
                self.assertIn(expected, app.static_answer(question, lang))

    def test_groq_outage_degrades_to_static_answer(self):
        import httpx
        err = app.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))
        with patch.object(app, "_groq_chat", side_effect=err):
            response = app.app.test_client().post(
                "/chat", json={"question": "Cuéntame sobre ti"},
                environ_base={"REMOTE_ADDR": "test-client"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["rate_limited"])
        self.assertIn("Soy Eric C.", data["answer"])

    def test_chat_and_suggest_share_the_same_client_ip(self):
        headers = {"X-Real-IP": "1.1.1.1", "X-Forwarded-For": "2.2.2.2"}
        with app.app.test_request_context("/", headers=headers):
            chat_ip = app._client_ip()
        with patch.object(app, "_groq_chat", return_value='["a?"]'):
            app.app.test_client().post("/suggest", json={"question": "q", "answer": "a"},
                                       headers=headers)
        self.assertEqual(chat_ip, "1.1.1.1")
        self.assertIn("1.1.1.1", app._suggest_rate_log)

    def test_system_prompt_restricts_scope_to_eric(self):
        self.assertIn("ONLY answer questions about Eric", app.SYSTEM_PROMPT)
        self.assertIn("Cybersecurity Fundamentals", app.PROFILE)
        self.assertNotIn("611 409 833", app.PROFILE)  # phone must never reach the model

    def test_language_detection(self):
        cases = [
            ("cual es tu experiencia con docker", "Spanish"),       # no accents
            ("tiene experiencia con Active Directory y Microsoft Intune", "Spanish"),
            ("sabe kubernetes?", "Spanish"),                        # tie with Portuguese
            ("Is he willing to relocate to Málaga?", "English"),    # accented place name
            ("Does he have a résumé I can download?", "English"),
            ("Tell me about the FCT internship at Instituto Escuela de Badalona", "English"),
            ("We are hiring in Logroño. Requirements: Linux and networking. Is Eric a good fit?", "English"),
            ("Quina experiència té amb Linux?", "Catalan"),
            ("Quelle est son expérience avec Docker ?", "French"),
            ("Quais projetos ele fez?", "Portuguese"),
            ("Che esperienza ha con Linux?", "Italian"),
            ("Welche Erfahrung hat er mit Kubernetes?", "German"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(app.detect_lang(text), expected)

    def test_ambiguous_follow_up_keeps_conversation_language(self):
        for text in ("ok", "Docker?", "Python"):
            with self.subTest(text=text):
                self.assertIsNone(app.detect_lang(text))
                self.assertEqual(app.resolve_lang(text, "English"), "English")
                self.assertEqual(app.resolve_lang(text, None), app.DEFAULT_LANG)

    def test_chat_uses_previous_language_for_short_follow_up(self):
        prompts = []

        def fake(messages, temperature, **kwargs):
            prompts.append(messages[0]["content"])
            return "answer"

        client = app.app.test_client()
        with patch.object(app, "_groq_chat", side_effect=fake):
            first = client.post("/chat", json={"question": "What projects has he built?"},
                                environ_base={"REMOTE_ADDR": "lang-test"}).get_json()
            second = client.post("/chat", json={"question": "Docker?", "session_id": first["session_id"]},
                                 environ_base={"REMOTE_ADDR": "lang-test"}).get_json()
        self.assertEqual(first["lang"], "English")
        self.assertEqual(second["lang"], "English")
        self.assertIn("entire reply in English", prompts[-1])

    def test_catalan_rate_limit_falls_back_to_spanish_answers(self):
        self.assertIn("dos años", app.static_answer("Quanta experiència té?", "Catalan"))

    def test_index_pins_cdn_versions(self):
        html = app.app.test_client().get("/").get_data(as_text=True)
        self.assertIn("marked@15.0.12", html)
        self.assertIn("dompurify@3.2.6", html)


if __name__ == "__main__":
    unittest.main()