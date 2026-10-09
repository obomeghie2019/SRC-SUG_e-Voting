import axios from "axios";

// Web app talks ONLY to the web API (/api/web). Mobile has its own API folder and URL.
const api = axios.create({ baseURL: (import.meta.env.VITE_API_URL || "") + "/api/web" });

api.interceptors.request.use((cfg) => {
  const key = cfg.url.startsWith("/admin") ? "admin_token" : "voter_token";
  const token = sessionStorage.getItem(key);
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

export const errMsg = (e, fallback = "Something went wrong. Try again.") => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
};

export default api;
