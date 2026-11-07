import { createBrowserRouter, type RouteObject } from "react-router";

import { AppShell } from "./AppShell";
import { AlbumsPage, MapPage, MorePage, NotFoundPage, PhotosPage, ReviewPage, UploadPage } from "./pages";

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <PhotosPage /> },
      { path: "revisar", element: <ReviewPage /> },
      { path: "albumes", element: <AlbumsPage /> },
      { path: "mapa", element: <MapPage /> },
      { path: "mas", element: <MorePage /> },
      { path: "subir", element: <UploadPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}
