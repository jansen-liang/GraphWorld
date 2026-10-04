import { clearStoredToken, requestJson, setStoredToken } from "./client";
import type { LoginResponse, UserRead } from "../types/api";

export async function login(username: string, password: string) {
  const response = await requestJson<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setStoredToken(response.access_token);
  return response.user;
}

export function me() {
  return requestJson<UserRead>("/auth/me");
}

export async function logout() {
  try {
    await requestJson<void>("/auth/logout", { method: "POST" });
  } finally {
    clearStoredToken();
  }
}
