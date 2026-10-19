import { Component, ReactNode } from "react";
import { tr } from "../lang";

/** A page that crashes shows a short message with a reload button instead of a blank screen.
 *  `resetKey` (the current address) clears the error when the person moves to another page. */
export default class ErrorBoundary extends Component<{ resetKey: string; children: ReactNode }, { failed: boolean; key: string }> {
  state = { failed: false, key: this.props.resetKey };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: { resetKey: string }, state: { failed: boolean; key: string }) {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null;
  }

  componentDidCatch(error: unknown) {
    console.error("Page error", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="page-crash" role="alert">
        <h2>{tr("This page could not be shown.")}</h2>
        <p>{tr("Reload to get the latest version of the app. If it happens again, tell us what you clicked.")}</p>
        <button className="btn btn-primary" onClick={() => window.location.reload()}>{tr("Reload")}</button>
      </div>
    );
  }
}
