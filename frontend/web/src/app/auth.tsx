import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { clearStoredToken, getStoredToken } from "../api/client";
import { login as loginRequest, logout as logoutRequest, me } from "../api/auth";
import type { UserRead } from "../types/api";

interface AuthContextValue {
  user: UserRead | null;
  isAdmin: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState(getStoredToken);
  const currentUser = useQuery({
    queryKey: ["auth-me", token],
    queryFn: me,
    enabled: Boolean(token),
    retry: false,
  });
  const user = currentUser.data ?? null;

  async function login(username: string, password: string) {
    const nextUser = await loginRequest(username, password);
    const nextToken = getStoredToken();
    setToken(nextToken);
    queryClient.setQueryData(["auth-me", nextToken], nextUser);
  }

  async function logout() {
    await logoutRequest();
    setToken("");
    queryClient.clear();
  }

  useEffect(() => {
    if (!currentUser.isError) {
      return;
    }
    clearStoredToken();
    setToken("");
    queryClient.removeQueries({ queryKey: ["auth-me"] });
  }, [currentUser.isError, queryClient]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAdmin: user?.role === "admin",
        isLoading: Boolean(token) && currentUser.isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
