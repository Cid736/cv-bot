import json
import os
import unittest
from unittest.mock import patch

import tempfile

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ["STATS_DB"] = os.path.join(tempfile.mkdtemp(), "stats.db")
os.environ["STATS_TOKEN"] = "secret-token"

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
            ("¿Cuánta experiencia tiene?", "Spanish", "Dos años de experiencia"),
            ("¿Por qué deberíamos contratarle?", "Spanish", "Puntos fuertes"),
            ("Why should we hire him?", "English", "strengths"),
            ("What programming languages does he know?", "English", "Python"),
            ("¿Cuál es su expectativa salarial?", "Spanish", "contactar con Eric"),
            ("Cuéntame sobre él", "Spanish", "Eric Cid López"),
            ("Does he know networking?", "English", "Systems and support"),
            ("¿Qué nivel de inglés tiene?", "Spanish", "B1–B2"),
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
                "/chat", json={"question": "Cuéntame sobre él"},
                environ_base={"REMOTE_ADDR": "test-client"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["rate_limited"])
        self.assertIn("Eric Cid López", data["answer"])

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
        self.assertIn("Dos años", app.static_answer("Quanta experiència té?", "Catalan"))

    def test_index_pins_cdn_versions(self):
        html = app.app.test_client().get("/").get_data(as_text=True)
        self.assertIn("marked@15.0.12", html)
        self.assertIn("dompurify@3.2.6", html)

    # ── v0.7 features ────────────────────────────────────────────────────────

    def _post(self, payload, ip="t"):
        return app.app.test_client().post("/chat", json=payload, environ_base={"REMOTE_ADDR": ip})

    def test_streaming_sends_deltas_and_saves_session(self):
        with patch.object(app, "_groq_stream", return_value=iter(["**Eric** ", "trabaja ", "en Infinity Neural."])):
            res = self._post({"question": "¿Dónde trabaja?", "stream": True})
        self.assertEqual(res.mimetype, "text/event-stream")
        events = [json.loads(line[6:]) for line in res.get_data(as_text=True).split("\n\n") if line.startswith("data: ")]
        self.assertEqual(events[0]["type"], "meta")
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "delta"),
                         "**Eric** trabaja en Infinity Neural.")
        self.assertEqual(events[-1]["type"], "done")
        self.assertRegex(events[-1]["message_id"], r"^[0-9a-f]{16}$")
        self.assertEqual(app.sessions[events[0]["session_id"]][-1]["a"], "**Eric** trabaja en Infinity Neural.")

    def test_streaming_rate_limit_returns_static_json(self):
        import httpx
        err = app.RateLimitError("Please try again in 7s.", response=httpx.Response(
            429, request=httpx.Request("POST", "https://api.groq.com")), body=None)
        with patch.object(app, "_groq_stream", side_effect=err):
            res = self._post({"question": "Cuéntame sobre él", "stream": True})
        data = res.get_json()
        self.assertTrue(data["rate_limited"])
        self.assertIn("7s", data["reset_msg"])

    def test_job_mode_wraps_offer_and_allows_long_text(self):
        captured = {}

        def fake(messages, temperature, **kwargs):
            captured.update(messages=messages, **kwargs)
            return "| Requisito | Encaje |"

        offer = "Requisitos: Intune, ServiceNow, Active Directory. " * 40  # > MAX_QUESTION_LEN
        self.assertGreater(len(offer), app.MAX_QUESTION_LEN)
        with patch.object(app, "_groq_chat", side_effect=fake):
            res = self._post({"question": offer, "mode": "job"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("<job_description>", captured["messages"][-1]["content"])
        self.assertEqual(captured["max_tokens"], app.JOB_MAX_TOKENS)
        self.assertEqual(captured["reasoning_effort"], "medium")
        too_long = self._post({"question": "x" * (app.JOB_MAX_LEN + 1), "mode": "job"})
        self.assertEqual(too_long.status_code, 400)

    def test_feedback_is_stored_and_shown_in_stats(self):
        with patch.object(app, "_groq_chat", return_value="Not specified in the profile."):
            msg_id = self._post({"question": "Does he know Rust?"}).get_json()["message_id"]
        client = app.app.test_client()
        self.assertTrue(client.post("/feedback", json={"message_id": msg_id, "rating": -1}).get_json()["ok"])
        self.assertEqual(client.post("/feedback", json={"message_id": "nope", "rating": 1}).status_code, 400)
        self.assertEqual(client.post("/feedback", json={"message_id": msg_id, "rating": 5}).status_code, 400)
        summary = client.get("/stats.json?token=secret-token").get_json()
        self.assertIn("Does he know Rust?", [r["question"] for r in summary["disliked"]])
        self.assertIn("Does he know Rust?", [r["question"] for r in summary["not_covered"]])

    def test_stats_require_token(self):
        client = app.app.test_client()
        self.assertEqual(client.get("/stats").status_code, 404)
        self.assertEqual(client.get("/stats?token=wrong").status_code, 404)
        page = client.get("/stats?token=secret-token")
        self.assertEqual(page.status_code, 200)
        self.assertIn("estad", page.get_data(as_text=True))

    def test_public_cv_has_no_phone_number(self):
        res = app.app.test_client().get("/cv.pdf")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/pdf")
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf not installed")
        import io
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(res.data)).pages)
        self.assertIn("Infinity Neural", text)
        self.assertNotIn("611", text)

    def test_chat_survives_unwritable_stats_db(self):
        import stats
        with patch.object(stats, "_conn", None), \
             patch.object(stats, "DB_PATH", stats.Path("/proc/forbidden/stats.db")), \
             patch.object(app, "_groq_chat", return_value="Respuesta"):
            res = self._post({"question": "¿Qué certificaciones tiene?"})
            self.assertEqual(res.status_code, 200)
            self.assertIsNone(res.get_json()["message_id"])
            page = app.app.test_client().get("/stats?token=secret-token")
            self.assertEqual(page.status_code, 200)

    def test_page_uses_svg_icons_and_valid_icon_json(self):
        html = app.app.test_client().get("/").get_data(as_text=True)
        self.assertIn('<svg class="icon"', html)
        raw = html.split('<script type="application/json" id="icons">', 1)[1].split("</script>", 1)[0]
        icons = json.loads(raw.replace("<\\/", "</"))
        for name in ("thumbs-up", "thumbs-down", "copy", "clipboard", "briefcase"):
            self.assertIn(name, icons)

    def test_page_has_theme_toggle_share_preview_and_contact_card(self):
        html = app.app.test_client().get("/").get_data(as_text=True)
        self.assertIn('id="theme-toggle"', html)
        self.assertIn('property="og:image"', html)
        self.assertIn('favicon.svg', html)
        self.assertIn("¿Encaja con tu vacante?", html)
        self.assertIn("Eric Cid López", html)
        self.assertNotIn("gpt-oss", html)  # no model name shown to recruiters
        for asset in ("/static/og.png", "/static/favicon.svg", "/static/fonts/inter-latin.woff2", "/static/foto.webp"):
            self.assertEqual(app.app.test_client().get(asset).status_code, 200, asset)

    # ── Regression tests for the full review ─────────────────────────────────

    def _rate_limit_error(self):
        import httpx
        return app.RateLimitError("Please try again in 7s.", response=httpx.Response(
            429, request=httpx.Request("POST", "https://api.groq.com")), body=None)

    def test_job_offer_during_outage_says_analysis_unavailable(self):
        offer = "Buscamos técnico de soporte IT. Perfil: experiencia con Active Directory e Intune."
        with patch.object(app, "_groq_chat", side_effect=self._rate_limit_error()):
            data = self._post({"question": offer, "mode": "job"}).get_json()
        self.assertTrue(data["rate_limited"])
        self.assertIn("no puedo analizar la oferta", data["answer"])
        self.assertNotIn("Eric Cid López** es", data["answer"])

    def test_follow_up_sees_the_whole_long_offer(self):
        offer = ("Requisito inicial. " + "relleno " * 600 + "ÚLTIMO REQUISITO: certificación ITIL.")
        self.assertGreater(len(offer), 3000)
        sent = []
        def fake(messages, temperature, **kwargs):
            sent.append(messages); return "ok"
        with patch.object(app, "_groq_chat", side_effect=fake):
            sid = self._post({"question": offer, "mode": "job"}).get_json()["session_id"]
            self._post({"question": "¿Cumple el último requisito?", "session_id": sid})
        history_q = sent[-1][1]["content"]
        self.assertIn("ÚLTIMO REQUISITO", history_q)
        self.assertIn("</job_description>", history_q)

    def test_truncated_first_answer_is_not_cached(self):
        def fake(messages, temperature, **kwargs):
            app._last_finish.reason = "length"; return "Respuesta cortada a med"
        app._answer_cache.clear()
        with patch.object(app, "_groq_chat", side_effect=fake):
            self._post({"question": "¿Qué certificaciones tiene exactamente?"})
        self.assertEqual(app._answer_cache, {})

    def test_truncated_stream_is_not_cached(self):
        class Cut:
            finish_reason = "length"
            def __iter__(self): return iter(["Respuesta ", "cortada"])
        app._answer_cache.clear()
        with patch.object(app, "_groq_stream", return_value=Cut()):
            self._post({"question": "¿Dónde estudió?", "stream": True}).get_data()
        self.assertEqual(app._answer_cache, {})

    def test_empty_completion_falls_back_instead_of_500(self):
        with patch.object(app, "_groq_chat", return_value=""):
            res = self._post({"question": "¿Qué experiencia tiene?"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["rate_limited"])

    def test_stats_token_with_non_ascii_is_404_not_500(self):
        self.assertEqual(app.app.test_client().get("/stats?token=%C3%A9").status_code, 404)

    def test_og_image_is_https_in_production(self):
        html = app.app.test_client().get("/", base_url="http://cv-bot.example.com").get_data(as_text=True)
        self.assertIn('content="https://cv-bot.example.com/static/og.png"', html)

    def test_eval_checks(self):
        from evals.run_evals import check
        self.assertEqual(check({"lang": "English", "must_contain_any": ["two years"]},
                               "He has two years of experience in IT support."), [])
        self.assertTrue(check({"must_not_match": ["611"]}, "Call 611 409 833"))
        self.assertTrue(check({"off_topic": True}, "Kubernetes is... ```kubectl get pods```"))
        self.assertTrue(check({"lang": "English"}, "Tiene dos años de experiencia en soporte y sistemas."))


if __name__ == "__main__":
    unittest.main()