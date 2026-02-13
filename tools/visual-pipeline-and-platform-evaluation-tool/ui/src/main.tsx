import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import router from "./routes.ts";
import "./index.css";
import { Provider } from "react-redux";
import { PersistGate } from "redux-persist/integration/react";
import { persistor, store } from "@/store";
import { MetricsProvider } from "@/features/metrics/MetricsProvider.tsx";
import { ThemeProvider } from "next-themes";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Provider store={store}>
      <PersistGate loading={null} persistor={persistor}>
        <ThemeProvider attribute="class" defaultTheme="light">
          <MetricsProvider>
            <RouterProvider router={router} />
          </MetricsProvider>
        </ThemeProvider>
      </PersistGate>
    </Provider>
  </StrictMode>,
);
