"use strict";

const WARNING_LEVEL = 25;
const DANGER_LEVEL = 40;
const MAX_LEVEL = 50;
const READING_INTERVAL = 2000;

const initialZones = {
    "Road Zone": 20,
    "Underpass Zone": 15,
    "Drainage Zone": 10
};

let zones = {};
let monitoringTimer = null;
let readingHistory = [];

function resetZoneData() {
    zones = {};

    Object.entries(initialZones).forEach(([name, level]) => {
        zones[name] = {
            level: level,
            previous: level,
            history: [level]
        };
    });
}

const zoneSelect = document.getElementById("zoneSelect");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const resetBtn = document.getElementById("resetBtn");

const zoneName = document.getElementById("zoneName");
const waterLevel = document.getElementById("waterLevel");
const rateValue = document.getElementById("rateValue");
const statusText = document.getElementById("statusText");

const alertBox = document.getElementById("alertBox");
const alertTitle = document.getElementById("alertTitle");
const alertMessage = document.getElementById("alertMessage");

const historyTableBody = document.getElementById("historyTableBody");
const canvas = document.getElementById("simulationCanvas");
const ctx = canvas ? canvas.getContext("2d") : null;

function getCurrentZoneName() {
    return zoneSelect.value;
}

function getCurrentZone() {
    return zones[getCurrentZoneName()];
}

function getStatus(level) {
    if (level >= DANGER_LEVEL) return "DANGER";
    if (level >= WARNING_LEVEL) return "WARNING";
    return "NORMAL";
}

function checkReadingReliability(level) {
    if (level === null || level === undefined || level === "") {
        return {
            reliable: false,
            message: "Reading unavailable."
        };
    }

    if (typeof level !== "number" || !Number.isFinite(level)) {
        return {
            reliable: false,
            message: "Reading is not a valid number."
        };
    }

    if (level < 0 || level > MAX_LEVEL) {
        return {
            reliable: false,
            message: "Reading is outside the configured range."
        };
    }

    return {
        reliable: true,
        message: "Simulated reading passed basic validation."
    };
}

function updateReliability(level) {
    const statusElement = document.getElementById("reliabilityStatus");
    const messageElement = document.getElementById("reliabilityMessage");

    if (!statusElement || !messageElement) return;

    const result = checkReadingReliability(level);

    statusElement.textContent = result.reliable ? "VALID" : "INVALID";
    messageElement.textContent = result.message;

    statusElement.classList.remove("status-normal", "status-danger");
    statusElement.classList.add(
        result.reliable ? "status-normal" : "status-danger"
    );
}

function updateLastUpdated() {
    const element = document.getElementById("lastUpdated");

    if (element) {
        element.textContent = new Date().toLocaleTimeString();
    }
}

function updateAlert(status, level) {
    alertBox.classList.remove("warning", "danger");

    if (status === "DANGER") {
        alertBox.classList.add("danger");
        alertTitle.textContent = "Danger Level Reached";
        alertMessage.textContent =
            `The simulated water level in ${getCurrentZoneName()} is ${level} cm.`;
    } else if (status === "WARNING") {
        alertBox.classList.add("warning");
        alertTitle.textContent = "Warning Level Reached";
        alertMessage.textContent =
            `The simulated water level in ${getCurrentZoneName()} is ${level} cm.`;
    } else {
        alertTitle.textContent = monitoringTimer
            ? "Monitoring Active"
            : "System Ready";

        alertMessage.textContent = monitoringTimer
            ? "The local water-level simulation is running."
            : "Start monitoring to begin the water-level simulation.";
    }
}

function updateDashboard() {
    const zone = getCurrentZone();

    if (!zone) return;

    const status = getStatus(zone.level);

    document.querySelectorAll("[data-zone-card]").forEach(card => {
        const name = card.dataset.zoneCard;
        const zoneData = zones[name];
        if (!zoneData) return;

        const zoneStatus = getStatus(zoneData.level);
        const levelElement = card.querySelector("[data-zone-level]");
        const statusElement = card.querySelector("[data-zone-status]");
        const barElement = card.querySelector("[data-zone-bar]");

        if (levelElement) levelElement.textContent = zoneData.level;
        if (statusElement) {
            statusElement.textContent = zoneStatus;
            statusElement.classList.remove(
                "status-normal", "status-warning", "status-danger"
            );
            statusElement.classList.add(`status-${zoneStatus.toLowerCase()}`);
        }
        if (barElement) {
            barElement.style.width = `${(zoneData.level / MAX_LEVEL) * 100}%`;
            barElement.style.background = zoneStatus === "DANGER"
                ? "#ca5052"
                : zoneStatus === "WARNING"
                    ? "#c98722"
                    : "";
        }

        card.classList.toggle("selected", name === getCurrentZoneName());
        card.setAttribute(
            "aria-pressed",
            String(name === getCurrentZoneName())
        );
    });

    const systemState = document.getElementById("systemState");
    if (systemState) {
        systemState.textContent = monitoringTimer
            ? "Monitoring active"
            : "System ready";
    }

    zoneName.textContent = getCurrentZoneName();
    waterLevel.textContent = zone.level;
    rateValue.textContent = zone.level - zone.previous;

    statusText.textContent = status;
    statusText.classList.remove(
        "status-normal",
        "status-warning",
        "status-danger"
    );

    if (status === "DANGER") {
        statusText.classList.add("status-danger");
    } else if (status === "WARNING") {
        statusText.classList.add("status-warning");
    } else {
        statusText.classList.add("status-normal");
    }

    updateReliability(zone.level);
    updateAlert(status, zone.level);
    drawGraph(zone.history);
}

