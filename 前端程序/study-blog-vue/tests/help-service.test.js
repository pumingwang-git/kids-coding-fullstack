import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/services/auth", () => ({ request: vi.fn() }));

import { request } from "../src/services/auth";
import {
  createHelpRequest,
  getHelpChatLine,
  listHelpChatLines,
  messagesOf,
  recallHelpMessage,
  subscribeToHelpChatEvents,
  uploadHelpAttachment,
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
    await getHelpChatLine(7, { beforeId: 42, limit: 50 });
    expect(request).toHaveBeenLastCalledWith(
      "/api/student/help-chat-lines/7?limit=50&before_id=42",
    );
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

  it("uses the server withdrawal contract instead of treating the two-minute hint as authorization", async () => {
    request.mockResolvedValue({ id: 8, recalled: true });
    await recallHelpMessage(8);
    expect(request).toHaveBeenCalledWith("/api/student/help-messages/8/recall", {
      method: "POST",
      body: "{}",
    });
  });

  it("uploads an image with one stable idempotency key and reports byte progress", async () => {
    const instances = [];
    class FakeXmlHttpRequest {
      constructor() {
        this.upload = {};
        this.headers = {};
        this.status = 201;
        this.responseText = JSON.stringify({ id: 17, original_name: "code.png" });
        instances.push(this);
      }
      open(...args) {
        this.openArgs = args;
      }
      setRequestHeader(name, value) {
        this.headers[name] = value;
      }
      send() {
        this.upload.onprogress({ lengthComputable: true, loaded: 4, total: 5 });
        this.onload();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXmlHttpRequest);
    const progress = vi.fn();
    await expect(
      uploadHelpAttachment(9, new File(["image"], "code.png", { type: "image/png" }), {
        requestKey: "attachment-retry-key",
        onProgress: progress,
      }),
    ).resolves.toMatchObject({ id: 17 });
    expect(instances[0].openArgs).toEqual(["POST", "/api/student/help-requests/9/attachments"]);
    expect(instances[0].headers["Idempotency-Key"]).toBe("attachment-retry-key");
    expect(progress).toHaveBeenCalledWith(80);
    vi.unstubAllGlobals();
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
