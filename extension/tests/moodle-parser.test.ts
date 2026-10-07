/**
 * Mirrors the Python parser test suite — same fixtures, same assertions.
 * Together with `tests/hash.test.ts` this guarantees both parsers emit
 * structurally identical NormalizedQuestion objects.
 */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

import {
  MoodleParseError,
  parseQuestions,
} from "@/content/moodle-parser.js";

const FIXTURES = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "fixtures/moodle",
);

async function loadFixture(name: string): Promise<HTMLElement> {
  const html = await readFile(resolve(FIXTURES, name), "utf-8");
  document.body.innerHTML = html;
  return document.body;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("parseQuestions", () => {
  it("parses a single_choice fixture", async () => {
    await loadFixture("single_choice.html");
    const qs = await parseQuestions({ cmid: "305095" });
    expect(qs).toHaveLength(1);
    const q = qs[0]!;
    expect(q.id).toBe("q739284:1");
    expect(q.type).toBe("single_choice");
    expect(q.text).toContain("БГУИР");
    expect(q.options.map((o) => o.text)).toEqual(["1964", "1967", "1971", "1980"]);
    expect(q.options.map((o) => o.value)).toEqual(["1", "2", "3", "4"]);
    expect(q.metadata.attempt_id).toBe("739284");
    expect(q.metadata.cmid).toBe("305095");
    expect(q.metadata.has_images).toBe(false);
    expect(q.hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("parses a multiple_choice fixture (checkboxes)", async () => {
    await loadFixture("multiple_choice.html");
    const qs = await parseQuestions({ cmid: "305095" });
    expect(qs).toHaveLength(1);
    const q = qs[0]!;
    expect(q.id).toBe("q739284:7");
    expect(q.type).toBe("multiple_choice");
    expect(q.text).toContain("интерпретируемыми");
    expect(q.options.map((o) => o.text)).toEqual([
      "Python",
      "C++",
      "JavaScript",
      "Rust",
    ]);
  });

  it("parses every question on a multi-question page", async () => {
    await loadFixture("multi_question_page.html");
    const qs = await parseQuestions({ cmid: "305095", pageNumber: 2 });
    expect(qs.map((q) => q.id)).toEqual(["q739284:3", "q739284:4"]);
    expect(qs.every((q) => q.metadata.page_number === 2)).toBe(true);
    expect(qs[0]!.options[0]!.text).toBe("Протокол передачи гипертекста");
    expect(qs[1]!.options[1]!.text).toBe("443");
  });

  it("marks has_images when <img> is present", async () => {
    await loadFixture("with_image.html");
    const qs = await parseQuestions({ cmid: "305095" });
    expect(qs[0]!.metadata.has_images).toBe(true);
  });

  it("returns an empty array on empty input", async () => {
    document.body.innerHTML = "<div></div>";
    expect(await parseQuestions({ cmid: "305095" })).toEqual([]);
  });

  it("raises on malformed question id", async () => {
    document.body.innerHTML = `
      <div class="que" id="question-bad">
        <div class="qtext">x</div>
        <div class="answer">
          <div class="r0">
            <input type="radio" name="x" value="1">
            <label>x</label>
          </div>
        </div>
      </div>`;
    await expect(parseQuestions({ cmid: "305095" })).rejects.toBeInstanceOf(
      MoodleParseError,
    );
  });

  it("strips '1.'-style answernumber prefixes", async () => {
    await loadFixture("single_choice.html");
    const qs = await parseQuestions({ cmid: "305095" });
    for (const opt of qs[0]!.options) {
      expect(opt.text).not.toMatch(/^\d+\./);
    }
  });

  it("produces stable hashes between runs", async () => {
    await loadFixture("single_choice.html");
    const a = await parseQuestions({ cmid: "305095" });
    document.body.innerHTML = "";
    await loadFixture("single_choice.html");
    const b = await parseQuestions({ cmid: "305095" });
    expect(a[0]!.hash).toBe(b[0]!.hash);
  });

  // Real lms.bsuir.by markup has no <label> elements — option text sits
  // directly under the row div. Parser must read it anyway, and the
  // highlight code must paint the row.
  it("parses BSUIR-style question without <label>", async () => {
    await loadFixture("no_label_bsuir.html");
    const qs = await parseQuestions({ cmid: "305095" });
    expect(qs).toHaveLength(1);
    const q = qs[0]!;
    expect(q.id).toBe("q739955:2");
    expect(q.type).toBe("single_choice");
    expect(q.options.map((o) => o.text)).toEqual([
      "1) нет 2) да",
      "1) нет 2) нет",
      "1) да 2) да",
      "1) да 2) нет",
    ]);
  });

  it("findOptionLabel falls back to row when no <label>", async () => {
    const { findOptionLabel } = await import("@/content/moodle-parser.js");
    await loadFixture("no_label_bsuir.html");
    const container = document.getElementById(
      "question-739955-2",
    ) as HTMLElement;
    const opt0 = findOptionLabel(container, 0);
    expect(opt0).not.toBeNull();
    expect(opt0?.tagName).toBe("DIV");
    expect(opt0?.className).toBe("r0");
  });
});

describe("formulas in question text", () => {
  it("keeps a TeX-filter image as its alt text", async () => {
    await loadFixture("with_image.html");
    const [q] = await parseQuestions({ cmid: "1" });
    expect(q!.text).toBe("Решите уравнение: [x^2 = 4]");
  });

  it("keeps MathJax source and drops the rendered copy", async () => {
    document.body.innerHTML = `
      <div class="que multichoice" id="question-1-1">
        <div class="qtext">Чему равно
          <span class="MathJax_Preview">junk</span>
          <span class="MathJax"><span>x2</span></span>
          <script type="math/tex">x^2</script> при x = 3?
        </div>
        <div class="answer">
          <div class="r0"><input type="radio" value="1"><label>6</label></div>
          <div class="r1"><input type="radio" value="2"><label>
            <mjx-container><mjx-math>9</mjx-math><mjx-assistive-mml><math><semantics>
              <mn>9</mn><annotation encoding="application/x-tex">3^2</annotation>
            </semantics></math></mjx-assistive-mml></mjx-container></label></div>
        </div>
      </div>`;
    const [q] = await parseQuestions({ cmid: "1" });
    expect(q!.text).toBe("Чему равно $x^2$ при x = 3?");
    expect(q!.options.map((o) => o.text)).toEqual(["6", "$3^2$"]);
  });
});
