export interface DataPrepMinioDTO {
  bucket_name: string;
  video_id: string;
  video_name: string;
  chunk_duration?: number;
  clip_duration?: number;
}

export interface DataPrepSummaryDTO {
  bucket_name: string;
  video_id: string;
  video_summary: string;
  video_start_time: number;
  video_end_time: number;
  tags: string[];
}

export interface DataPrepMinioRO {
  status: string;
  message: string;
}
