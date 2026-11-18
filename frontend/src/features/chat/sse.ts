/**
 * Parser body SSE `POST /stream` menjadi event bertipe (kontrak `stream-event.schema.json`).
 *
 * Setiap frame dikirim sebagai `data: <json>` dan diakhiri baris kosong. Stream selalu ditutup
 * dengan `data: [DONE]` yang bukan JSON.
 */
import type { StreamEvent } from "@/api/stream-event";

const DATA_PREFIX = "data:";
const DONE_MARKER = "[DONE]";
const LINE_BREAK = /\r?\n/;

/**
 * Baca event dari body respons sampai `[DONE]` atau body habis.
 *
 * Function, bukan class: transformasi stream tanpa state di luar satu iterasi.
 *
 * @param body Body respons SSE.
 * @throws SyntaxError Jika frame `data:` berisi JSON yang tidak valid.
 */
export async function* readStreamEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split(LINE_BREAK);
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const payload = dataPayload(line);
        if (payload === DONE_MARKER) {
          return;
        }
        if (payload !== null) {
          yield JSON.parse(payload) as StreamEvent;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Isi frame `data:`, atau `null` untuk baris kosong dan field SSE lain. */
function dataPayload(line: string): string | null {
  if (!line.startsWith(DATA_PREFIX)) {
    return null;
  }
  return line.slice(DATA_PREFIX.length).trim();
}
