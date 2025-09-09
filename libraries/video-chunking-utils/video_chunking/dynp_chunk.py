import logging
import math
import ruptures as rpt

from video_chunking.data import MicroChunkMeta
from video_chunking.pelt_chunk import PeltChunking

logger = logging.getLogger(__name__)

# Debug
import os
DYNP_DATA_VIS_PATH = os.getenv("DYNP_DATA_VIS_PATH", None)

class DynpChunking(PeltChunking):
    
    METHOD_NAME = "dynp"

    def __init__(
        self,
        avg_chunk_duration: float = 10,
        min_chunk_duration: float = 1,
        **kwargs
    ):
        """Creates a Video Chunking object.
        Args:
            avg_chunk_duration: average duration for each chunk
        """
        super().__init__(**kwargs)
        
        self.pre_frame = None
        self.timestamps = []
        self.diff_scores = []
        self.avg_chunk_duration = avg_chunk_duration
        self.min_chunk_duration = min_chunk_duration

    def process(self) -> list[MicroChunkMeta]:
        """
        Process video chunking with collected diff_scores
        Return:
            list[MicroChunkMeta], A list of micro chunk metadata
        """
        
        # Combine features
        combined = self._normalize_and_combine(self.diff_scores)
            
        # Debug
        if DYNP_DATA_VIS_PATH is not None:
            import matplotlib.pyplot as plt
            filename = os.path.basename(self.video_input)
            video_name, _ = os.path.splitext(filename)
            color_diffs = [_[0] for _ in self.diff_scores]
            flow_diffs = [_[1] for _ in self.diff_scores]
            texture_diffs = [_[2] for _ in self.diff_scores]
            norm_corlor_diff = self._normalize(color_diffs)
            norm_flow_diff = self._normalize(flow_diffs)
            norm_texture_diff = self._normalize(texture_diffs)
            # Visualize
            fig, axs = plt.subplots(4, 1, figsize=(10, 11), sharey=True)
            self._plot_score_curve(norm_corlor_diff, plt=axs[0], sampling_interval=1, prefix="color")
            self._plot_score_curve(norm_flow_diff, plt=axs[1], sampling_interval=1, prefix="flow")
            self._plot_score_curve(norm_texture_diff, plt=axs[2], sampling_interval=1, prefix="texture")
            self._plot_score_curve(combined, plt=axs[3], sampling_interval=1, prefix="combine")        
            # Save the plot if save_path is provided
            save_to = os.path.join(DYNP_DATA_VIS_PATH+f"-fps{self.sample_fps}", f"{video_name}_score_for_dynp.jpg")
            os.makedirs(os.path.dirname(save_to), exist_ok=True)
            plt.tight_layout()
            plt.savefig(save_to)
            print(f"{save_to} saved.")
        
        # Calculate expected chunks
        total_duration = len(self.diff_scores) / self.sample_fps
        n_bkps = math.ceil(total_duration / self.avg_chunk_duration)
        
        min_size = self.sample_fps * self.min_chunk_duration
        logger.debug(f"Start dynp processing, avg-chunk-duration={self.avg_chunk_duration},"
                     f"total-duration={total_duration}, expected chunks num: {n_bkps}, "
                     f"min_size={min_size:.2f} (min chunk dur={self.min_chunk_duration}s)")
        best_segments = self._detect_segments(combined, self.timestamps, min_size=min_size, n_bkps=n_bkps)
        logger.debug(f"Process done, final chunks num: {len(best_segments)}")

        listMicroChunk = []
        for i in range(len(best_segments) - 1):
            start_time = best_segments[i]
            end_time = best_segments[i+1]
            micro_chunk = self.format_chunks(start_time, end_time)
            micro_chunk.id = i
            micro_chunk.level = 0
            listMicroChunk.append(micro_chunk)

        # clean up chunking context
        self._reset()
        
        return listMicroChunk
    
    def _detect_segments(self, combined_scores, timestamps, min_size, n_bkps=0, **kwargs):
        # 1. Use Dynp algorithm to detect change points
        algo = rpt.Dynp(model="l2", min_size=min_size).fit(combined_scores.reshape(-1,1))
        breakpoints = algo.predict(n_bkps=n_bkps)

        # 2. Handle case with no change points: return video start and end timestamps
        if not breakpoints:
            return [timestamps[0], timestamps[-1]]

        # 3. Filter invalid breakpoints and sort (defensive programming)
        breakpoints = sorted([b for b in breakpoints if 0 < b < len(timestamps)])

        # 4. Build segment timestamp list
        segments = [timestamps[0]]  # Start time
        segments.extend(timestamps[b] for b in breakpoints)  # Add all valid breakpoint times

        # 5. Force inclusion of video end time (avoid missing last segment)
        if segments[-1] != timestamps[-1]:
            segments.append(timestamps[-1])

        return segments
