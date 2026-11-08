import os
from html import unescape
import re
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager


_test_dir = tempfile.TemporaryDirectory()
os.environ["WAVEGUARD_SECRET_KEY"] = "test-key-for-local-unit-tests-only"
os.environ["WAVEGUARD_DATABASE_PATH"] = os.path.join(_test_dir.name, "test.sqlite3")

import app as app_module
from werkzeug.security import generate_password_hash


@contextmanager
def test_db():
    db = sqlite3.connect(app_module.app.config["DATABASE_PATH"])
    try:
        yield db
        db.commit()
    finally:
        db.close()


class WaveGuardAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app_module.app
        cls.app.config.update(TESTING=True, DATABASE_PATH=os.path.join(_test_dir.name, "test.sqlite3"))
        cls.client = cls.app.test_client()
        cls.app.test_cli_runner().invoke(args=["init-db"])
        with test_db() as db:
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("operator", generate_password_hash("correct horse battery staple")),
            )

    def setUp(self):
        self.client = self.app.test_client()
        with test_db() as db:
            db.execute("DELETE FROM web_sessions")

    def csrf_from_login(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode("ascii")

    def sign_in(self):
        token = self.csrf_from_login()
        return self.client.post(
            "/login",
            data={"username": "operator", "password": "correct horse battery staple", "csrf_token": token},
            follow_redirects=False,
        )

    def test_dashboard_requires_authentication(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_health_keeps_existing_public_payload(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "project": "WaveGuard", "status": "running", "mode": "offline simulation"
        })

    def test_dashboard_renders_isolated_scenario_controls_and_script(self):
        self.sign_in()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Flood Scenario Simulator", response.data)
        self.assertIn(b'id="scenarioLevel"', response.data)
        self.assertIn(b'id="resetScenarioBtn"', response.data)
        script = self.client.get("/static/js/dashboard.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn(b"function updateScenario()", script.data)
        self.assertIn(b"getStatus(level)", script.data)
        script.close()
        styles = self.client.get("/static/css/style.css")
        self.assertEqual(styles.status_code, 200)
        styles.close()

    def test_login_rejects_missing_csrf_token(self):
        self.csrf_from_login()
        response = self.client.post("/login", data={"username": "operator", "password": "wrong"})
        self.assertEqual(response.status_code, 400)

    def test_signup_validates_password_and_requires_csrf(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)
        token = re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()
        response = self.client.post("/signup", data={"username": "newuser", "password": "short", "csrf_token": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn("between 12 and 256 characters", unescape(response.get_data(as_text=True)))
        self.assertEqual(self.client.post("/signup", data={"username": "newuser", "password": "long enough password"}).status_code, 400)

    def test_signup_creates_hashed_user_and_rejects_duplicate_case_insensitively(self):
        response = self.client.get("/signup")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()
        result = self.client.post("/signup", data={"username": "Demo User", "password": "a secure password", "csrf_token": token})
        self.assertEqual(result.status_code, 302)
        with test_db() as db:
            row = db.execute("SELECT username, password_hash FROM users WHERE username = ? COLLATE NOCASE", ("Demo User",)).fetchone()
        self.assertEqual(row[0], "Demo User")
        self.assertNotEqual(row[1], "a secure password")
        self.assertTrue(app_module.check_password_hash(row[1], "a secure password"))
        response = self.client.get("/signup")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()
        duplicate = self.client.post("/signup", data={"username": "demo user", "password": "a secure password", "csrf_token": token})
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn(b"username is unavailable", duplicate.data)

    def test_signup_route_is_not_an_authenticated_action(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)

    def test_invalid_login_uses_generic_error(self):
        token = self.csrf_from_login()
        response = self.client.post("/login", data={
            "username": "missing-user", "password": "wrong", "csrf_token": token
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("We couldn't sign you in with those details.", unescape(response.get_data(as_text=True)))
        self.assertNotIn(b"account does not exist", response.data.lower())

    def test_wrong_password_uses_same_generic_error(self):
        token = self.csrf_from_login()
        response = self.client.post("/login", data={
            "username": "operator", "password": "incorrect password", "csrf_token": token
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("We couldn't sign you in with those details.", unescape(response.get_data(as_text=True)))

    def test_login_creates_server_session_and_logout_invalidates_it(self):
        response = self.sign_in()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        cookie = self.client.get_cookie("waveguard_session")
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie.http_only)
        self.assertFalse(cookie.secure)
        with test_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0], 1)

        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Monitoring overview", dashboard.data)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', dashboard.data)
        self.assertIsNotNone(match)
        response = self.client.post("/logout", data={"csrf_token": match.group(1).decode("ascii")})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertEqual(self.client.get("/").status_code, 302)
        with test_db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM web_sessions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
