import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { apiAuth, type User } from "./api";

export type AuthModalMode = "signin" | "register";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAuthModalOpen: boolean;
  authModalMode: AuthModalMode;
  openAuthModal: (mode?: AuthModalMode) => void;
  closeAuthModal: () => void;
  login: (usernameOrEmail: string, password: string) => Promise<User>;
  register: (username: string, email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  updateDisplayName: (name: string) => Promise<void>;
  updatePassword: (oldPw: string, newPw: string) => Promise<void>;
  updatePhoto: (file: File) => Promise<string>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState<AuthModalMode>("signin");

  const openAuthModal = useCallback((mode: AuthModalMode = "signin") => {
    setAuthModalMode(mode);
    setIsAuthModalOpen(true);
  }, []);

  const closeAuthModal = useCallback(() => {
    setIsAuthModalOpen(false);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const res = await apiAuth.me();
      if (res.ok && res.user) {
        setUser(res.user);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (usernameOrEmail: string, password: string): Promise<User> => {
    const res = await apiAuth.login(usernameOrEmail, password);
    setUser(res.user);
    setIsAuthModalOpen(false);
    return res.user;
  };

  const register = async (username: string, email: string, password: string): Promise<User> => {
    const res = await apiAuth.register(username, email, password);
    setUser(res.user);
    setIsAuthModalOpen(false);
    return res.user;
  };

  const logout = async (): Promise<void> => {
    await apiAuth.logout();
    setUser(null);
  };

  const updateDisplayName = async (name: string): Promise<void> => {
    const res = await apiAuth.changeName(name);
    if (res.user) {
      setUser(res.user);
    } else if (user) {
      setUser({ ...user, display_name: res.display_name });
    }
  };

  const updatePassword = async (oldPw: string, newPw: string): Promise<void> => {
    await apiAuth.changePassword(oldPw, newPw);
  };

  const updatePhoto = async (file: File): Promise<string> => {
    const res = await apiAuth.changePhoto(file);
    if (res.user) {
      setUser(res.user);
    } else if (user) {
      setUser({ ...user, avatar_url: res.avatar_url });
    }
    return res.avatar_url;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        isAuthModalOpen,
        authModalMode,
        openAuthModal,
        closeAuthModal,
        login,
        register,
        logout,
        refreshUser,
        updateDisplayName,
        updatePassword,
        updatePhoto,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
