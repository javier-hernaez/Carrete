import { createBrowserRouter, type RouteObject } from "react-router";

import { AdminPage } from "../features/admin/AdminPage";
import { AuthGate } from "../features/auth/AuthGate";
import { InviteScreen, ResetScreen } from "../features/auth/screens";
import { SettingsPage } from "../features/settings/SettingsPage";
import { TrashPage } from "../features/trash/TrashPage";
import { SpaceSettingsPage } from "../features/space/SpaceSettingsPage";
import { AppShell } from "./AppShell";
import { PhotosPage } from "../features/photos/PhotosPage";
import { UploadPage } from "../features/upload/UploadPage";
import { ActivityPage } from "../features/activity/ActivityPage";
import { AlbumPage } from "../features/albums/AlbumPage";
import { AlbumsPage } from "../features/albums/AlbumsPage";
import { DuplicatesPage } from "../features/duplicates/DuplicatesPage";
import { ExportPage } from "../features/export/ExportPage";
import { DiscardedPage } from "../features/review/DiscardedPage";
import { ReviewPage } from "../features/review/ReviewPage";
import { MapPage } from "../features/map/MapPage";
import { MorePage, NotFoundPage } from "./pages";

export const routes: RouteObject[] = [
  // Públicas: se abren desde un enlace, con o sin sesión.
  { path: "invitacion/:token", element: <InviteScreen /> },
  { path: "restablecer/:token", element: <ResetScreen /> },
  {
    element: (
      <AuthGate>
        <AppShell />
      </AuthGate>
    ),
    children: [
      { index: true, element: <PhotosPage /> },
      { path: "revisar", element: <ReviewPage /> },
      { path: "albumes", element: <AlbumsPage /> },
      { path: "mapa", element: <MapPage /> },
      { path: "mas", element: <MorePage /> },
      { path: "subir", element: <UploadPage /> },
      { path: "ajustes", element: <SettingsPage /> },
      { path: "espacio", element: <SpaceSettingsPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "papelera", element: <TrashPage /> },
      { path: "albumes/:albumId", element: <AlbumPage /> },
      { path: "repetidas", element: <DuplicatesPage /> },
      { path: "descartadas", element: <DiscardedPage /> },
      { path: "actividad", element: <ActivityPage /> },
      { path: "exportar", element: <ExportPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}
