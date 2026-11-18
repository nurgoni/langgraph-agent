/**
 * Tampilan chat (FR-43), disusun dari template registry assistant-ui `thread` (0.15) dan
 * disesuaikan untuk agent service (keputusan user F33: template boleh diedit).
 *
 * Dibuang dari template: attachment, suara, cabang message, edit pesan, saran, dan feedback, karena
 * service belum mendukungnya. Ditambahkan: grup sub-agent per `parentId` (FR-23), peringatan
 * jawaban terpotong (FR-30), tanda run dihentikan, dan slot `composerExtra` (pemilih model).
 */
import {
  ActionBarPrimitive,
  AuiIf,
  type AssistantState,
  ComposerPrimitive,
  ErrorPrimitive,
  groupPartByType,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  BotIcon,
  CheckIcon,
  CopyIcon,
  ScissorsIcon,
  SquareIcon,
} from "lucide-react";
import { type FC, type PropsWithChildren, type ReactNode, useState } from "react";

import { MarkdownText } from "@/components/assistant-ui/elements/markdown-text";
import {
  Reasoning,
  ReasoningContent,
  ReasoningRoot,
  ReasoningText,
  ReasoningTrigger,
} from "@/components/assistant-ui/elements/reasoning.aui";
import { ToolFallback } from "@/components/assistant-ui/elements/tool-fallback.aui";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "@/components/assistant-ui/elements/tool-group.aui";
import { TooltipIconButton } from "@/components/assistant-ui/elements/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArtifactCards } from "@/features/artifacts/ArtifactCards";
import { ArtifactMarkdownImage } from "@/features/artifacts/ArtifactMarkdownImage";
import { ComposerAddAttachment, ComposerAttachments } from "@/features/artifacts/ComposerAttachments";
import { artifactsFromValue } from "@/features/artifacts/message-artifacts";
import { ARTIFACTS_DATA_PART_NAME } from "@/features/chat/conversation";
import { cn } from "@/lib/utils";

export const TRUNCATED_WARNING =
  "The answer was cut off because the model reached its token limit (LLM_MAX_TOKENS).";
export const CANCELLED_NOTICE = "Stopped.";
const AGENT_GROUP_PREFIX = "group-agent:";
// Gambar markdown dengan path workspace dicocokkan ke artifact jawaban yang sama (F38).
const MARKDOWN_COMPONENTS = { img: ArtifactMarkdownImage };
const MILLISECONDS_PER_SECOND = 1000;

type ThreadGroupPart = MessagePrimitive.GroupedParts.GroupPart;
type GroupByPart = Parameters<typeof messageGroupBy>[0];
type GroupByContext = Parameters<typeof messageGroupBy>[1];

const messageGroupBy = groupPartByType({
  reasoning: ["group-chainOfThought", "group-reasoning"],
  "tool-call": ["group-chainOfThought", "group-tool"],
  "standalone-tool-call": [],
});

/** Part buatan sub-agent (`parentId` = nama expert) dibungkus satu grup per expert. */
function groupByAgent(part: GroupByPart, context: GroupByContext): readonly `group-${string}`[] {
  const path = messageGroupBy(part, context);
  const parentId = "parentId" in part ? part.parentId : undefined;
  return parentId ? [`${AGENT_GROUP_PREFIX}${parentId}`, ...path] : path;
}

const reasoningDuration = (timing: ThreadGroupPart["timing"]) =>
  timing?.completedAt === undefined
    ? undefined
    : Math.round((timing.completedAt - timing.startedAt) / MILLISECONDS_PER_SECOND);

const isNewChatView = (s: AssistantState) => s.thread.messages.length === 0 && !s.thread.isLoading;
const isHistoryLoadingView = (s: AssistantState) =>
  s.thread.messages.length === 0 && s.thread.isLoading;

export interface ThreadProps {
  /** Isi layar chat kosong, misalnya sapaan. */
  welcome?: ReactNode;
  /** Kontrol tambahan di baris aksi composer, misalnya pemilih model. */
  composerExtra?: ReactNode;
}

