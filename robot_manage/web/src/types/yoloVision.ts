export type YoloVisionState = {
  import_ok: boolean;
  weights_path: string | null;
  worker_running: boolean;
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
