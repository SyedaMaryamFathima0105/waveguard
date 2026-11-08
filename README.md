# WaveGuard

WaveGuard is an offline-first educational flood-monitoring demonstration. Its Flask website presents three simulated zones, a water-level trend, threshold alerts, and a recent-reading history. The readings are generated in the browser; this project does not connect to physical sensors and is not a real flood detection or public warning system.

## Requirements

- Windows 10/11
- Python 3.10 or newer available as `python` in PowerShell
- Internet access is needed for the optional Leaflet/OpenStreetMap map, Nominatim place search, and Google Fonts. The dashboard simulation continues to work when those services are unavailable.

## Install and configure

Open PowerShell in the project directory and create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy the example environment file, then replace its placeholder secret with a newly generated random value. Keep `.env` private; it is excluded from Git.

```powershell
Copy-Item .env.example .env
$secret = python -c "import secrets; print(secrets.token_hex(32))"
(Get-Content .env) -replace '^WAVEGUARD_SECRET_KEY=.*$', "WAVEGUARD_SECRET_KEY=$secret" | Set-Content -Encoding ascii .env
Remove-Variable secret
```

The project reads `.env` when Flask starts. `WAVEGUARD_DATABASE_PATH` is optional and defaults to `instance\waveguard.sqlite3`.

## Initialize the database and create an account

Create the local SQLite tables:

```powershell
python -m flask --app app init-db
```

Create an operator account. The command prompts for a password twice; passwords must be 12 to 256 characters and are stored as Werkzeug password hashes.

```powershell
python -m flask --app app create-user operator
```

The existing operator account remains in the same database. The sign-in page also links to public registration; accounts created there have ordinary user access and cannot grant themselves administrator privileges. Usernames are unique without regard to letter case. Back up the database securely if you need to retain accounts between machines.

## Run WaveGuard

```powershell
python app.py
```

Open <http://127.0.0.1:5001>. The existing local host and port are preserved. The dashboard redirects to sign-in until you authenticate. Use the account created above; choose **Sign out** in the top bar to end the session. Sessions expire after 30 minutes without activity and are stored server-side in the same SQLite database.

`/health` remains unauthenticated and returns the existing project, status, and simulation-mode fields. The dashboard is protected by a server-side session check.

## Location map and data sources

The dashboard map uses Leaflet and OpenStreetMap tiles. Place search sends a submitted query to the public Nominatim service; requests are only made after submission and are rate-spaced in the browser. These community services have availability and usage limits and require an internet connection. Map tiles include OpenStreetMap attribution. Browser location is requested only when the user presses **Use my location**, and the browser presents its permission prompt. A map click, search result, or coordinate is never treated as evidence of flooding.

WaveGuard currently has no configured official flood data feed. The location assessment therefore reports flood-risk data as unavailable. The water levels, trend, alerts, and history on the monitoring dashboard are simulated in the browser and are not tied to a selected map location. To provide location-specific assessment, configure an authoritative flood or gauge data source with documented coverage, timestamps, and an appropriate service agreement.

## Flood Scenario Simulator

The dashboard's **Flood Scenario Simulator** is a separate what-if demonstration. Choose one of the three zones and move the level slider from 0–50 cm. It uses the same existing 25 cm warning and 40 cm danger thresholds as the dashboard. Changing or resetting this scenario does not modify the running monitoring simulation, zone readings, graph, alerts, or history. Scenario results are illustrative and do not measure or predict real flood conditions.

## Cookie security and deployment

The session ID is random, stored server-side, and signed with `WAVEGUARD_SECRET_KEY`. The cookie is HttpOnly and SameSite=Lax. For local HTTP, leave `WAVEGUARD_COOKIE_SECURE=false`; for HTTPS deployment, set it to `true` so browsers send the cookie only over TLS. Use a new, private random secret per deployment, serve only over HTTPS, and do not expose Flask's development server directly to the internet. The app starts with debug mode disabled.

Login, registration, and logout submissions are protected by a per-session CSRF token. Login errors are generic, database statements are parameterized, and new user passwords are hashed with Werkzeug. The built-in server is intended for local demonstration use; production deployment should use a properly configured WSGI server and HTTPS reverse proxy.

## Tests

Run the new authentication and route checks from the project root:

```powershell
python -m unittest discover -s tests -v
```

Run the existing monitoring-engine tests from `core` (the existing test file is named `tesr_monitoring_engine.py`):

```powershell
Push-Location core
python -m unittest tesr_monitoring_engine -v
Pop-Location
```

The dashboard simulation remains in `static\js\dashboard.js`; it does not call or change the Python `MonitoringEngine`.

## Troubleshooting

- **`python` is not recognized:** install Python 3.10+ and enable the Python launcher/PATH option, then open a new PowerShell window. Alternatively replace `python` with `py -3` in the commands.
- **Secret key error:** confirm `.env` exists in the project root and `WAVEGUARD_SECRET_KEY` contains a generated value, not the example placeholder.
- **Database/table error:** run `python -m flask --app app init-db` before creating an account or signing in.
- **Cannot activate the virtual environment:** use `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if your Windows policy blocks locally created activation scripts, or call `\.venv\Scripts\python.exe` directly instead of activating it.
- **Port 5001 is in use:** stop the other local process using that port before starting WaveGuard.
