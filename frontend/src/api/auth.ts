import axios from "axios";

const canonicalizeLoopbackUrl = (rawUrl?: string) => {
  if (!rawUrl) return "http://localhost:8000";
  try {
    const url = new URL(rawUrl);
    if (url.hostname === "127.0.0.1") {
      url.hostname = "localhost";
    }
    return url.toString().replace(/\/$/, "");
  } catch {
    return rawUrl.replace(/\/$/, "");
  }
};

export const API_BASE_URL = canonicalizeLoopbackUrl(import.meta.env.VITE_API_URL);

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // ← sends HttpOnly cookies automatically on every request
});

let refreshPromise: Promise<string> | null = null;
let redirectingToLogin = false;

const clearSessionAndRedirectToLogin = () => {
  if (redirectingToLogin) return;
  redirectingToLogin = true;
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("full_name");
  window.location.href = "/login?session=expired";
};

const isRefreshableRequest = (url?: string) => {
  if (!url) return false;
  return !(
    url.includes("/auth/login") ||
    url.includes("/auth/register") ||
    url.includes("/auth/verify-email") ||
    url.includes("/auth/forgot-password") ||
    url.includes("/auth/reset-password") ||
    url.includes("/auth/refresh") ||
    url.includes("/auth/github")
  );
};

// ── Automatically attach access token from localStorage to every request ──────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (config.data instanceof FormData) {
    const headers = config.headers as Record<string, string> & { delete?: (header: string) => unknown };
    if (typeof headers.delete === "function") {
      headers.delete("Content-Type");
      headers.delete("content-type");
    } else {
      delete headers["Content-Type"];
      delete headers["content-type"];
    }
  }
  return config;
});

// ── Auto-refresh if 401 received ──────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (!original || error.response?.status !== 401) {
      return Promise.reject(error);
    }

    if (!isRefreshableRequest(original.url) || original._retry) {
      return Promise.reject(error);
    }

    original._retry = true;

    try {
      if (!refreshPromise) {
        refreshPromise = api.post("/auth/refresh")
          .then((res) => {
            const newToken = res.data?.access_token;
            if (!newToken) throw new Error("No refreshed access token");
            localStorage.setItem("token", newToken);
            return newToken;
          })
          .finally(() => {
            refreshPromise = null;
          });
      }

      const newToken = await refreshPromise;
      original.headers = original.headers || {};
      original.headers.Authorization = `Bearer ${newToken}`;
      return api(original); // retry original request once
    } catch {
      clearSessionAndRedirectToLogin();
      return Promise.reject(error);
    }

    return Promise.reject(error);
  }
);

// ── Login ─────────────────────────────────────────────────────────────────────
export const login = async (credentials: {
  username: string;
  password: string;
}) => {
  const response = await api.post("/auth/login", credentials);
  return response.data;
};

// ── Whoami ────────────────────────────────────────────────────────────────────
export const whoami = async () => {
  const response = await api.get("/auth/whoami");
  return response.data; // { id, username, role }
};

// ── Logout ────────────────────────────────────────────────────────────────────
export const logout = async () => {
  try {
    await api.post("/auth/logout");
  } catch (_) {
    // clear anyway
  } finally {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("full_name");
    window.location.href = "/login";
  }
};

// ── Refresh ───────────────────────────────────────────────────────────────────
export const refreshToken = async () => {
  const response = await api.post("/auth/refresh");
  if (response.data.access_token) {
    localStorage.setItem("token", response.data.access_token);
  }
  return response.data;
};

// ── Register ──────────────────────────────────────────────────────────────────
export const register = async (data: {
  username: string;
  full_name: string;
  work_email: string;
  role: string;
  password: string;
  specialization?: string;
}) => {
  const response = await api.post("/auth/register", data);
  return response.data;
};

// ── Verify Email ──────────────────────────────────────────────────────────────
export const verifyEmail = async (data: {
  work_email: string;
  code: string;
}) => {
  const response = await api.post("/auth/verify-email", data);
  return response.data;
};

// ── Forgot Password ──────────────────────────────────────────────────────────
export const forgotPassword = async (data: { email: string }) => {
  const response = await api.post("/auth/forgot-password", data);
  return response.data;
};

// ── Reset Password ───────────────────────────────────────────────────────────
export const resetPassword = async (data: {
  token: string;
  new_password: string;
}) => {
  const response = await api.post("/auth/reset-password", data);
  return response.data;
};

export default api;
