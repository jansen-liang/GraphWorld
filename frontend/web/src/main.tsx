import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import { AppProviders } from "./app/providers";
import { App } from "./app/App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </React.StrictMode>,
);