export const Thread: FC<ThreadProps> = ({ welcome, composerExtra }) => {
  const isEmpty = useAuiState(isNewChatView);
  return (
    <ThreadPrimitive.Root
      className="aui-root aui-thread-root bg-background @container flex h-full flex-col"
      style={{
        ["--thread-max-width" as string]: "44rem",
        ["--composer-bg" as string]: "color-mix(in oklab, var(--color-muted) 30%, transparent)",
        ["--composer-radius" as string]: "1rem",
        ["--composer-padding" as string]: "8px",
      }}
    >
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        className="relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth"
      >
        <div
          className={cn(
            "mx-auto flex w-full max-w-(--thread-max-width) flex-1 flex-col px-4 pt-4",
            isEmpty && "justify-center",
          )}
        >
          <AuiIf condition={isNewChatView}>
            <div className="mb-6 flex flex-col px-2">{welcome}</div>
          </AuiIf>
          <AuiIf condition={isHistoryLoadingView}>
            <ThreadHistorySkeleton />
          </AuiIf>
          <div className="mb-14 flex flex-col gap-y-6 empty:hidden">
            <ThreadPrimitive.Messages>{() => <ThreadMessage />}</ThreadPrimitive.Messages>
          </div>
          <ThreadPrimitive.ViewportFooter
            className={cn(
              "aui-thread-viewport-footer bg-background flex flex-col gap-4 overflow-visible pb-4 md:pb-6",
              !isEmpty && "sticky bottom-0 mt-auto rounded-t-(--composer-radius)",
            )}
          >
            <ThreadScrollToBottom />
            <Composer extra={composerExtra} />
          </ThreadPrimitive.ViewportFooter>
        </div>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadHistorySkeleton: FC = () => (
  <div role="status" className="flex flex-col gap-y-6">
    <span className="sr-only">Loading conversation</span>
    <Skeleton className="ml-auto h-9 w-2/5 rounded-xl" />
    <div className="flex flex-col gap-y-2">
      <Skeleton className="h-4 w-11/12" />
      <Skeleton className="h-4 w-4/5" />
    </div>
  </div>
);

const ThreadMessage: FC = () => {
  const role = useAuiState((s) => s.message.role);
  return role === "user" ? <UserMessage /> : <AssistantMessage />;
};

const ThreadScrollToBottom: FC = () => (
  <ThreadPrimitive.ScrollToBottom asChild>
    <TooltipIconButton
      tooltip="Scroll to bottom"
      variant="outline"
      className="aui-thread-scroll-to-bottom dark:border-border dark:bg-background dark:hover:bg-accent absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible"
    >
      <ArrowDownIcon />
    </TooltipIconButton>
  </ThreadPrimitive.ScrollToBottom>
);

const Composer: FC<{ extra: ReactNode }> = ({ extra }) => (
  <ComposerPrimitive.Root className="aui-composer-root relative flex w-full flex-col">
    <div className="border-foreground/10 focus-within:border-foreground/25 flex w-full cursor-text flex-col gap-2 rounded-(--composer-radius) border bg-(--composer-bg) p-(--composer-padding) transition-[border-color]">
      <ComposerAttachments />
      <ComposerPrimitive.Input
        placeholder="Send a message..."
        className="aui-composer-input caret-primary placeholder:text-muted-foreground/60 max-h-48 min-h-10 w-full resize-none bg-transparent px-2.5 py-1 text-base leading-6 outline-none"
        rows={1}
        autoFocus
        enterKeyHint="send"
        aria-label="Message input"
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <ComposerAddAttachment />
          {extra}
        </div>
        <AuiIf condition={(s) => !s.thread.isRunning}>
          <ComposerPrimitive.Send asChild>
            <TooltipIconButton
              tooltip="Send message"
              side="bottom"
              type="button"
              variant="default"
              size="icon"
              className="aui-composer-send size-7 rounded-full"
              aria-label="Send message"
            >
              <ArrowUpIcon className="size-4" />
            </TooltipIconButton>
          </ComposerPrimitive.Send>
        </AuiIf>
        <AuiIf condition={(s) => s.thread.isRunning}>
          <ComposerPrimitive.Cancel asChild>
            <Button
              type="button"
              variant="default"
              size="icon"
              className="aui-composer-cancel size-7 rounded-full"
              aria-label="Stop generating"
            >
              <SquareIcon className="size-3.5 fill-current" />
            </Button>
          </ComposerPrimitive.Cancel>
        </AuiIf>
      </div>
    </div>
  </ComposerPrimitive.Root>
);

const DefaultToolGroup: FC<PropsWithChildren<{ group: ThreadGroupPart }>> = ({
  group,
  children,
}) => {
  const [open, setOpen] = useState(false);
  return (
    <ToolGroupRoot variant="ghost" open={open} onOpenChange={setOpen}>
      <ToolGroupTrigger count={group.indices.length} active={group.status.type === "running"} />
      <ToolGroupContent>{children}</ToolGroupContent>
    </ToolGroupRoot>
  );
};

/** Langkah satu sub-agent (expert), bertingkat di dalam jawaban agent utama (FR-23). */
const AgentGroup: FC<PropsWithChildren<{ agent: string }>> = ({ agent, children }) => (
  <section
    aria-label={`Sub-agent ${agent}`}
    className="border-border my-2 rounded-lg border px-3 py-2"
  >
    <p className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium">
      <BotIcon className="size-3.5" />
      {agent}
    </p>
    {children}
  </section>
);

const MessageError: FC = () => (
  <MessagePrimitive.Error>
    <ErrorPrimitive.Root className="aui-message-error-root border-destructive bg-destructive/10 text-destructive dark:bg-destructive/5 mt-2 rounded-md border p-3 text-sm dark:text-red-200">
      <ErrorPrimitive.Message className="aui-message-error-message" />
    </ErrorPrimitive.Root>
  </MessagePrimitive.Error>
);

/** Peringatan untuk jawaban yang berhenti karena batas token (FR-30), dan tanda run dihentikan. */
const MessageEndNotice: FC = () => {
  const reason = useAuiState((s) =>
    s.message.status?.type === "incomplete" ? s.message.status.reason : null,
  );
  if (reason === "length") {
    return (
      <p
        role="note"
        className="mt-2 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200"
      >
        <ScissorsIcon className="size-4 shrink-0" />
        {TRUNCATED_WARNING}
      </p>
    );
  }
  if (reason === "cancelled") {
    return <p className="text-muted-foreground mt-2 text-sm">{CANCELLED_NOTICE}</p>;
  }
  return null;
};

const AssistantMessage: FC = () => (
  <MessagePrimitive.Root
    data-role="assistant"
    className="fade-in slide-in-from-bottom-1 animate-in relative duration-150"
  >
    <div className="text-foreground px-2 leading-relaxed wrap-break-word">
      <MessagePrimitive.GroupedParts groupBy={groupByAgent}>
        {({ part, children }) => {
          if (part.type.startsWith(AGENT_GROUP_PREFIX)) {
            return (
              <AgentGroup agent={part.type.slice(AGENT_GROUP_PREFIX.length)}>{children}</AgentGroup>
            );
          }
          switch (part.type) {
            case "group-chainOfThought":
              return <div>{children}</div>;
            case "group-tool":
              return (
                <DefaultToolGroup group={part}>{children}</DefaultToolGroup>
              );
            case "group-reasoning": {
              const group = part as ThreadGroupPart;
              const running = group.status.type === "running";
              return (
                <ReasoningRoot streaming={running}>
                  <ReasoningTrigger active={running} duration={reasoningDuration(group.timing)} />
                  <ReasoningContent aria-busy={running}>
                    <ReasoningText>{children}</ReasoningText>
                  </ReasoningContent>
                </ReasoningRoot>
              );
            }
            case "text":
              return <MarkdownText components={MARKDOWN_COMPONENTS} />;
            case "reasoning":
              return <Reasoning {...part} />;
            case "tool-call":
              return part.toolUI ?? <ToolFallback {...part} />;
            case "data":
              if (part.name === ARTIFACTS_DATA_PART_NAME) {
                return <ArtifactCards artifacts={artifactsFromValue(part.data)} />;
              }
              return (
                <pre className="bg-muted my-2 overflow-x-auto rounded-md p-3 text-xs">
                  {JSON.stringify(part.data, null, 2)}
                </pre>
              );
            case "indicator":
              return (
                <span className="animate-pulse font-sans" aria-label="Assistant is working">
                  {"●"}
                </span>
              );
            default:
              return null;
          }
        }}
      </MessagePrimitive.GroupedParts>
      <MessageError />
      <MessageEndNotice />
    </div>
    <div className="ms-2 flex min-h-7.5 items-center pt-1.5">
      <AssistantActionBar />
    </div>
  </MessagePrimitive.Root>
);

const AssistantActionBar: FC = () => (
  <ActionBarPrimitive.Root
    hideWhenRunning
    autohide="not-last"
    className="aui-assistant-action-bar-root text-muted-foreground -ms-1 flex gap-1"
  >
    <ActionBarPrimitive.Copy asChild>
      <TooltipIconButton tooltip="Copy">
        <AuiIf condition={(s) => s.message.isCopied}>
          <CheckIcon />
        </AuiIf>
        <AuiIf condition={(s) => !s.message.isCopied}>
          <CopyIcon />
        </AuiIf>
      </TooltipIconButton>
    </ActionBarPrimitive.Copy>
  </ActionBarPrimitive.Root>
);

const UserMessage: FC = () => (
  <MessagePrimitive.Root
    data-role="user"
    className="fade-in slide-in-from-bottom-1 animate-in grid auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] content-start gap-y-2 px-2 duration-150 [&:where(>*)]:col-start-2"
  >
    <UserMessageArtifacts />
    <div className="aui-user-message-content bg-muted text-foreground col-start-2 min-w-0 rounded-(--composer-radius) px-4 py-2 wrap-break-word">
      <MessagePrimitive.Parts />
    </div>
  </MessagePrimitive.Root>
);

/** Lampiran pesan user dari `metadata.custom` (F38), di atas isi pesan. */
const UserMessageArtifacts: FC = () => {
  const value = useAuiState((s) => s.message.metadata.custom[ARTIFACTS_DATA_PART_NAME]);
  return (
    <div className="col-start-2 flex justify-end empty:hidden">
      <ArtifactCards artifacts={artifactsFromValue(value)} />
    </div>
  );
};
