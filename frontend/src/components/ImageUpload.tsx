import { ChangeEvent, useRef, useState } from "react";
import { post } from "../api";
import { useI18n } from "../lang";

const MAX_BYTES = 2_400_000;

function canvasBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

function blobBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/** Shrinks the photo in the browser (keeps uploads small and strips camera metadata). */
async function prepare(file: File, maxSide: number): Promise<{ type: string; data: string }> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  // WebP keeps logo transparency; browsers that can't write WebP return PNG, then JPEG is the fallback.
  for (const [type, quality] of [["image/webp", 0.85], ["image/jpeg", 0.85], ["image/jpeg", 0.6]] as const) {
    const blob = await canvasBlob(canvas, type, quality);
    if (!blob) continue;
    if (!["image/webp", "image/jpeg", "image/png"].includes(blob.type)) continue;
    if (blob.size <= MAX_BYTES) return { type: blob.type, data: await blobBase64(blob) };
  }
  throw new Error("too-large");
}

/** Pick a photo from the device, upload it and get back its address. */
export default function ImageUpload({ value, onChange, endpoint = "/api/media", maxSide = 1600, label, contain }: {
  value: string | null;
  onChange: (url: string | null) => void;
  endpoint?: string;
  maxSide?: number;
  label?: string;
  contain?: boolean;
}) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError(t("Please choose a photo (JPEG, PNG or WebP)."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const img = await prepare(file, maxSide);
      const res = await post<{ url: string }>(endpoint, { content_type: img.type, data_base64: img.data });
      onChange(res.url);
    } catch (err) {
      setError(err instanceof Error && err.message !== "too-large" && !(err instanceof DOMException)
        ? err.message : t("This photo could not be used. Try another one."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="image-upload">
      <div className={`image-preview ${contain ? "contain" : ""}`}>
        {value ? <img src={value} alt="" /> : <span className="muted small">{t("No photo")}</span>}
      </div>
      <div className="image-actions">
        <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={pick} />
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? t("Uploading…") : label ?? (value ? t("Change photo") : t("Upload photo"))}
        </button>
        {value && !busy && (
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => onChange(null)}>{t("Remove")}</button>
        )}
        {error && <div className="field-hint error-text">{error}</div>}
      </div>
    </div>
  );
}
