import "./design-system/base.css";

import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { createQueryClient } from "./app/queryClient";
import { createRouter } from "./app/router";

const root = document.getElementById("root");
if (!root) throw new Error("Falta el elemento #root");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createRouter()} />
    </QueryClientProvider>
  </StrictMode>,
);