function drawGraph(history) {
    if (!canvas || !ctx) return;

    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    if (!width || !height) return;

    const pixelRatio = window.devicePixelRatio || 1;

    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);

    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const padding = {
        top: 20,
        right: 20,
        bottom: 35,
        left: 42
    };

    const graphWidth = width - padding.left - padding.right;
    const graphHeight = height - padding.top - padding.bottom;

    function xPosition(index) {
        if (history.length <= 1) {
            return padding.left + graphWidth / 2;
        }

        return padding.left +
            (index / (history.length - 1)) * graphWidth;
    }

    function yPosition(level) {
        return padding.top +
            graphHeight - (level / MAX_LEVEL) * graphHeight;
    }

    ctx.font = "11px Arial";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (let level = 0; level <= MAX_LEVEL; level += 10) {
        const y = yPosition(level);

        ctx.beginPath();
        ctx.strokeStyle = "#e8edf3";
        ctx.lineWidth = 1;
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        ctx.fillStyle = "#738195";
        ctx.fillText(String(level), padding.left - 10, y);
    }

    ctx.save();
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1;

    ctx.strokeStyle = "#d88b13";
    ctx.beginPath();
    ctx.moveTo(padding.left, yPosition(WARNING_LEVEL));
    ctx.lineTo(width - padding.right, yPosition(WARNING_LEVEL));
    ctx.stroke();

    ctx.strokeStyle = "#d94747";
    ctx.beginPath();
    ctx.moveTo(padding.left, yPosition(DANGER_LEVEL));
    ctx.lineTo(width - padding.right, yPosition(DANGER_LEVEL));
    ctx.stroke();
    ctx.restore();

    ctx.strokeStyle = "#13a89e";
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();

    history.forEach((level, index) => {
        const x = xPosition(index);
        const y = yPosition(level);

        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    });

    ctx.stroke();

    history.forEach((level, index) => {
        ctx.beginPath();
        ctx.fillStyle = "#13a89e";
        ctx.arc(xPosition(index), yPosition(level), 3.5, 0, Math.PI * 2);
        ctx.fill();
    });

    ctx.fillStyle = "#738195";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText("Reading history", width / 2, height - 23);
}

function recordReading() {
    const zone = getCurrentZone();
    readingHistory.unshift({
        time: new Date().toLocaleTimeString(),
        zone: getCurrentZoneName(),
        level: zone.level,
        status: getStatus(zone.level)
    });

    if (readingHistory.length > 50) {
        readingHistory.pop();
    }

    renderHistory();
}

function renderHistory() {
    if (!historyTableBody) return;

    historyTableBody.replaceChildren();

    if (readingHistory.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 4;
        cell.className = "empty-history";
        cell.textContent =
            "No readings yet. Start monitoring to record readings.";

        row.appendChild(cell);
        historyTableBody.appendChild(row);
        return;
    }

    readingHistory.forEach(entry => {
        const row = document.createElement("tr");

        [
            entry.time,
            entry.zone,
            `${entry.level} cm`,
            entry.status
        ].forEach((value, index) => {
            const cell = document.createElement("td");
            cell.textContent = value;
            if (index === 3) {
                cell.classList.add(
                    "history-status",
                    `status-${entry.status.toLowerCase()}`
                );
            }
            row.appendChild(cell);
        });

        historyTableBody.appendChild(row);
    });
}

