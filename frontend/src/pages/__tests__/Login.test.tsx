import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Login from "../Login";
import { makeMockContext, MockAppProvider, useMockAppContext } from "../../test/mockContext";

// Redirect the imports Login reaches for.
vi.mock("../../context/AppContext", () => ({
  useAppContext: () => useMockAppContext(),
}));
vi.mock("@react-oauth/google", () => ({
  useGoogleLogin: () => vi.fn(),
}));

function renderLogin(overrides: any = {}) {
  const ctx = makeMockContext(overrides);
  render(
    <MockAppProvider value={ctx}>
      <Login />
    </MockAppProvider>
  );
  return ctx;
}

describe("Login — sign-in mode", () => {
  it("calls login() and navigates to '/' on success", async () => {
    const ctx = renderLogin({
      login: vi.fn(async () => ({ success: true })),
    });
    await userEvent.type(screen.getByPlaceholderText("Email id"), "a@b.com");
    await userEvent.type(screen.getByPlaceholderText("Password"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /^login$/i }));

    expect(ctx.login).toHaveBeenCalledWith("a@b.com", "hunter2");
    expect(ctx.navigate).toHaveBeenCalledWith("/");
  });

  it("surfaces a server error message without navigating", async () => {
    const ctx = renderLogin({
      login: vi.fn(async () => ({ success: false, error: "Bad credentials" })),
    });
    await userEvent.type(screen.getByPlaceholderText("Email id"), "a@b.com");
    await userEvent.type(screen.getByPlaceholderText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /^login$/i }));

    expect(await screen.findByText("Bad credentials")).toBeInTheDocument();
    expect(ctx.navigate).not.toHaveBeenCalled();
  });
});

describe("Login — sign-up mode validation", () => {
  async function switchToSignup() {
    await userEvent.click(screen.getByRole("button", { name: /^sign up$/i }));
  }

  it("blocks submit when passwords don't match", async () => {
    const ctx = renderLogin();
    await switchToSignup();

    await userEvent.type(screen.getByPlaceholderText("Full Name"), "Ada");
    await userEvent.type(screen.getByPlaceholderText("Email id"), "ada@x.com");
    await userEvent.type(screen.getByPlaceholderText("Password"), "longenough");
    await userEvent.type(screen.getByPlaceholderText("Confirm Password"), "mismatch99");
    await userEvent.click(screen.getByRole("button", { name: /^sign up$/i }));

    expect(await screen.findByText(/Passwords do not match/i)).toBeInTheDocument();
    expect(ctx.register).not.toHaveBeenCalled();
  });

  it("blocks submit when password is under 6 characters", async () => {
    const ctx = renderLogin();
    await switchToSignup();

    await userEvent.type(screen.getByPlaceholderText("Full Name"), "Ada");
    await userEvent.type(screen.getByPlaceholderText("Email id"), "ada@x.com");
    await userEvent.type(screen.getByPlaceholderText("Password"), "short");
    await userEvent.type(screen.getByPlaceholderText("Confirm Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: /^sign up$/i }));

    expect(
      await screen.findByText(/Password must be at least 6 characters/i)
    ).toBeInTheDocument();
    expect(ctx.register).not.toHaveBeenCalled();
  });

  it("calls register() with full credentials when validation passes", async () => {
    const ctx = renderLogin({
      register: vi.fn(async () => ({ success: true })),
    });
    await switchToSignup();

    await userEvent.type(screen.getByPlaceholderText("Full Name"), "Ada");
    await userEvent.type(screen.getByPlaceholderText("Email id"), "ada@x.com");
    await userEvent.type(screen.getByPlaceholderText("Password"), "longenough");
    await userEvent.type(screen.getByPlaceholderText("Confirm Password"), "longenough");
    await userEvent.click(screen.getByRole("button", { name: /^sign up$/i }));

    expect(ctx.register).toHaveBeenCalledWith("Ada", "ada@x.com", "longenough");
    expect(ctx.navigate).toHaveBeenCalledWith("/");
  });
});
