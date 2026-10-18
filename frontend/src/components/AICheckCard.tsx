import { useState } from "react";
import { post } from "../api";
import { useAuth } from "../auth";
import { trServer, useI18n } from "../lang";
import type { AICheck } from "../types";
import { Brain, CheckCircle, Lightning, WarningCircle, XCircle } from "./Icon";

/** "Test AI" button: one real request to the AI provider, showing the exact result. */
export default function AICheckCard({ path }: { path: string }) {
  const { t } = useI18n();
  const { user } = useAuth();
  // The technical details (model, server, key) only mean something to the platform owner.
  const technical = user?.role === "system_admin";
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

  const good = !!result && result.ok && result.uses_tools;
  const tone = !result ? "" : good ? "ok" : result.ok ? "warn" : "bad";
  return (
    <section className={`ad-card ai-card ${tone}`}>
      <div className="ai-status">
        <span className="ai-icon" aria-hidden="true"><Brain /></span>
        <div className="ai-status-text">
          <h2 className="ad-card-title">{t("AI brain status")}
            {result && !busy && (
              <span className={`ad-status ${good ? "on" : result.ok ? "warn" : "bad"}`}>
                {good ? t("Working") : result.ok ? t("Partly working") : t("Not working")}
              </span>
            )}
          </h2>
          <p className="ad-card-note">{t("Sends one test question to the AI and shows exactly what happens.")}</p>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={busy} aria-busy={busy}>
          {busy ? <><span className="login-spin" aria-hidden="true" />{t("Testing…")}</> : <><Lightning weight="fill" />{t("Test AI")}</>}
        </button>
      </div>
      <div aria-live="polite">
        {error && <div className="ai-result bad"><XCircle weight="fill" /><span>{error}</span></div>}
        {result && (
          <div className={`ai-result ${tone}`}>
            {good ? <CheckCircle weight="fill" /> : result.ok ? <WarningCircle weight="fill" /> : <XCircle weight="fill" />}
            <div>
              <strong>{good ? t("Working") : result.ok ? t("Partly working") : t("Not working")}</strong>
              {" · "}{trServer(result.message)}{" · "}<span className="tnum">{t("{n}s", { n: result.seconds })}</span>
              {technical && <div className="ai-tech">
                {t("Model:")} <code>{result.answered_by || result.model}</code>
                {result.fallback_models.length > 0 && <> ({t("backup:")} <code>{result.fallback_models.join(", ")}</code>)</>}
                {" · "}{t("Server:")} <code>{result.server}</code> · {t("API key:")} {result.api_key_set ? t("set") : t("missing")}
              </div>}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
