# Fixture SSE chat (F33)

Rekaman asli dari agent service dengan Ollama `qwen3.5:9b`, dibuat 2026-11-17 dengan template
smoke test (`.claude/skills/feature-workflow/references/smoke_template.py`) di database Postgres
sementara. Body SSE disimpan byte per byte dari `POST /{agent}/stream` dengan `stream_tokens=true`.

| File | Agent | Pesan | Isi |
|---|---|---|---|
| `reasoning.sse` | `chatbot` | "Is 221 a prime number? Answer in one sentence." | reasoning, token, message |
| `tool-calls.sse`, `.history.json` | `research-assistant` | "Use the calculator to compute 1234 * 5678, then state the result." | tool call `calculator` + hasil |
| `sub-agents.sse`, `.history.json` | `supervisor` | "Ask the math expert to compute (17 + 25) * 3 and report the answer." | message `agent=math_expert` |
| `interrupt.sse` | `interrupt-agent` | "Hi" | pertanyaan interrupt sebagai message AI |
| `truncated.sse`, `.history.json` | `chatbot`, `LLM_MAX_TOKENS=600` | "Write a detailed 500-word essay about the history of tea." | `truncated=true` |

`*.history.json` adalah respons `POST /{agent}/history` untuk thread yang sama. Test memastikan
riwayat menghasilkan message yang sama persis dengan hasil stream-nya.

Rekam ulang jika kontrak `stream-event.schema.json` berubah: salin template smoke, kirim pesan di
atas lewat `client.stream("POST", f"/{agent}/stream", ...)`, dan tulis `response.aiter_bytes()` apa
adanya.
