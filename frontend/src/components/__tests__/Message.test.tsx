import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Message from "../Message";
import { makeMockContext, MockAppProvider, useMockAppContext } from "../../test/mockContext";

// Redirect Message's `useAppContext` import to our mock provider so tests
// don't need a full AppContextProvider (which requires a Router).
vi.mock("../../context/AppContext", () => ({
  useAppContext: () => useMockAppContext(),
}));

// Prism is lazy-imported by Message for syntax highlighting. jsdom can't run
// it and we don't care about the output in unit tests.
vi.mock("prismjs", () => ({
  default: { highlightAll: vi.fn() },
}));

const baseUser = { _id: "u1", email: "u@x", name: "U", credits: 99 };

function renderMessage(message: any, chatId = "c1", ctxOverrides: any = {}) {
  const ctx = makeMockContext({ user: baseUser, ...ctxOverrides });
  render(
    <MockAppProvider value={ctx}>
      <Message message={message} chatId={chatId} />
    </MockAppProvider>
  );
  return ctx;
}

describe("Message — user role", () => {
  it("renders attached filenames as chips", () => {
    renderMessage({
      role: "user",
      content: "look at these",
      timestamp: Date.now(),
      files: ["a.pdf", "b.docx"],
    });
    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    expect(screen.getByText("b.docx")).toBeInTheDocument();
  });

  it("shows the message content text", () => {
    renderMessage({ role: "user", content: "hi there", timestamp: Date.now() });
    expect(screen.getByText("hi there")).toBeInTheDocument();
  });
});

describe("Message — assistant role with sources", () => {
  it("renders each source as a citation chip", () => {
    renderMessage({
      role: "assistant",
      content: "Here is the answer.",
      timestamp: Date.now(),
      sources: ["notes.pdf", "spec.md"],
    });
    // Sources appear after the "Sources:" label.
    expect(screen.getByText("Sources:")).toBeInTheDocument();
    expect(screen.getByText(/notes\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/spec\.md/)).toBeInTheDocument();
  });

  it("omits the Sources block when the list is empty", () => {
    renderMessage({
      role: "assistant",
      content: "No context needed",
      timestamp: Date.now(),
      sources: [],
    });
    expect(screen.queryByText("Sources:")).not.toBeInTheDocument();
  });
});

describe("Message — feedback voting", () => {
  it("calls submitFeedback with rating=1 when thumbs-up is clicked", async () => {
    const ctx = renderMessage({
      role: "assistant",
      content: "ok",
      timestamp: 12345,
      sources: [],
    });
    await userEvent.click(screen.getByTitle("Helpful"));
    expect(ctx.submitFeedback).toHaveBeenCalledWith({
      chatId: "c1",
      messageTimestamp: 12345,
      rating: 1,
    });
  });

  it("toggles a previously-set rating back to 0 when clicked again", async () => {
    const ctx = renderMessage({
      role: "assistant",
      content: "ok",
      timestamp: 7777,
      sources: [],
      rating: 1,
    });
    await userEvent.click(screen.getByTitle("Helpful"));
    expect(ctx.submitFeedback).toHaveBeenCalledWith({
      chatId: "c1",
      messageTimestamp: 7777,
      rating: 0,
    });
  });

  it("hides vote buttons when no user is logged in", () => {
    renderMessage(
      { role: "assistant", content: "ok", timestamp: 1, sources: [] },
      "c1",
      { user: null }
    );
    expect(screen.queryByTitle("Helpful")).not.toBeInTheDocument();
    expect(screen.queryByTitle("Not helpful")).not.toBeInTheDocument();
  });
});
