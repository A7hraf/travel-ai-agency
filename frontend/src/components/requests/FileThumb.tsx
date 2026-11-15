import { useEffect, useState } from "react";
import { download, fetchBlob } from "../../api";
import { useI18n } from "../../lang";
import type { RequestFile } from "../../types";
import { DownloadSimple, FilePdf } from "../Icon";

/** A request file's small preview (photos fetched with the login: files are never public) and download. */
export default function FileThumb({ ticketId, file, onError }: { ticketId: number; file: RequestFile; onError?: (m: string) => void }) {
  const { t } = useI18n();
  const [url, setUrl] = useState<string | null>(null);
  const image = file.content_type.startsWith("image/");
  useEffect(() => {
    if (!image) return;
    let gone = false;
    let made: string | null = null;
    fetchBlob(`/api/tickets/${ticketId}/files/${file.id}`).then(({ blob }) => {
      if (gone) return;
      made = URL.createObjectURL(blob);
      setUrl(made);
    }).catch(() => {});
    return () => { gone = true; if (made) URL.revokeObjectURL(made); };
  }, [ticketId, file.id, image]);
  const save = () => download(`/api/tickets/${ticketId}/files/${file.id}`, file.name).catch((e) => onError?.((e as Error).message));
  return (
    <button type="button" className="rw-thumb" onClick={save} title={t("Download {name}", { name: file.name })} aria-label={t("Download {name}", { name: file.name })}>
      {image ? (url ? <img src={url} alt="" /> : <span className="skeleton" />) : <FilePdf weight="duotone" />}
      <span className="rw-thumb-dl"><DownloadSimple /></span>
    </button>
  );
}
