import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ChatBox from "../ChatBox";
import { makeMockContext, MockAppProvider, useMockAppContext } from "../../test/mockContext";

vi.mock("../../context/AppContext", () => ({
  useAppContext: () => useMockAppContext(),
}));
// Message lazy-loads prismjs; stub it so the DOM stays quiet.
vi.mock("prismjs", () => ({ default: { highlightAll: vi.fn() } }));

function renderChatBox(overrides: any = {}) {
  const ctx = makeMockContext({
    user: { _id: "u1", email: "u@x", name: "U", credits: 5 },
    token: "t",
    API_URL: "http://test",
    ...overrides,
  });
  render(
    <MockAppProvider value={ctx}>
      <ChatBox />
    </MockAppProvider>
  );
  return ctx;
}

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("ChatBox — text-only prompt flow", () => {
  it("posts to /api/v1/chat and appends the assistant reply", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        response: "Hello from assistant",
        sources: ["doc.pdf"],
        chatId: "c1",
      }),
    });

    const ctx = renderChatBox();
    await userEvent.type(screen.getByPlaceholderText("Type a message..."), "hi");
    await userEvent.click(screen.getByAltText("send"));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const [url, init] = (fetch as any).mock.calls[0];
    expect(url).toBe("http://test/api/v1/chat");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer t");
    const body = JSON.parse(init.body);
    expect(body.prompt).toBe("hi");

    expect(await screen.findByText("Hello from assistant")).toBeInTheDocument();
    // chatId came back → context refresh hooks should fire.
    await waitFor(() => {
      expect(ctx.fetchUserChats).toHaveBeenCalled();
      expect(ctx.refreshUser).toHaveBeenCalled();
    });
  });

  it("shows the credits-exhausted notice without throwing", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ credits_exhausted: true, error: "no credits" }),
    });

    renderChatBox();
    await userEvent.type(screen.getByPlaceholderText("Type a message..."), "hi");
    await userEvent.click(screen.getByAltText("send"));

    expect(
      await screen.findByText(/Credits exhausted/i)
    ).toBeInTheDocument();
  });

  it("falls back to a generic error message when fetch rejects", async () => {
    (fetch as any).mockRejectedValueOnce(new Error("network down"));
    // Silence the console.error from the component's catch branch.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    renderChatBox();
    await userEvent.type(screen.getByPlaceholderText("Type a message..."), "hi");
    await userEvent.click(screen.getByAltText("send"));

    expect(
      await screen.findByText(/Something went wrong/i)
    ).toBeInTheDocument();
    spy.mockRestore();
  });
});

describe("ChatBox — input guards", () => {
  it("does not fire when prompt is empty and no files attached", async () => {
    renderChatBox();
    // The send button is disabled in this state; click is a no-op, fetch shouldn't run.
    await userEvent.click(screen.getByAltText("send"));
    expect(fetch).not.toHaveBeenCalled();
  });
});
