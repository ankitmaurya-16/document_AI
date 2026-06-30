import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppContextProvider, useAppContext } from "../AppContext";

// A tiny consumer that exposes the context surface through DOM nodes so the
// test can drive it with userEvent and assert rendered state.
function Harness() {
  const { user, token, login, register, logout } = useAppContext();
  return (
    <div>
      <div data-testid="user">{user ? (user as any).email : "none"}</div>
      <div data-testid="token">{token ?? "none"}</div>
      <button onClick={() => login("a@b.com", "pw")}>login</button>
      <button onClick={() => register("Ada", "a@b.com", "pw")}>register</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

function wrap(ui: React.ReactNode) {
  return (
    <MemoryRouter>
      <AppContextProvider>{ui}</AppContextProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  // AppContext boots `verifyAuth()`; when no token exists, it short-circuits
  // without fetching. The login/register tests still need fetch to exist.
  global.fetch = vi.fn();
});

describe("AppContext — login", () => {
  it("stores token and user on success", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        token: "jwt-123",
        user: { _id: "u1", email: "a@b.com", name: "A", credits: 10 },
      }),
    });

    render(wrap(<Harness />));
    await userEvent.click(screen.getByText("login"));

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    expect(screen.getByTestId("token")).toHaveTextContent("jwt-123");
    expect(localStorage.getItem("token")).toBe("jwt-123");
  });

  it("leaves state unchanged on failure", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "bad creds" }),
    });

    render(wrap(<Harness />));
    await userEvent.click(screen.getByText("login"));

    // Give the failed promise time to resolve; state should remain empty.
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(localStorage.getItem("token")).toBeNull();
  });
});

describe("AppContext — register", () => {
  it("stores token and user on successful register", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        token: "jwt-reg",
        user: { _id: "u2", email: "a@b.com", name: "Ada", credits: 100 },
      }),
    });

    render(wrap(<Harness />));
    await userEvent.click(screen.getByText("register"));

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("a@b.com"));
    expect(screen.getByTestId("token")).toHaveTextContent("jwt-reg");
  });
});

describe("AppContext — logout", () => {
  it("clears token and user and removes the stored JWT", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        token: "jwt-x",
        user: { _id: "u", email: "e@x", name: "E", credits: 1 },
      }),
    });

    render(wrap(<Harness />));
    await userEvent.click(screen.getByText("login"));
    await waitFor(() => expect(localStorage.getItem("token")).toBe("jwt-x"));

    await userEvent.click(screen.getByText("logout"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(localStorage.getItem("token")).toBeNull();
  });
});

describe("useAppContext — guard", () => {
  it("throws when used outside the provider", () => {
    // Silence the inevitable error log from React's error boundary output.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    function Bad() {
      useAppContext();
      return null;
    }
    expect(() =>
      act(() => {
        render(<Bad />);
      })
    ).toThrow(/useAppContext must be used inside AppContextProvider/);

    spy.mockRestore();
  });
});
