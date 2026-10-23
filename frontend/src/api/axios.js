import axios from "axios";

export const API_ORIGIN = "http://localhost:8498";
const TOKEN_KEY = "hw7_access_token";

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token lives only for this page load */
  }
}

function withBearer(config) {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
}

// HW7: domain routes use JWT bearer auth (no session cookie).
const api = axios.create({ baseURL: `${API_ORIGIN}/api/hw4` });
api.interceptors.request.use(withBearer);

export const authApi = axios.create({ baseURL: `${API_ORIGIN}/auth` });
authApi.interceptors.request.use(withBearer);

export default api;