function simulateReading() {
    const zone = getCurrentZone();

    zone.previous = zone.level;

    if (zone.level < MAX_LEVEL) {
        zone.level = Math.min(zone.level + 1, MAX_LEVEL);
    }

    zone.history.push(zone.level);

    if (zone.history.length > 30) {
        zone.history.shift();
    }

    recordReading();
    updateLastUpdated();
    updateDashboard();

    if (zone.level >= MAX_LEVEL) {
        stopMonitoring();

        alertTitle.textContent = "Simulation Limit Reached";
        alertMessage.textContent =
            "The demonstration has reached its maximum simulated water level.";
    }
}

function startMonitoring() {
    if (monitoringTimer !== null) return;

    simulateReading();

    if (getCurrentZone().level >= MAX_LEVEL) return;

    monitoringTimer = setInterval(
        simulateReading,
        READING_INTERVAL
    );

    updateDashboard();
}

function stopMonitoring() {
    if (monitoringTimer !== null) {
        clearInterval(monitoringTimer);
        monitoringTimer = null;
    }

    updateDashboard();
}

function resetMonitoring() {
    stopMonitoring();
    resetZoneData();

    readingHistory = [];

    const lastUpdatedElement = document.getElementById("lastUpdated");

    if (lastUpdatedElement) {
        lastUpdatedElement.textContent = "Waiting";
    }

    renderHistory();
    updateDashboard();
}

startBtn.addEventListener("click", startMonitoring);
stopBtn.addEventListener("click", stopMonitoring);
resetBtn.addEventListener("click", resetMonitoring);

zoneSelect.addEventListener("change", updateDashboard);
window.addEventListener("resize", updateDashboard);

document.querySelectorAll("[data-zone-card]").forEach(card => {
    card.addEventListener("click", () => {
        zoneSelect.value = card.dataset.zoneCard;
        updateDashboard();
    });
    card.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            zoneSelect.value = card.dataset.zoneCard;
            updateDashboard();
        }
    });
});

resetZoneData();
renderHistory();
updateDashboard();

