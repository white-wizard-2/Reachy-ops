export type FeedStatus = "live" | "offline" | "unavailable";

export interface CameraFeedInfo {
  id: string;
  label: string;
  channel: string;
  status: FeedStatus;
  stream_path: string | null;
  detail: string | null;
  specs_class?: string | null;
}

export interface CameraLayoutResponse {
  feeds: CameraFeedInfo[];
  sdk_single_stream: boolean;
  error?: string;
}
