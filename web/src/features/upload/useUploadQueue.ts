import { useSyncExternalStore } from "react";

import { uploadQueue } from "./queue";

export function useUploadQueue() {
  return useSyncExternalStore(uploadQueue.subscribe, uploadQueue.getSnapshot);
}