// Location selection never changes the demonstration readings above.
const mapElement = document.getElementById("locationMap");
if (mapElement) {
    const mapMessage = document.getElementById("mapMessage");
    const locationName = document.getElementById("selectedLocationName");
    const coordinatesText = document.getElementById("selectedCoordinates");
    let marker = null;
    let map = null;
    let lastSearchAt = 0;
    const setMapMessage = message => { mapMessage.textContent = message; };
    const selectLocation = (lat, lon, name = "Selected map location") => {
        if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
            setMapMessage("Enter a valid latitude (−90 to 90) and longitude (−180 to 180).");
            return;
        }
        if (map) {
            if (!marker) marker = L.marker([lat, lon], { draggable: true }).addTo(map);
            marker.setLatLng([lat, lon]);
            map.setView([lat, lon], Math.max(map.getZoom(), 12));
            marker.off("dragend");
            marker.on("dragend", () => {
                const point = marker.getLatLng();
                selectLocation(point.lat, point.lng, "Selected map location");
            });
        }
        locationName.textContent = name;
        coordinatesText.textContent = `Latitude ${lat.toFixed(5)} · Longitude ${lon.toFixed(5)}`;
        document.getElementById("latitudeInput").value = lat.toFixed(6);
        document.getElementById("longitudeInput").value = lon.toFixed(6);
        document.getElementById("riskStatus").textContent = "Location selected — flood risk data unavailable";
        setMapMessage("Location selected. No live flood measurement is available for this point.");
    };

    const showMapUnavailable = () => {
        mapElement.classList.add("map-unavailable");
        mapElement.textContent = "The map library could not load. You can still search for a place or enter coordinates below.";
        setMapMessage("Map unavailable. Check your connection; place search and coordinates may still work.");
    };
    let mapInitialized = false;
    const initializeMap = () => {
        if (mapInitialized || !window.L) return;
        try {
            mapElement.replaceChildren();
            map = window.L.map(mapElement, { scrollWheelZoom: false }).setView([20, 0], 2);
            window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                maxZoom: 19,
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
            }).addTo(map);
            map.on("click", event => selectLocation(event.latlng.lat, event.latlng.lng));
            mapInitialized = true;
            mapElement.classList.remove("map-unavailable");
            setMapMessage("Map ready. Click the map, search for a place, or enter coordinates.");
            requestAnimationFrame(() => map.invalidateSize());
        } catch (error) {
            console.error("WaveGuard map initialization failed:", error);
            showMapUnavailable();
        }
    };
    const leafletScript = document.getElementById("leafletScript");
    if (window.L) {
        initializeMap();
    } else if (leafletScript) {
        leafletScript.addEventListener("load", initializeMap, { once: true });
        leafletScript.addEventListener("error", showMapUnavailable, { once: true });
    } else {
        showMapUnavailable();
    }

    document.getElementById("placeSearchForm").addEventListener("submit", async event => {
        event.preventDefault();
        const submitButton = event.currentTarget.querySelector("button[type='submit']");
        if (submitButton.disabled) return;
        const query = document.getElementById("placeSearch").value.trim();
        if (query.length < 2) { setMapMessage("Enter at least two characters to search."); return; }
        submitButton.disabled = true;
        try {
            const wait = Math.max(0, 1100 - (Date.now() - lastSearchAt));
            if (wait) await new Promise(resolve => setTimeout(resolve, wait));
            lastSearchAt = Date.now();
            setMapMessage("Searching OpenStreetMap…");
            const response = await fetch(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=${encodeURIComponent(query)}`, { headers: { Accept: "application/json" } });
            if (response.status === 429) throw new Error("Search limit reached. Wait a moment before trying again.");
            if (!response.ok) throw new Error("The place search service is unavailable right now.");
            const results = await response.json();
            if (!results.length) { setMapMessage("No matching place found. Try a nearby city or a more specific address."); return; }
            selectLocation(Number(results[0].lat), Number(results[0].lon), results[0].display_name || query);
        } catch (error) {
            setMapMessage(error.message || "Could not reach place search. You can select a point or enter coordinates manually.");
        } finally {
            submitButton.disabled = false;
        }
    });

    document.getElementById("setCoordinatesBtn").addEventListener("click", () => {
        const lat = Number(document.getElementById("latitudeInput").value);
        const lon = Number(document.getElementById("longitudeInput").value);
        if (document.getElementById("latitudeInput").value === "" || document.getElementById("longitudeInput").value === "") {
            setMapMessage("Enter both latitude and longitude."); return;
        }
        selectLocation(lat, lon, "Manually entered location");
    });

    document.getElementById("locateMeBtn").addEventListener("click", () => {
        if (!navigator.geolocation) { setMapMessage("This browser does not provide location access."); return; }
        setMapMessage("Waiting for your browser location permission…");
        navigator.geolocation.getCurrentPosition(
            position => selectLocation(position.coords.latitude, position.coords.longitude, "Your selected location"),
            error => setMapMessage(error.code === error.PERMISSION_DENIED ? "Location permission was denied. You can choose a point manually." : "Could not get your location. Check browser permissions and try again."),
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
        );
    });
}

// Isolated what-if controls: these never mutate zones or readingHistory.
const scenarioZone = document.getElementById("scenarioZone");
const scenarioLevel = document.getElementById("scenarioLevel");
const scenarioOutput = document.getElementById("scenarioLevelOutput");
const scenarioStatus = document.getElementById("scenarioStatus");
const scenarioExplanation = document.getElementById("scenarioExplanation");
const scenarioBar = document.getElementById("scenarioBar");

function updateScenario() {
    if (!scenarioZone || !scenarioLevel) return;

    const zone = scenarioZone.value;
    const level = Number(scenarioLevel.value);
    const status = getStatus(level);
    scenarioOutput.textContent = `${level} cm`;
    document.getElementById("scenarioZoneName").textContent = zone;
    scenarioStatus.textContent = status;
    scenarioStatus.classList.remove("status-normal", "status-warning", "status-danger");
    scenarioStatus.classList.add(`status-${status.toLowerCase()}`);

    if (status === "DANGER") {
        scenarioExplanation.textContent = `${level} cm is at or above the ${DANGER_LEVEL} cm danger threshold.`;
    } else if (status === "WARNING") {
        scenarioExplanation.textContent = `${level} cm has reached the ${WARNING_LEVEL} cm warning threshold and remains below danger at ${DANGER_LEVEL} cm.`;
    } else {
        scenarioExplanation.textContent = `${level} cm is below the ${WARNING_LEVEL} cm warning threshold.`;
    }

    scenarioBar.style.width = `${(level / MAX_LEVEL) * 100}%`;
    scenarioBar.classList.remove("warning", "danger");
    if (status === "WARNING") scenarioBar.classList.add("warning");
    if (status === "DANGER") scenarioBar.classList.add("danger");
    scenarioLevel.setAttribute("aria-valuetext", `${level} centimeters, ${status.toLowerCase()} scenario`);
}

if (scenarioZone && scenarioLevel) {
    scenarioLevel.addEventListener("input", updateScenario);
    scenarioZone.addEventListener("change", () => {
        scenarioLevel.value = initialZones[scenarioZone.value];
        updateScenario();
    });
    document.getElementById("resetScenarioBtn").addEventListener("click", () => {
        scenarioLevel.value = initialZones[scenarioZone.value];
        updateScenario();
    });
    updateScenario();
}
