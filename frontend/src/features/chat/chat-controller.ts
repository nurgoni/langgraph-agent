/**
 * State satu percakapan di browser: riwayat thread yang dibuka dan run yang sedang berjalan.
 *
 * Disimpan di luar React (dibaca lewat `useSyncExternalStore`), karena run streaming dan pemuatan
 * riwayat selesai secara asinkron dan harus dibatalkan saat user pindah thread.
 */
import type { ChatMessage } from "@/api/stream-event";
import { ChatService, ChatServiceError } from "@/features/chat/chat-service";
import {
  appendHuman,
  appendRunEnd,
  applyStreamEvent,
  type ConversationState,
  conversationFromHistory,
  EMPTY_CONVERSATION,
} from "@/features/chat/conversation";

export const THREAD_NOT_FOUND_MESSAGE = "This conversation was not found.";
export const UNEXPECTED_ERROR_MESSAGE = "Something went wrong. Try again.";
const HTTP_NOT_FOUND = 404;

export interface ChatSnapshot {
  /** Thread yang sedang dibuka, atau `null` untuk chat baru yang belum dikirim. */
  threadId: string | null;
  conversation: ConversationState;
  isRunning: boolean;
  isLoadingHistory: boolean;
  /** Alasan riwayat gagal dimuat. */
  historyError: string | null;
}

const NEW_CHAT: ChatSnapshot = {
  threadId: null,
  conversation: EMPTY_CONVERSATION,
  isRunning: false,
  isLoadingHistory: false,
  historyError: null,
};

/**
 * Menjalankan run dan memuat riwayat untuk satu tampilan chat.
 *
 * Class karena menyimpan state yang berubah (snapshot, run aktif, listener) dan dependency
 * (`ChatService`). Setiap pergantian thread menaikkan `generation`, sehingga hasil asinkron dari
 * thread sebelumnya diabaikan.
 */
export class ChatController {
  private readonly service: ChatService;
  private threadCreatedListener: (threadId: string) => void = () => undefined;
  private readonly listeners = new Set<() => void>();
  private snapshot: ChatSnapshot = NEW_CHAT;
  private generation = 0;
  private activeRun: AbortController | null = null;

  /** @param service Client chat ke agent service. */
  constructor(service: ChatService) {
    this.service = service;
  }

  /**
   * Pasang callback yang dipanggil saat service membuat thread untuk chat baru, misalnya untuk
   * mengganti URL ke `/chat/<id>`.
   */
  setThreadCreatedListener(listener: (threadId: string) => void): void {
    this.threadCreatedListener = listener;
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  readonly getSnapshot = (): ChatSnapshot => this.snapshot;

  /**
   * Buka thread dari URL. Tidak melakukan apa-apa jika thread itu sudah terbuka, misalnya setelah
   * URL diganti ke thread yang baru dibuat run ini.
   *
   * @param threadId Thread yang dibuka, atau `null` untuk chat baru.
   */
  openThread(threadId: string | null): void {
    if (threadId === this.snapshot.threadId) {
      return;
    }
    this.startGeneration();
    if (threadId === null) {
      this.update(NEW_CHAT);
      return;
    }
    this.update({ ...NEW_CHAT, threadId, isLoadingHistory: true });
    void this.loadHistory(threadId, this.generation);
  }

  /**
   * Kirim pesan user dan stream jawaban agent ke snapshot.
   *
   * @param text Pesan user.
   * @param model Model pilihan user, atau `null` untuk default service.
   */
  async send(text: string, model: string | null): Promise<void> {
    if (this.snapshot.isRunning) {
      return;
    }
    const generation = this.generation;
    const run = new AbortController();
    this.activeRun = run;
    this.update({ conversation: appendHuman(this.snapshot.conversation, text), isRunning: true });
    try {
      await this.streamRun({ message: text, threadId: this.snapshot.threadId, model }, run);
    } catch (caught) {
      if (generation === this.generation) {
        this.endRun(caught, run.signal);
      }
    } finally {
      if (generation === this.generation) {
        this.activeRun = null;
        this.update({ isRunning: false });
      }
    }
  }

  /** Hentikan run yang sedang berjalan. Teks yang sudah diterima tetap tampil. */
  cancel(): void {
    this.activeRun?.abort();
  }

  /** Batalkan pekerjaan yang tertunda, misalnya saat halaman chat ditutup. */
  dispose(): void {
    this.startGeneration();
  }

  private async streamRun(
    request: { message: string; threadId: string | null; model: string | null },
    run: AbortController,
  ): Promise<void> {
    const generation = this.generation;
    const { threadId, events } = await this.service.startRun(request, run.signal);
    if (threadId !== this.snapshot.threadId) {
      this.update({ threadId });
      this.threadCreatedListener(threadId);
    }
    for await (const event of events) {
      if (generation !== this.generation) {
        return;
      }
      this.update({ conversation: applyStreamEvent(this.snapshot.conversation, event) });
    }
  }

  /** Catat akhir run yang gagal: dihentikan user, ditolak service, atau error tak terduga. */
  private endRun(caught: unknown, signal: AbortSignal): void {
    const conversation = this.snapshot.conversation;
    if (signal.aborted) {
      this.update({ conversation: appendRunEnd(conversation, { kind: "cancelled" }) });
      return;
    }
    if (!(caught instanceof ChatServiceError)) {
      console.error("Chat run failed", caught);
    }
    const text = caught instanceof ChatServiceError ? caught.message : UNEXPECTED_ERROR_MESSAGE;
    this.update({ conversation: appendRunEnd(conversation, { kind: "error", text }) });
  }

  private async loadHistory(threadId: string, generation: number): Promise<void> {
    let messages: ChatMessage[];
    try {
      messages = await this.service.loadHistory(threadId);
    } catch (caught) {
      if (generation === this.generation) {
        this.update({ isLoadingHistory: false, historyError: historyErrorText(caught) });
      }
      return;
    }
    if (generation === this.generation) {
      this.update({ conversation: conversationFromHistory(messages), isLoadingHistory: false });
    }
  }

  private startGeneration(): void {
    this.generation += 1;
    this.activeRun?.abort();
    this.activeRun = null;
  }

  private update(change: Partial<ChatSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...change };
    for (const listener of this.listeners) {
      listener();
    }
  }
}

function historyErrorText(caught: unknown): string {
  if (!(caught instanceof ChatServiceError)) {
    console.error("Loading history failed", caught);
    return UNEXPECTED_ERROR_MESSAGE;
  }
  if (caught.status === HTTP_NOT_FOUND) {
    return THREAD_NOT_FOUND_MESSAGE;
  }
  return caught.message;
}
