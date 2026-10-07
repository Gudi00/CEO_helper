/**
 * Overlay UI: highlight in assist mode, modal in step-by-step mode,
 * dispatched click events that satisfy the ADR-0007 stealth rules
 * (never write input.checked directly, only fire native MouseEvents).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  dispatchClick,
  highlight,
  highlightDots,
  injectStylesOnce,
  showInlineBadge,
  showStepPrompt,
  showToast,
} from "@/content/overlay.js";
import type { AnswerResult } from "@/shared/types.js";

function mountQuestion(): HTMLElement {
  document.body.innerHTML = `
    <div class="que multichoice" id="question-1-1">
      <div class="qtext">Q?</div>
      <div class="answer">
        <div class="r0">
          <input type="radio" name="q1:1_answer" value="1" id="i1">
          <label for="i1">A</label>
        </div>
        <div class="r1">
          <input type="radio" name="q1:1_answer" value="2" id="i2">
          <label for="i2">B</label>
        </div>
      </div>
    </div>`;
  return document.getElementById("question-1-1") as HTMLElement;
}

function answer(partial: Partial<AnswerResult> = {}): AnswerResult {
  return {
    answer_indices: [0],
    confidence: 0.9,
    reasoning: "because",
    provider: "stub",
    from_cache: false,
    ...partial,
  };
}

beforeEach(() => {
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("injectStylesOnce", () => {
  it("inserts the stylesheet exactly once", () => {
    injectStylesOnce();
    injectStylesOnce();
    expect(document.querySelectorAll("#lms-tool-styles")).toHaveLength(1);
  });
});

describe("highlight", () => {
  it("marks the chosen label with data-lms-tool=suggested", () => {
    const q = mountQuestion();
    highlight(q, answer({ answer_indices: [1], confidence: 0.9 }));
    const labels = q.querySelectorAll<HTMLLabelElement>("label");
    expect(labels[0]!.getAttribute("data-lms-tool")).toBeNull();
    expect(labels[1]!.getAttribute("data-lms-tool")).toBe("suggested");
  });

  it("uses the 'suggested-low' variant for low confidence", () => {
    const q = mountQuestion();
    highlight(q, answer({ answer_indices: [0], confidence: 0.4 }));
    const labels = q.querySelectorAll<HTMLLabelElement>("label");
    expect(labels[0]!.getAttribute("data-lms-tool")).toBe("suggested-low");
  });

  it("returns a cleanup function that strips the marks", () => {
    const q = mountQuestion();
    const cleanup = highlight(q, answer({ answer_indices: [0] }));
    cleanup();
    const labels = q.querySelectorAll<HTMLLabelElement>("label");
    expect(labels[0]!.getAttribute("data-lms-tool")).toBeNull();
    expect(labels[0]!.getAttribute("title")).toBeNull();
  });

  it("ignores option indices that don't exist", () => {
    const q = mountQuestion();
    expect(() =>
      highlight(q, answer({ answer_indices: [99] })),
    ).not.toThrow();
  });
});

describe("dispatchClick", () => {
  it("fires mousedown, mouseup and click on the input element", () => {
    const q = mountQuestion();
    const input = q.querySelector<HTMLInputElement>("#i1")!;
    const seen: string[] = [];
    for (const t of ["mousedown", "mouseup", "click"]) {
      input.addEventListener(t, () => seen.push(t));
    }

    const ok = dispatchClick(q, 0);
    expect(ok).toBe(true);
    expect(seen).toEqual(["mousedown", "mouseup", "click"]);
  });

  it("returns false when the option does not exist", () => {
    const q = mountQuestion();
    expect(dispatchClick(q, 99)).toBe(false);
  });

  it("does not flip input.checked directly (stealth contract)", () => {
    const q = mountQuestion();
    const input = q.querySelector<HTMLInputElement>("#i1")!;
    // Intercept the would-be native click — confirm the wrapper isn't
    // setting .checked outside the event flow.
    input.addEventListener("click", (e) => e.preventDefault());
    dispatchClick(q, 0);
    expect(input.checked).toBe(false);
  });
});

describe("showStepPrompt", () => {
  it("renders confidence and resolves 'confirm' on the primary button", async () => {
    const q = mountQuestion();
    const promise = showStepPrompt(q, answer({ answer_indices: [1], confidence: 0.87 }));

    const modal = document.querySelector(".lms-tool-step")!;
    expect(modal).not.toBeNull();
    expect(modal.textContent).toContain("87%");
    expect(modal.textContent).toContain("вариант 2"); // 1-based

    (modal.querySelector('[data-act="confirm"]') as HTMLButtonElement).click();
    await expect(promise).resolves.toBe("confirm");
    expect(document.querySelector(".lms-tool-step")).toBeNull();
  });

  it("resolves 'reject' on Esc", async () => {
    const q = mountQuestion();
    const promise = showStepPrompt(q, answer());
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
    );
    await expect(promise).resolves.toBe("reject");
  });

  it("resolves 'confirm' on Enter", async () => {
    const q = mountQuestion();
    const promise = showStepPrompt(q, answer());
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true }),
    );
    await expect(promise).resolves.toBe("confirm");
  });

  it("escapes HTML in reasoning", async () => {
    const q = mountQuestion();
    const promise = showStepPrompt(
      q,
      answer({ reasoning: "<script>alert(1)</script>" }),
    );
    const reason = document.querySelector(".lms-tool-step__reason")!;
    expect(reason.innerHTML).not.toContain("<script>");
    expect(reason.textContent).toContain("<script>alert(1)</script>");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await promise;
  });
});

describe("showToast", () => {
  it("renders a toast with the right kind class", () => {
    const dismiss = showToast("backend error", "err", 0);
    const toast = document.querySelector(".lms-tool-toast");
    expect(toast).not.toBeNull();
    expect(toast?.classList.contains("lms-tool-toast--err")).toBe(true);
    expect(toast?.textContent).toBe("backend error");
    dismiss();
  });

  it("auto-dismisses after duration", async () => {
    vi.useFakeTimers();
    try {
      showToast("temporary", "info", 200);
      expect(document.querySelector(".lms-tool-toast")).not.toBeNull();
      vi.advanceTimersByTime(250);
      expect(document.querySelector(".lms-tool-toast")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("click dismisses immediately", () => {
    showToast("clickme", "warn", 0);
    const toast = document.querySelector<HTMLElement>(".lms-tool-toast")!;
    toast.click();
    expect(document.querySelector(".lms-tool-toast")).toBeNull();
  });

  it("escapes attacker text via textContent (no HTML injection)", () => {
    showToast("<img onerror=alert>", "err", 0);
    const toast = document.querySelector(".lms-tool-toast");
    expect(toast?.innerHTML).not.toContain("<img");
    expect(toast?.textContent).toBe("<img onerror=alert>");
  });
});

describe("showInlineBadge", () => {
  function mountQ(): HTMLElement {
    document.body.innerHTML = `
      <div class="que" id="question-1-1">
        <div class="qtext">Test question</div>
        <div class="answer">
          <div class="r0"><input type="radio" name="a" value="1">A</div>
          <div class="r1"><input type="radio" name="a" value="2">B</div>
        </div>
      </div>`;
    return document.getElementById("question-1-1")!;
  }

  it("inserts a badge right after .qtext", () => {
    const q = mountQ();
    showInlineBadge(q, answer({ answer_indices: [1], confidence: 0.9 }));
    const badge = q.querySelector(".lms-tool-badge")!;
    expect(badge).not.toBeNull();
    expect((badge.textContent || "")).toContain("AI: вариант 2");
    expect((badge.textContent || "")).toContain("90%");
    const sibling = q.querySelector(".qtext")!.nextElementSibling;
    expect(sibling).toBe(badge);
  });

  it("uses the low-confidence variant under 0.6", () => {
    const q = mountQ();
    showInlineBadge(q, answer({ confidence: 0.4 }));
    const badge = q.querySelector(".lms-tool-badge")!;
    expect(badge.classList.contains("lms-tool-badge--low")).toBe(true);
  });

  it("renders multiple picks as comma list", () => {
    const q = mountQ();
    showInlineBadge(q, answer({ answer_indices: [0, 1] }));
    expect(q.querySelector(".lms-tool-badge")?.textContent).toContain(
      "AI: вариант 1, 2",
    );
  });

  it("marks the cached-from-cache origin", () => {
    const q = mountQ();
    showInlineBadge(q, answer({ from_cache: true }));
    expect(q.querySelector(".lms-tool-badge")?.textContent).toContain("кеш");
  });

  it("re-rendering replaces the prior badge (no duplicates)", () => {
    const q = mountQ();
    showInlineBadge(q, answer({ answer_indices: [0] }));
    showInlineBadge(q, answer({ answer_indices: [1] }));
    const badges = q.querySelectorAll(".lms-tool-badge");
    expect(badges.length).toBe(1);
    expect((badges[0]!.textContent || "")).toContain("вариант 2");
  });

  it("survives when the question container has no .qtext (falls back to .content)", () => {
    document.body.innerHTML = `
      <div class="que" id="question-1-1">
        <div class="content">
          <div class="answer">
            <div class="r0"><input type="radio" name="a" value="1">A</div>
          </div>
        </div>
      </div>`;
    const q = document.getElementById("question-1-1")!;
    showInlineBadge(q, answer({ answer_indices: [0] }));
    expect(q.querySelector(".lms-tool-badge")).not.toBeNull();
  });

  it("escapes attacker text in reasoning", () => {
    const q = mountQ();
    showInlineBadge(q, answer({ reasoning: "<img onerror=alert>" }));
    const badge = q.querySelector(".lms-tool-badge")!;
    expect(badge.innerHTML).not.toContain("<img");
    expect(badge.textContent).toContain("<img onerror=alert>");
  });
});

describe("highlightDots", () => {
  it("inserts a dot after the correct label", () => {
    const q = mountQuestion();
    highlightDots(q, answer({ answer_indices: [1] }));
    const dots = q.querySelectorAll("[data-lms-dot]");
    expect(dots).toHaveLength(1);
    const labels = q.querySelectorAll("label");
    expect(labels[1]!.nextElementSibling?.getAttribute("data-lms-dot")).toBe("1");
  });

  it("respects custom diameter and offsets", () => {
    const q = mountQuestion();
    highlightDots(q, answer({ answer_indices: [0] }), { diameter: 20, offsetX: 5, offsetY: 3 });
    const dot = q.querySelector<HTMLElement>("[data-lms-dot]")!;
    expect(dot.style.width).toBe("20px");
    expect(dot.style.height).toBe("20px");
    expect(dot.style.marginLeft).toBe("5px");
    expect(dot.style.marginTop).toBe("3px");
  });

  it("places a dot for every correct index", () => {
    const q = mountQuestion();
    highlightDots(q, answer({ answer_indices: [0, 1] }));
    expect(q.querySelectorAll("[data-lms-dot]")).toHaveLength(2);
  });

  it("returns cleanup that removes all dots", () => {
    const q = mountQuestion();
    const cleanup = highlightDots(q, answer({ answer_indices: [0, 1] }));
    cleanup();
    expect(q.querySelectorAll("[data-lms-dot]")).toHaveLength(0);
  });

  it("ignores missing option indices without throwing", () => {
    const q = mountQuestion();
    expect(() => highlightDots(q, answer({ answer_indices: [99] }))).not.toThrow();
    expect(q.querySelectorAll("[data-lms-dot]")).toHaveLength(0);
  });

  it("does not insert badge or outline — no side-effects on label attributes", () => {
    const q = mountQuestion();
    highlightDots(q, answer({ answer_indices: [0] }));
    expect(q.querySelector(".lms-tool-badge")).toBeNull();
    const label = q.querySelectorAll("label")[0]!;
    expect(label.getAttribute("data-lms-tool")).toBeNull();
  });
});

describe("highlight integration", () => {
  it("renders the inline badge even when there is no <label> to paint", () => {
    document.body.innerHTML = `
      <div class="que" id="question-1-1">
        <div class="qtext">Q?</div>
        <div class="answer">
          <div class="r0"><input type="radio" name="a" value="1">A row</div>
          <div class="r1"><input type="radio" name="a" value="2">B row</div>
        </div>
      </div>`;
    const q = document.getElementById("question-1-1")!;
    highlight(q, answer({ answer_indices: [1] }));
    const badge = q.querySelector(".lms-tool-badge");
    expect(badge).not.toBeNull();
    // Row should get the attribute since there's no <label>.
    const marked = q.querySelector('[data-lms-tool="suggested"]');
    expect(marked).not.toBeNull();
    expect(marked?.tagName).toBe("DIV");
    expect(marked?.className).toBe("r1");
  });
});

describe("showStatusBadge", () => {
  it("replaces the previous badge and exposes the status", async () => {
    const { showStatusBadge } = await import("@/content/overlay.js");
    const q = mountQuestion();
    showStatusBadge(q, "queued", "В очереди…");
    showStatusBadge(q, "thinking", "Нейросеть думает…");

    const badges = q.querySelectorAll(".lms-tool-badge");
    expect(badges).toHaveLength(1);
    expect(badges[0]?.getAttribute("data-lms-tool-status")).toBe("thinking");
    expect(badges[0]?.textContent).toContain("Нейросеть думает");
  });

  it("is replaced by the answer badge", async () => {
    const { showStatusBadge } = await import("@/content/overlay.js");
    const q = mountQuestion();
    showStatusBadge(q, "thinking", "Нейросеть думает…");
    highlight(q, answer());

    expect(q.querySelector("[data-lms-tool-status]")).toBeNull();
    expect(q.querySelectorAll(".lms-tool-badge")).toHaveLength(1);
  });

  it("runs an action when its button is clicked", async () => {
    const { showStatusBadge } = await import("@/content/overlay.js");
    const q = mountQuestion();
    const onClick = vi.fn();
    showStatusBadge(q, "error", "Сервер не отвечает.", [{ label: "Повторить", onClick }]);

    const btn = q.querySelector<HTMLButtonElement>(".lms-tool-badge__btn");
    expect(btn?.textContent).toBe("Повторить");
    btn?.click();
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("showManualPanel", () => {
  it("passes the pasted reply to onSubmit and shows its error text", async () => {
    const { showManualPanel } = await import("@/content/overlay.js");
    const q = mountQuestion();
    const onSubmit = vi.fn().mockReturnValue("Не удалось распознать ответ.");
    showManualPanel(q, { onCopy: async () => true, onSubmit });

    const input = q.querySelector<HTMLTextAreaElement>(".lms-tool-badge__input");
    expect(input).not.toBeNull();
    (input as HTMLTextAreaElement).value = "что-то";
    const buttons = q.querySelectorAll<HTMLButtonElement>(".lms-tool-badge__btn");
    buttons[1]?.click();

    expect(onSubmit).toHaveBeenCalledWith("что-то");
    expect(q.querySelector(".lms-tool-badge__hint")?.textContent).toBe(
      "Не удалось распознать ответ.",
    );
  });

  it("never interprets pasted text as HTML", async () => {
    const { showManualPanel } = await import("@/content/overlay.js");
    const q = mountQuestion();
    const payload = '<img src=x onerror="alert(1)">';
    showManualPanel(q, { onCopy: async () => true, onSubmit: () => payload });

    q.querySelectorAll<HTMLButtonElement>(".lms-tool-badge__btn")[1]?.click();

    expect(q.querySelector(".lms-tool-badge img")).toBeNull();
    expect(q.querySelector(".lms-tool-badge__hint")?.textContent).toBe(payload);
  });
});
