import { useState } from "react";
import { post } from "../api";
import { useI18n } from "../lang";
import type { AICheck } from "../types";

/** "Test AI" button: one real request to the AI provider, showing the exact result. */
export default function AICheckCard({ path }: { path: string }) {
  const { t } = useI18n();
  const [result, setResult] = useState<AICheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await post<AICheck>(path));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <div className="ai-status">
        <div>
          <h3>{t("AI brain status")}</h3>
          <p className="muted small">{t("Sends one test question to the AI and shows exactly what happens.")}</p>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? t("Testing…") : t("Test AI")}</button>
      </div>
      {error && <div className="ai-result bad">{error}</div>}
      {result && (
        <div className={`ai-result ${result.ok && result.uses_tools ? "ok" : "bad"}`}>
          <strong>{result.ok ? (result.uses_tools ? `✓ ${t("Working")}` : `⚠ ${t("Partly working")}`) : `✕ ${t("Not working")}`}</strong>
          {" · "}{result.message}
          <div className="small" style={{ marginTop: ".35rem" }}>
            {t("Model:")} <code>{result.answered_by || result.model}</code>
            {result.fallback_models.length > 0 && <> ({t("backup:")} <code>{result.fallback_models.join(", ")}</code>)</>}
            {" · "}{t("Server:")} <code>{result.server}</code> · {t("API key:")} {result.api_key_set ? t("set") : t("missing")} · {t("{n}s", { n: result.seconds })}
          </div>
        </div>
      )}
    </section>
  );
}
