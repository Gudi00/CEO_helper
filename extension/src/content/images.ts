/**
 * Collects the pictures of a question so a vision model can see them.
 * Only same-origin images are read (the quiz page's own files), only raster
 * formats, and only within size limits the backend accepts.
 */

import type { QuestionImage, QuestionImageMime } from "@/shared/types.js";

export const MAX_IMAGES = 4;
export const MAX_IMAGE_BYTES = 1_000_000;
const ALLOWED: readonly string[] = ["image/png", "image/jpeg", "image/webp"];

export function isAllowedImage(mime: string, bytes: number): mime is QuestionImageMime {
  return ALLOWED.includes(mime) && bytes > 0 && bytes <= MAX_IMAGE_BYTES;
}

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function collectImages(
  container: HTMLElement,
  fetchImpl: typeof fetch = fetch,
): Promise<QuestionImage[]> {
  const origin = container.ownerDocument.location.origin;
  const urls = Array.from(
    container.querySelectorAll<HTMLImageElement>(".qtext img, .answer img"),
  )
    .map((img) => img.currentSrc || img.src)
    .filter((src) => {
      try {
        return new URL(src).origin === origin;
      } catch {
        return false;
      }
    });

  const out: QuestionImage[] = [];
  for (const url of [...new Set(urls)]) {
    if (out.length >= MAX_IMAGES) break;
    try {
      const resp = await fetchImpl(url, { credentials: "include" });
      if (!resp.ok) continue;
      const blob = await resp.blob();
      if (!isAllowedImage(blob.type, blob.size)) continue;
      out.push({
        mime: blob.type,
        data: toBase64(new Uint8Array(await blob.arrayBuffer())),
      });
    } catch {
      // A picture we can't read is skipped; the question still goes out.
    }
  }
  return out;
}
