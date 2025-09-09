import logging
import cv2
import numpy as np
import ruptures as rpt
from skimage.feature import local_binary_pattern

from video_chunking.data import MicroChunkMeta
from video_chunking.base_chunk import BaseChunking

logger = logging.getLogger(__name__)

# Debug
import os
PELT_DATA_VIS_PATH = os.getenv("PELT_DATA_VIS_PATH", None)

class PeltChunking(BaseChunking):
    
    METHOD_NAME = "pelt"

    def __init__(
        self,
        initial_pen: float = 20,
        max_iteration: int = 5,
        min_avg_duration: float = 10,
        max_avg_duration: float = 45,
        min_chunk_duration: float = 1,
        **kwargs
    ):
        """Creates a Video Chunking object.
        Args:
            initial_pen: initial penalty value (>0)
            max_iteration: max iteration for pelt searching
            min_avg_duration: Minimum allowed average segment duration
            max_avg_duration: Maximum allowed average segment duration
            min_chunk_duration: Minimum allowed segment duration
        """
        super().__init__(**kwargs)

        self.initial_pen = initial_pen
        self.max_iteration = max_iteration
        self.min_avg_duration = min_avg_duration
        self.max_avg_duration = max_avg_duration
        self.min_chunk_duration = min_chunk_duration
        
        self.pre_frame = None
        self.timestamps = []
        self.diff_scores = []
    
    def _init_frame_set(self, frame: np.ndarray):
        
        '''
        Processing frames from several views, will be used to calcuate diff scores
        Args:
            frame(np.ndarray): input single frame
        Return:
            An initialzed frame set with several fields:
            > origin
            > hsv_historgram
            > gray
            > lbp_historgam
        '''        
        # Convert RGB to BGR then to HSV (ffmpeg outputs RGB images)
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)

        # Calculate HSV histograms
        hsv_historgram = cv2.calcHist([hsv_frame], [0, 1], None, [180, 256], [0, 180, 0, 256])

        # Normalize histograms
        cv2.normalize(hsv_historgram, hsv_historgram)

        # Convert to grayscale and resize
        # resize for faster computation
        scale_factor = 0.25
        gray_frame = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), None, fx=scale_factor, fy=scale_factor)

        # Use grayscale images for LBP calculation
        lbp = local_binary_pattern(gray_frame, P=8, R=1, method='uniform')

        # Calculate LBP histograms
        lbp_histogram = np.histogram(lbp, bins=59, range=(0, 58))[0]
        
        frame_set = {
            'origin': frame,
            'hsv_histogram': hsv_historgram,
            'gray': gray_frame,
            'lbp_histogram': lbp_histogram
        }
        return frame_set
    
    def chunk(self,
              video_input: str,
              ) -> list[MicroChunkMeta]:
        """
        Process video chunking with video_input
        Args:
            video_input: the path of video. support "file://", "http://", "https://" and local path.
        Return:
            list[MicroChunkMeta], A list of micro chunk metadata
        """
        
        # To avoid OOM, do not read all frames at once
        while True:
            frames, timestamps = self.read_video_next_nframes(video_input, num_frames=10)
            if not frames:
                break
            self.update(frames, timestamps)
            
        # debug
        self.video_input = video_input
        
        # Achieve end of video, start to detect change points
        # return all micro chunks
        return self.process()
    
    def update(self, 
               frame: np.ndarray | list[np.ndarray],
               timestamp: float | list[float],
               ):
        """
        Collect frame difference scores while receiving decoded frames and corresponding timestamps
        Args:
            frame:
            timestamp
        """
        frame_sets = []
        if isinstance(frame, np.ndarray) and isinstance(timestamp, float):
            frame_sets.append(self._init_frame_set(frame))
            self.timestamps.append(timestamp)
        elif isinstance(frame, list) and isinstance(timestamp, list):
            frame_sets.extend([self._init_frame_set(_) for _ in frame])
            self.timestamps.extend(timestamp)
        else:
            raise RuntimeError(f"Invalid input type: frame({type(frame)}), timestamp({type(timestamp)})")
        
        # Calculate inter-frame differences
        if self.pre_frame is not None:
            frame_sets.insert(0, self.pre_frame)
        for i in range(1, len(frame_sets)):
            diff = self._calculate_differences(frame_sets[i], frame_sets[i - 1])
            self.diff_scores.append(diff)
        
        # Save previous frame sets for next time calculation
        self.pre_frame = frame_sets[-1]

    def process(self) -> list[MicroChunkMeta]:
        """
        Process video chunking with collected diff_scores
        Return:
            list[MicroChunkMeta], A list of micro chunk metadata
        """
        
        # Combine features
        combined = self._normalize_and_combine(self.diff_scores)
            
        # Debug
        if PELT_DATA_VIS_PATH is not None:
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
            save_to = os.path.join(PELT_DATA_VIS_PATH+f"-fps{self.sample_fps}", f"{video_name}_score_for_pelt.jpg")
            os.makedirs(os.path.dirname(save_to), exist_ok=True)
            plt.tight_layout()
            plt.savefig(save_to)
            print(f"{save_to} saved.")
        
        # Automatically adjust pen value
        pen = self.initial_pen
        min_size = self.sample_fps * self.min_chunk_duration

        logger.debug(f"Start pelt processing, initial pen={self.initial_pen:.1f}, "
                     f"min_size={min_size:.2f} (min chunk dur={self.min_chunk_duration}s)")
        
        best_pen = pen
        best_segments = []
        for i in range(self.max_iteration):
            '''
            > min_size: The minimum segment length between two change points.
            > combined: frame-level score, each second has {self.sample_fps} scores.
            
            >> How to set proper `min_size`:
                min_size = self.sample_fps * {acceptable_minimum_clip_duration}
                Then you can get the chunk with no less than `self.min_chunk_duration` time.
            '''
            segments = self._detect_segments(combined, self.timestamps, 
                                             min_size=min_size, pen=pen)

            # Calculate segment durations
            durations = [segments[i+1]-segments[i] for i in range(len(segments)-1)]
            avg_duration = np.mean(durations) if durations else 0
            
            ## Debug
            if PELT_DATA_VIS_PATH is not None:
                rpt.display(combined, [_ * self.sample_fps for _ in segments])
                plt.title("Change Point Detection: Pelt Method")
                # Save the plot if save_path is provided
                save_folder = os.path.join(PELT_DATA_VIS_PATH, f"pelt-min{self.min_chunk_duration}s")
                save_to = os.path.join(save_folder, f"{video_name}_try{i}_{len(segments)-1}chunks_avg{avg_duration:.2f}s.jpg")
                os.makedirs(os.path.dirname(save_to), exist_ok=True)
                plt.savefig(save_to)

            logger.debug(f"Trying pen={pen:.1f}, average segment duration={avg_duration:.2f}s, "
                         f"num segments: {len(durations)}")

            # Check if conditions are met
            if self.min_avg_duration <= avg_duration <= self.max_avg_duration:
                best_segments = segments
                best_pen = pen
                break
            elif avg_duration < self.min_avg_duration:
                # Segments too short, increase pen to get fewer segments
                pen *= 2
                best_segments = segments  # Record current best
                best_pen = pen
            else:
                # Segments too long, decrease pen to get more segments
                pen *= 0.5
                best_segments = segments  # Record current best
                best_pen = pen

        # If iteration ends without finding ideal value, use closest value
        if not best_segments:
            best_segments = self._detect_segments(combined, self.timestamps, 
                                                  min_size=min_size, pen=self.initial_pen)
            best_pen = self.initial_pen

        # Final check
        durations = [best_segments[i+1]-best_segments[i] for i in range(len(best_segments)-1)]
        avg_duration = np.mean(durations) if durations else 0
        logger.debug(f"Final choice: pen={best_pen:.1f}, average segment duration={avg_duration:.2f}s, "
                     f"num segments: {len(durations)}")

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
    
    def _detect_segments(self, combined_scores, timestamps, min_size, pen=5, **kwargs):
        # 1. Use Pelt algorithm to detect change points
        algo = rpt.Pelt(model="l2", min_size=min_size).fit(combined_scores.reshape(-1,1))
        breakpoints = algo.predict(pen=pen)

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

    def _calculate_differences(self, prev_frame_sets, curr_frame_sets):
        '''
        frame_set = {
            'origin': frame,
            'hsv_histogram': hsv_histogram,
            'gray': gray_frame,
            'lbp_histogram': hsv_histogram
        }
        '''
        
        # Color difference (Bhattacharyya distance of HSV histograms)
        hist_prev = prev_frame_sets['hsv_histogram']
        hist_curr = curr_frame_sets['hsv_histogram']
        color_diff = cv2.compareHist(hist_prev, hist_curr, cv2.HISTCMP_BHATTACHARYYA)

        # Optical flow difference from gray scale frame
        prev_gray = prev_frame_sets['gray']
        curr_gray = curr_frame_sets['gray']
        flow = cv2.calcOpticalFlowFarneback(prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        flow_diff = np.mean(np.sqrt(flow[..., 0]**2 + flow[..., 1]**2))

        # Texture difference (Chi-square distance of LBP histograms)
        lbp_hist_prev = prev_frame_sets['lbp_histogram']
        lbp_hist_curr = curr_frame_sets['lbp_histogram']
        texture_diff = 0.5 * np.sum((lbp_hist_prev - lbp_hist_curr)**2 / (lbp_hist_prev + lbp_hist_curr + 1e-10))

        return color_diff, flow_diff, texture_diff
    
    def _normalize_and_combine(self, diffs):
        diffs = np.array(diffs)
        normalized = (diffs - np.mean(diffs, axis=0)) / np.std(diffs, axis=0)
        return np.sum(normalized, axis=1)
    
    def _normalize(self, diff):
        diff = np.array(diff)
        normalized = (diff - np.mean(diff)) / np.std(diff)
        return normalized
    
    def _reset(self):
        self.pre_frame = None
        self.timestamps = []
        self.diff_scores = []  

    # debug
    def _plot_score_curve(self, data, sampling_interval=1, prefix='', plt=None):
        """
        Plot a curve of the given data array, allowing control of the x-axis points via sampling interval.

        Parameters:
        data (numpy.ndarray): A numpy array with shape [N, 1].
        sampling_interval (int): Sampling interval, default is 1.
        """
        if PELT_DATA_VIS_PATH is None:
            return
        import matplotlib.pyplot as plt
        if not isinstance(data, np.ndarray):
            raise ValueError("Input data must be a numpy array")
        
        data = data.reshape(-1,1)
        
        # Extract data
        y = data.flatten()
        N = len(y)
        
        # Generate x-axis data based on sampling interval
        x = np.arange(0, N, sampling_interval)
        # Extract corresponding y-axis data
        y_sampled = y[x]
        
        # Plot the curve
        if plt is None:
            plt.figure(figsize=(10, 2))
            plt.plot(x, y_sampled)
        else:
            plt.plot(x, y_sampled)
            plt.set_ylabel(prefix)
        
        # Find out points with highest value
        top_15_indices = np.argsort(y_sampled)[-15:]
        top_15_x = x[top_15_indices]
        top_15_y = y[top_15_indices]
        plt.scatter(top_15_x, top_15_y, color='red', s=50, zorder=5)
        for i, txt in enumerate(zip(top_15_x, top_15_y)):
            seconds = int(txt[0] / self.sample_fps)
            mins = int(seconds // 60)
            secs = int(seconds % 60 )
            plt.annotate(f'({mins:02d}m{secs:02d}s)', (top_15_x[i], top_15_y[i]), textcoords="offset points", xytext=(0,10), ha='center')
        
        # plt.tight_layout()
        # plt.title('Curve Plot with Top 15 Highlights')
        
        if plt is None:
            # Save the plot if save_path is provided
            save_to = os.path.join(PELT_DATA_VIS_PATH, f"{prefix}_score_for.jpg")
            os.makedirs(os.path.dirname(save_to), exist_ok=True)
            plt.savefig(save_to)
            print(f"{save_to} saved.")
