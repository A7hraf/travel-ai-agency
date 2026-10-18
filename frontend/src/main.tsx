import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { IconContext } from "./components/Icon";
import { LangProvider } from "./lang";
// Ghanjah brand fonts, served with the app (no outside requests): Source Serif 4 for English,
// Noto Naskh Arabic for Arabic.
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/source-serif-4/400-italic.css";
import "@fontsource/noto-naskh-arabic/arabic-500.css";
import "@fontsource/noto-naskh-arabic/arabic-700.css";
import "./styles/base.css";
import "./styles/staff.css";
import "./styles/admin.css";
import "./styles/storefront.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <LangProvider>
        <IconContext.Provider value={{ size: "1.15em", weight: "duotone", mirrored: false }}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </IconContext.Provider>
      </LangProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
