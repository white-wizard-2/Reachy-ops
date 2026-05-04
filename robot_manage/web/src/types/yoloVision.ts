export type YoloVisionState = {
  import_ok: boolean;
  weights_path: string | null;
  worker_running: boolean;
  /** Last known worker phase from server (e.g. ``running``, ``import_failed``). */
  worker_phase: string | null;
  worker_detail: string | null;
};

export type YoloTrackRow = {
  id: number | null;
  cls: number;
  label: string;
  conf: number;
  xyxy: [number, number, number, number];
};

/** Server message ``{ type: "yolo_detections", ... }`` (type field omitted in state). */
export type YoloDetectionsPayload = {
  frame_hw: [number, number];
  tracks: YoloTrackRow[];
  t_ms: number;
};
