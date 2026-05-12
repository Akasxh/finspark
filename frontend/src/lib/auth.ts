/**
 * Auth state management — tokens and current user stored in localStorage.
 */

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: string;
  tenant_id: string;
}

const ACCESS_KEY = "fs_access_token";
const REFRESH_KEY = "fs_refresh_token";
const USER_KEY = "fs_user";

export function getToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function setUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * Decode the payload of a JWT without verifying the signature.
 * Security relies on server-side validation; this is only for client-side
 * expiry checks to avoid sending expired tokens.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // Base64url -> Base64 -> decode
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(base64);
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;

  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return false;

  // Reject if token expired (compare against current UTC epoch seconds)
  return payload.exp > Date.now() / 1000;
}
