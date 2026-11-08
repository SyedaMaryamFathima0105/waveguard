import json
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    session, url_for,
)
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.security import check_password_hash, generate_password_hash


load_dotenv()


class SQLiteSession(dict, SessionMixin):
    """Small server-side session stored in the application's SQLite database."""

    def __init__(self, initial=None, sid=None, new=False):
        super().__init__(initial or {})
        self.sid = sid
        self.new = new


class SQLiteSessionInterface(SessionInterface):
    session_class = SQLiteSession

    @staticmethod
    def _signature(app, sid):
        key = app.config["SECRET_KEY"].encode("utf-8")
        return hmac.new(key, sid.encode("ascii"), hashlib.sha256).hexdigest()

    def open_session(self, app, req):
        cookie = req.cookies.get(self.get_cookie_name(app), "")
        sid, separator, signature = cookie.partition(".")
        signature_valid = (
            bool(separator)
            and len(sid) == 64
            and all(c in "0123456789abcdef" for c in sid)
            and hmac.compare_digest(signature, self._signature(app, sid))
        )
        if signature_valid:
            try:
                with database_connection(app.config["DATABASE_PATH"]) as db:
                    row = db.execute(
                        "SELECT data, expires_at FROM web_sessions WHERE sid = ?", (sid,)
                    ).fetchone()
                if row and row[1] > time.time():
                    return self.session_class(json.loads(row[0]), sid=sid)
            except sqlite3.OperationalError as error:
                if "no such table" not in str(error).lower():
                    app.logger.exception("Could not load the web session")
            except (sqlite3.Error, ValueError, TypeError):
                app.logger.exception("Could not load the web session")
        return self.session_class(sid=secrets.token_hex(32), new=True)

    def save_session(self, app, web_session, response):
        name = self.get_cookie_name(app)
        if not web_session:
            if web_session.sid and not web_session.new:
                with database_connection(app.config["DATABASE_PATH"]) as db:
                    db.execute("DELETE FROM web_sessions WHERE sid = ?", (web_session.sid,))
            response.delete_cookie(
                name, domain=self.get_cookie_domain(app), path=self.get_cookie_path(app),
                secure=self.get_cookie_secure(app), httponly=True, samesite="Lax",
            )
            return

        now = time.time()
        max_age = app.permanent_session_lifetime.total_seconds()
        expires_at = now + max_age
        with database_connection(app.config["DATABASE_PATH"]) as db:
            db.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (now,))
            db.execute(
                "INSERT INTO web_sessions (sid, data, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(sid) DO UPDATE SET data = excluded.data, expires_at = excluded.expires_at",
                (web_session.sid, json.dumps(dict(web_session)), expires_at),
            )
        response.set_cookie(
            name, f"{web_session.sid}.{self._signature(app, web_session.sid)}",
            max_age=int(max_age), httponly=True,
            secure=self.get_cookie_secure(app), samesite="Lax",
            domain=self.get_cookie_domain(app), path=self.get_cookie_path(app),
        )


@contextmanager
def database_connection(path):
    """Commit successful work and always release the SQLite connection."""
    db = sqlite3.connect(path)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.getenv("WAVEGUARD_SECRET_KEY"),
        DATABASE_PATH=os.getenv(
            "WAVEGUARD_DATABASE_PATH",
            str(Path(app.instance_path) / "waveguard.sqlite3"),
        ),
        SESSION_COOKIE_NAME="waveguard_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("WAVEGUARD_COOKIE_SECURE", "false").lower()
        in {"1", "true", "yes"},
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        DUMMY_PASSWORD_HASH=generate_password_hash(secrets.token_urlsafe(32)),
        MAX_CONTENT_LENGTH=128 * 1024,
    )
    app.session_interface = SQLiteSessionInterface()

    if (
        not app.config["SECRET_KEY"]
        or len(app.config["SECRET_KEY"]) < 32
        or app.config["SECRET_KEY"].startswith("replace-")
    ):
        raise RuntimeError(
            "Set WAVEGUARD_SECRET_KEY before starting WaveGuard. "
            "See README.md for local setup."
        )

    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect_db():
        with database_connection(app.config["DATABASE_PATH"]) as db:
            db.row_factory = sqlite3.Row
            yield db

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    def require_csrf():
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not secrets.compare_digest(expected, supplied):
            abort(400, description="The form expired. Reload the page and try again.")

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    @app.route("/")
    @login_required
    def home():
        return render_template("dashboard.html", username=session.get("username", ""))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("home"))
        if request.method == "POST":
            require_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            valid_input = 1 <= len(username) <= 80 and 1 <= len(password) <= 256
            user = None
            if valid_input:
                with connect_db() as db:
                    user = db.execute(
                        "SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE",
                        (username,),
                    ).fetchone()
            candidate_hash = (
                user["password_hash"] if user else app.config["DUMMY_PASSWORD_HASH"]
            )
            password_matches = check_password_hash(
                candidate_hash, password if len(password) <= 256 else ""
            )
            if user and valid_input and password_matches:
                old_sid = session.sid
                with connect_db() as db:
                    db.execute("DELETE FROM web_sessions WHERE sid = ?", (old_sid,))
                session.clear()
                session.sid = secrets.token_hex(32)
                session.new = True
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["csrf_token"] = secrets.token_urlsafe(32)
                session.permanent = True
                target = request.args.get("next", "")
                if (
                    target.startswith("/")
                    and not target.startswith("//")
                    and "\\" not in target
                ):
                    return redirect(target)
                return redirect(url_for("home"))
            flash("We couldn't sign you in with those details.", "error")
        return render_template("login.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if session.get("user_id"):
            return redirect(url_for("home"))
        if request.method == "POST":
            require_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not 1 <= len(username) <= 80 or any(ord(char) < 32 for char in username):
                flash("Choose a username between 1 and 80 characters.", "error")
            elif not 12 <= len(password) <= 256:
                flash("Use a password between 12 and 256 characters.", "error")
            else:
                try:
                    with connect_db() as db:
                        db.execute(
                            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                            (username, generate_password_hash(password)),
                        )
                    flash("Your account is ready. Sign in to continue.", "success")
                    return redirect(url_for("login"))
                except sqlite3.IntegrityError:
                    flash("That username is unavailable. Choose another.", "error")
        return render_template("signup.html")

    @app.post("/logout")
    @login_required
    def logout():
        require_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.route("/health")
    def health():
        return {
            "project": "WaveGuard",
            "status": "running",
            "mode": "offline simulation",
        }

    @app.cli.command("init-db")
    def init_db_command():
        """Create the local user and server-side session tables."""
        with connect_db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS web_sessions (
                    sid TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry
                    ON web_sessions(expires_at);
                """
            )
        click.echo("WaveGuard database initialized.")

    @app.cli.command("create-user")
    @click.argument("username")
    def create_user_command(username):
        """Create an account after running init-db; prompt for its password."""
        username = username.strip()
        if not 1 <= len(username) <= 80:
            raise click.ClickException("Username must be between 1 and 80 characters.")
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if not 12 <= len(password) <= 256:
            raise click.ClickException("Password must be between 12 and 256 characters.")
        try:
            with connect_db() as db:
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
        except sqlite3.IntegrityError:
            raise click.ClickException("That username is already in use.")
        click.echo("Account created.")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
