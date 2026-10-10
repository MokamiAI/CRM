import React from "react";
import ReactDOM from "react-dom/client";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App.jsx";
import { AuthProvider } from "./context/AuthContext";
import "@fontsource-variable/inter";
import "./i18n";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
  // Reports aggregate everything (deals, payments, activities), so any
  // successful change anywhere refreshes them, instead of every mutation
  // having to remember to.
  mutationCache: new MutationCache({
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reports"] }),
  }),
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
        {/* Mounted once, at the root, outside every page and sheet. Top
            center so toasts never land on the phone tab bar or the
            document editor's pinned total bar; the mobile offset clears
            the notch inside the native shell. */}
        <Toaster
          position="top-center"
          richColors
          mobileOffset={{ top: "max(env(safe-area-inset-top, 0px), 16px)" }}
        />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
