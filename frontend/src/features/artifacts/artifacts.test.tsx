/**
 * Acceptance F38 (FR-50) di jsdom: gambar, CSV, dan PDF dari agent bisa dipreview dan diunduh, dan
 * file dari composer di-upload lalu dikirim sebagai `artifact_ids`.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StoredArtifact } from "@/test/fake-service";
import { FakeService } from "@/test/fake-service";
import { renderApp, saveSession } from "@/test/render-app";

const CHART: StoredArtifact = {
  ref: { id: "a-chart", name: "chart.png", mime_type: "image/png", size: 19_341 },
  content: "\u0089PNG",
};
const SALES: StoredArtifact = {
  ref: { id: "a-sales", name: "sales.csv", mime_type: "text/csv", size: 40 },
  content: 'region,total,note\nnorth,200,"Jan, Feb"\nsouth,250,ok\n',
};
const REPORT: StoredArtifact = {
  ref: { id: "a-report", name: "report.pdf", mime_type: "application/pdf", size: 8 },
  content: "%PDF-1.4",
};
const THREAD_ID = "t-artifacts";
const HISTORY = {
  messages: [
    { type: "human", content: "Chart the sales" },
    {
      type: "ai",
      content: "",
      tool_calls: [{ name: "share_file", args: { path: "chart.png" }, id: "c1" }],
    },
    {
      type: "tool",
      content: "Shared chart.png with the user as chart.png.",
      tool_call_id: "c1",
      artifacts: [CHART.ref, SALES.ref, REPORT.ref],
    },
    { type: "ai", content: "Here it is:\n\n![chart](chart.png)\n\n![lost](missing.png)" },
  ],
};

beforeEach(() => saveSession());
afterEach(() => vi.restoreAllMocks());

function renderThread() {
  const service = new FakeService({
    histories: { [THREAD_ID]: HISTORY },
    artifacts: [CHART, SALES, REPORT],
  });
  renderApp(service, `/chat/${THREAD_ID}`);
  return { service, user: userEvent.setup() };
}

describe("artifact panel", () => {
  it("shows the files an agent shared as cards", async () => {
    renderThread();

    for (const name of ["chart.png", "sales.csv", "report.pdf"]) {
      expect(await screen.findByRole("button", { name: `Open ${name}` })).toBeInTheDocument();
    }
  });

  it("previews a CSV file as a table", async () => {
    const { user } = renderThread();

    await user.click(await screen.findByRole("button", { name: "Open sales.csv" }));

    const panel = await screen.findByRole("region", { name: "Preview of sales.csv" });
    const table = await within(panel).findByRole("table", { name: "CSV preview" });
    expect(within(table).getByRole("columnheader", { name: "region" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Jan, Feb" })).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("previews images and PDFs from the downloaded file", async () => {
    const { user, service } = renderThread();

    await user.click(await screen.findByRole("button", { name: "Open report.pdf" }));
    const pdfPanel = await screen.findByRole("region", { name: "Preview of report.pdf" });
    await waitFor(() => expect(pdfPanel.querySelector("iframe")).not.toBeNull());
    const pdfSource = pdfPanel.querySelector("iframe")?.getAttribute("src");
    await user.click(screen.getByRole("button", { name: "Open chart.png" }));
    const panel = await screen.findByRole("region", { name: "Preview of chart.png" });

    expect(pdfSource).toMatch(/^blob:/);
    expect(within(panel).getByRole("img", { name: "chart.png" }).getAttribute("src")).toMatch(
      /^blob:/,
    );
    expect(service.requestsTo("/api/artifacts/a-report")[0]?.authorization).toBe("Bearer jwt");
  });

  it("downloads the open file under its name", async () => {
    const { user } = renderThread();
    const clicked: HTMLAnchorElement[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicked.push(this);
    });

    await user.click(await screen.findByRole("button", { name: "Open report.pdf" }));
    await user.click(await screen.findByRole("button", { name: "Download report.pdf" }));

    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(clicked[0]?.download).toBe("report.pdf");
    expect(clicked[0]?.href).toMatch(/^blob:/);
  });

  it("closes the preview", async () => {
    const { user } = renderThread();

    await user.click(await screen.findByRole("button", { name: "Open chart.png" }));
    await user.click(await screen.findByRole("button", { name: "Close preview" }));

    expect(screen.queryByRole("region", { name: "Preview of chart.png" })).toBeNull();
  });

  it("shows markdown images that name a shared file and hides other relative paths", async () => {
    renderThread();

    const inline = await screen.findByRole("img", { name: "chart" });

    expect(inline.getAttribute("src")).toMatch(/^blob:/);
    expect(screen.getByText("[lost]")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "lost" })).toBeNull();
  });
});

describe("composer attachments", () => {
  async function attach(user: ReturnType<typeof userEvent.setup>, file: File) {
    const pick = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(function (this: HTMLInputElement) {
        Object.defineProperty(this, "files", { value: [file] });
        this.dispatchEvent(new Event("change"));
      });
    await user.click(await screen.findByRole("button", { name: "Attach files" }));
    pick.mockRestore();
  }

  it("uploads a picked file and sends it with the message", async () => {
    const service = new FakeService();
    renderApp(service, "/");
    const user = userEvent.setup();

    await attach(user, new File(["a,b\n1,2\n"], "data.csv", { type: "text/csv" }));
    await screen.findByRole("button", { name: "Remove data.csv" });
    await waitFor(() => expect(service.requestsTo("/api/artifacts", "POST")).toHaveLength(1));
    await user.type(screen.getByLabelText("Message input"), "Summarize this");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(service.requestsTo("/api/stream")).toHaveLength(1));
    expect(service.requestsTo("/api/stream")[0]?.body).toMatchObject({
      message: "Summarize this",
      artifact_ids: ["artifact-1"],
    });
    expect(await screen.findByRole("button", { name: "Open data.csv" })).toBeInTheDocument();
  });

  it("removes the uploaded file when its chip is removed", async () => {
    const service = new FakeService();
    renderApp(service, "/");
    const user = userEvent.setup();

    await attach(user, new File(["x"], "notes.txt", { type: "text/plain" }));
    await waitFor(() => expect(service.artifacts.size).toBe(1));
    await user.click(await screen.findByRole("button", { name: "Remove notes.txt" }));

    await waitFor(() => expect(service.artifacts.size).toBe(0));
    expect(service.requestsTo("/api/artifacts/artifact-1", "DELETE")).toHaveLength(1);
  });

  it("shows upload errors before sending", async () => {
    renderApp(new FakeService({ maxUploadBytes: 2 }), "/");
    const user = userEvent.setup();

    await attach(user, new File(["too big"], "big.bin"));

    expect(await screen.findByRole("alert")).toHaveTextContent("File is larger than the limit");
  });
});
