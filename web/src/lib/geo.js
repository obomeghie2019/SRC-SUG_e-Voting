// Browser location helpers. Geolocation only works on HTTPS pages (http://localhost is also allowed).

export function geoSupport() {
  if (!("geolocation" in navigator)) return { ok: false, reason: "This browser does not support location." };
  if (!window.isSecureContext) return { ok: false, reason: "Location needs a secure (HTTPS) connection. Open the site with https://." };
  return { ok: true };
}

// Resolves {latitude, longitude, accuracy_m} or rejects with an Error whose .code is "denied" | "unavailable" | "timeout"
export function getPosition({ maxAgeMs = 0 } = {}) {
  return new Promise((resolve, reject) => {
    const support = geoSupport();
    if (!support.ok) { const e = new Error(support.reason); e.code = "unsupported"; return reject(e); }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy_m: p.coords.accuracy }),
      (err) => {
        const map = { 1: ["denied", "Location is turned off for this site. Turn it ON in your browser settings, then try again."],
                      2: ["unavailable", "Your location could not be determined. Turn on GPS / location services and try again."],
                      3: ["timeout", "Finding your location took too long. Check your signal and try again."] };
        const [code, msg] = map[err.code] || ["unavailable", "Could not read your location."];
        const e = new Error(msg); e.code = code; reject(e);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: maxAgeMs }
    );
  });
}

// Calls cb(state) when the browser permission changes ("granted" | "denied" | "prompt"). Returns an unsubscribe fn.
export function watchPermission(cb) {
  let status;
  navigator.permissions?.query({ name: "geolocation" }).then((s) => {
    status = s; cb(s.state); s.onchange = () => cb(s.state);
  }).catch(() => {});
  return () => { if (status) status.onchange = null; };
}

// A random id kept in this browser; stored with the vote so the report can spot one device used by several voters.
export function deviceId() {
  let id = localStorage.getItem("device_id");
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/-/g, "");
    localStorage.setItem("device_id", id);
  }
  return id;
}
