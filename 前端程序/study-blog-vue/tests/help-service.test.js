import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/services/auth", () => ({ request: vi.fn() }));

import { request } from "../src/services/auth";
import {
  createHelpRequest,
  getHelpChatLine,
  listHelpChatLines,
  messagesOf,
  subscribeToHelpChatEvents,
} from "../src/services/help";

describe("student help service", () => {
  beforeEach(() => request.mockReset());

  it("uses the frozen paginated chat-line contract", async () => {
    request.mockResolvedValue({ items: [] });
    await listHelpChatLines();
    expect(request).toHaveBeenCalledWith(
      "/api/student/help-chat-lines?page=1&page_size=20&sort=-last_message_at%2C-id",
    );
    await getHelpChatLine(7);
    expect(request).toHaveBeenLastCalledWith("/api/student/help-chat-lines/7");
  });

  it("sends only public context fields and keeps context_key server-owned", async () => {
    request.mockResolvedValue({ chat_line_id: 3 });
    await createHelpRequest(
      {
        class_id: 9,
        body: "我不明白循环为什么停不下来",
        context_type: "attempt",
        context_id: 12,
        context_source: "lesson_attempt",
        problem_id_no: "PY-7",
        problem_id_no: "PY-7",
        context_key: "must-not-leave-browser",
        assigned_admin_user_id: 88,
      },
      { requestKey: "stable-retry-key" },
    );

    expect(request).toHaveBeenCalledWith("/api/student/help-requests", {
      method: "POST",
      headers: { "Idempotency-Key": "stable-retry-key" },
      body: JSON.stringify({
        class_id: 9,
        body: "我不明白循环为什么停不下来",
        context_type: "attempt",
        context_id: 12,
        context_source: "lesson_attempt",
        problem_id_no: "PY-7",
      }),
    });
  });

  it("reads messages from the server-owned detail contract", () => {
    expect(messagesOf({ messages: [{ id: 2 }, { id: 1 }] }).map((item) => item.id)).toEqual([2, 1]);
  });

  it("uses a one-time subprotocol ticket and retries without a visible error", async () => {
    const sockets = [];
    class FakeWebSocket {
      static OPEN = 1;

      constructor(url, protocols) {
        this.url = url;
        this.protocols = protocols;
        this.readyState = FakeWebSocket.OPEN;
        sockets.push(this);
      }

      close() {}
    }
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("window", {
      location: { protocol: "https:", host: "study.example.test" },
      setTimeout,
      clearTimeout,
    });
    request.mockResolvedValue({ ticket: "single-use-ticket" });
    const onChange = vi.fn();

    const unsubscribe = subscribeToHelpChatEvents(onChange);
    await vi.waitFor(() => expect(sockets).toHaveLength(1));

    expect(request).toHaveBeenCalledWith("/api/student/help-chat-lines/events/ticket", {
      method: "POST",
    });
    expect(sockets[0].protocols).toEqual(["help-v1", "help-ticket.single-use-ticket"]);
    sockets[0].onmessage({
      data: JSON.stringify({
        type: "help_chat_line_changed",
        event: "student_message",
        chat_line_id: 7,
        payload: { id: 9, messages: [{ id: 12, body: "已收到" }] },
      }),
    });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ payload: { id: 9, messages: expect.any(Array) } }),
    );

    unsubscribe();
    vi.unstubAllGlobals();
  });
});
