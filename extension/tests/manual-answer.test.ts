import { describe, expect, it } from "vitest";
import { buildManualPrompt, parseManualAnswer } from "@/shared/manual-answer.js";
import type { NormalizedQuestion, QuestionType } from "@/shared/types.js";

function question(type: QuestionType = "single_choice"): NormalizedQuestion {
  return {
    id: "q1:1",
    hash: "0".repeat(64),
    type,
    text: "Что такое HTTP?",
    options: [
      { index: 0, value: "1", text: "Протокол" },
      { index: 1, value: "2", text: "Язык программирования" },
      { index: 2, value: "3", text: "Операционная система" },
    ],
    metadata: { page_number: 0, attempt_id: "1", cmid: "1", has_images: false },
  };
}

describe("buildManualPrompt", () => {
  it("numbers options from 1 and asks for an answer line", () => {
    const p = buildManualPrompt(question());
    expect(p).toContain("1) Протокол");
    expect(p).toContain("3) Операционная система");
    expect(p).toContain("Ответ:");
  });
});

describe("parseManualAnswer", () => {
  it("reads the answer line after an explanation", () => {
    const reply = "HTTP работает поверх TCP, порт 80.\n\nОтвет: 1";
    expect(parseManualAnswer(reply, question())).toEqual([0]);
  });

  it("ignores digits in the explanation when an answer line exists", () => {
    const reply = "Порт 443 тут ни при чём, вариант 2 неверен.\nОтвет: 3";
    expect(parseManualAnswer(reply, question())).toEqual([2]);
  });

  it("reads bare numbers", () => {
    expect(parseManualAnswer(" 2 ", question())).toEqual([1]);
  });

  it("reads several numbers for multiple choice", () => {
    expect(parseManualAnswer("Ответ: 3, 1", question("multiple_choice"))).toEqual([0, 2]);
  });

  it("reads letters", () => {
    expect(parseManualAnswer("Ответ: Б", question())).toEqual([1]);
    expect(parseManualAnswer("a", question())).toEqual([0]);
  });

  it("matches an option quoted verbatim", () => {
    expect(parseManualAnswer("Ответ: протокол", question())).toEqual([0]);
  });

  it("rejects out-of-range numbers", () => {
    expect(parseManualAnswer("Ответ: 7", question())).toBeNull();
  });

  it("rejects several answers for single choice", () => {
    expect(parseManualAnswer("Ответ: 1, 2", question())).toBeNull();
  });

  it("rejects prose without a recognisable answer", () => {
    expect(parseManualAnswer("Не уверен, нужно больше контекста.", question())).toBeNull();
    expect(parseManualAnswer("", question())).toBeNull();
  });
});
