import { describe, expect, it } from "vitest";

import type { StreamEvent } from "@/api/stream-event";
import { readStreamEvents } from "@/features/chat/sse";
import { SSE_FIXTURES } from "@/test/fixtures";

/** Body stream dari teks, dipecah per `chunkSize` byte untuk meniru paket jaringan. */
function bodyOf(text: string, chunkSize = Number.MAX_SAFE_INTEGER): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      for (let start = 0; start < bytes.length; start += chunkSize) {
        controller.enqueue(bytes.slice(start, start + chunkSize));
      }
      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const event of readStreamEvents(body)) {
    events.push(event);
  }
  return events;
}

function countByType(events: StreamEvent[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const event of events) {
    const type = event.type ?? "unknown";
    counts[type] = (counts[type] ?? 0) + 1;
  }
  return counts;
}

describe("readStreamEvents", () => {
  it("reads every frame of a recorded run, in order", async () => {
    const events = await collect(bodyOf(SSE_FIXTURES.reasoning));

    expect(countByType(events)).toEqual({ reasoning: 224, token: 23, message: 1 });
    expect(events[0]?.type).toBe("reasoning");
    expect(events.at(-1)?.type).toBe("message");
  });

  it("gives the same events when frames are split across chunks", async () => {
    const whole = await collect(bodyOf(SSE_FIXTURES.subAgents));
    const split = await collect(bodyOf(SSE_FIXTURES.subAgents, 7));

    expect(split).toEqual(whole);
  });

  it("decodes multi-byte characters split between chunks", async () => {
    const text = 'data: {"type":"token","content":"café ☕"}\n\ndata: [DONE]\n\n';

    expect(await collect(bodyOf(text, 3))).toEqual([{ type: "token", content: "café ☕" }]);
  });

  it("accepts CRLF line endings and stops at [DONE]", async () => {
    const text =
      'data: {"type":"token","content":"a"}\r\n\r\ndata: [DONE]\r\n\r\ndata: {"type":"token","content":"b"}\r\n\r\n';

    expect(await collect(bodyOf(text))).toEqual([{ type: "token", content: "a" }]);
  });
});
