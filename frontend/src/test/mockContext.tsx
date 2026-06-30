import { createContext, useContext, type ReactNode } from "react";
import { vi } from "vitest";
import type { AppContextValue } from "../context/AppContext";

// A re-export of the real AppContext would trigger `react-router`'s
// `useNavigate` (which needs a Router) every time we mount a consumer.
// Instead, re-export the same context-shape via a local provider and swap
// the import via vi.mock in the test file.

export function makeMockContext(
  overrides: Partial<AppContextValue> = {}
): AppContextValue {
  return {
    navigate: vi.fn(),
    user: null,
    setUser: vi.fn(),
    token: null,
    login: vi.fn(async () => ({ success: true })),
    register: vi.fn(async () => ({ success: true })),
    logout: vi.fn(),
    googleLogin: vi.fn(async () => ({ success: true })),
    chats: [],
    setChats: vi.fn(),
    selectedChat: null,
    setSelectedChat: vi.fn(),
    theme: "light",
    setTheme: vi.fn(),
    loading: false,
    fetchUserChats: vi.fn(async () => {}),
    createNewChat: vi.fn(async () => null),
    deleteChat: vi.fn(async () => true),
    updateChatInState: vi.fn(),
    refreshChat: vi.fn(async () => null),
    refreshUser: vi.fn(async () => {}),
    fetchDocuments: vi.fn(async () => []),
    deleteDocument: vi.fn(async () => true),
    submitFeedback: vi.fn(async () => true),
    startCheckout: vi.fn(async () => null),
    API_URL: "http://test",
    ...overrides,
  } as AppContextValue;
}

const MockAppContext = createContext<AppContextValue | undefined>(undefined);

export function MockAppProvider({
  value,
  children,
}: {
  value: AppContextValue;
  children: ReactNode;
}) {
  return (
    <MockAppContext.Provider value={value}>{children}</MockAppContext.Provider>
  );
}

export function useMockAppContext(): AppContextValue {
  const ctx = useContext(MockAppContext);
  if (!ctx) throw new Error("useMockAppContext must be used inside MockAppProvider");
  return ctx;
}
