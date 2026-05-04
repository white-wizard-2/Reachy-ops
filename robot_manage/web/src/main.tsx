import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { AppSocketProvider } from "./AppSocketContext";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppSocketProvider>
      <App />
    </AppSocketProvider>
  </StrictMode>,
);
