import { describe, expect, it, vi } from "vitest";
import { collectImages, isAllowedImage, toBase64 } from "@/content/images.js";

function mount(html: string): HTMLElement {
  document.body.innerHTML = `<div class="que" id="question-1-1">${html}</div>`;
  return document.getElementById("question-1-1") as HTMLElement;
}

function imageResponse(type: string, bytes: number[]): Response {
  return new Response(new Blob([new Uint8Array(bytes)], { type }));
}

describe("isAllowedImage", () => {
  it("accepts raster formats within the size limit only", () => {
    expect(isAllowedImage("image/png", 10)).toBe(true);
    expect(isAllowedImage("image/svg+xml", 10)).toBe(false);
    expect(isAllowedImage("image/png", 2_000_000)).toBe(false);
    expect(isAllowedImage("image/png", 0)).toBe(false);
  });
});

describe("toBase64", () => {
  it("encodes bytes", () => {
    expect(toBase64(new Uint8Array([104, 105]))).toBe("aGk=");
  });
});

describe("collectImages", () => {
  it("reads same-origin pictures and skips foreign ones", async () => {
    const origin = document.location.origin;
    const q = mount(`
      <div class="qtext"><img src="${origin}/a.png"><img src="https://evil.example/b.png"></div>`);
    const fetchImpl = vi.fn().mockResolvedValue(imageResponse("image/png", [104, 105]));

    const images = await collectImages(q, fetchImpl);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe(`${origin}/a.png`);
    expect(images).toEqual([{ mime: "image/png", data: "aGk=" }]);
  });

  it("drops disallowed formats and failed downloads", async () => {
    const origin = document.location.origin;
    const q = mount(`
      <div class="qtext"><img src="${origin}/a.svg"><img src="${origin}/b.png"></div>`);
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(imageResponse("image/svg+xml", [1]))
      .mockRejectedValueOnce(new TypeError("network"));

    expect(await collectImages(q, fetchImpl)).toEqual([]);
  });
});
