import re
import os
import base64

file_path = "/usr/local/lib/python3.12/dist-packages/vllm/multimodal/video.py"

if os.path.exists(file_path):
    with open(file_path, "r") as f:
        content = f.read()

    new_func = """    def load_base64(
        self, media_type: str, data: str
    ) -> tuple[npt.NDArray, dict[str, Any]]:
        if media_type.lower() == "video/jpeg":
            load_frame = partial(
                self.image_io.load_base64,
                "image/jpeg",
            )
            
            # This is the fixed code
            '''
            > support video input with a list of base64-encoded extracted JPEG frames
            {
                "type": "video_url",
                "video_url": {"url": f"data:video/jpeg;base64,{','.join(video_base64_frames)}"},
                "fps": 1
            }
            '''
            frames = np.stack([np.asarray(load_frame(frame_data)) for frame_data in data.split(",")]) 
            total = int(frames.shape[0]) 
            fps = float(self.kwargs.get("fps", 1))     # Default is 1, change to your need 
            duration = (total / fps) if fps > 0 else 0.0 
            metadata = { 
                "total_num_frames": total, 
                "fps": fps, 
                "duration": duration, 
                "video_backend": "jpeg_sequence", 
                "frames_indices": list(range(total)), 
                "do_sample_frames": False, 
            } 

            return frames, metadata 

        return self.load_bytes(base64.b64decode(data))"""

    pattern = re.compile(r"    def load_base64\(.*?(?=    def |\Z)", re.DOTALL)
    
    if '"video_backend": "jpeg_sequence"' not in content:
        new_content = pattern.sub(new_func + "\n\n", content)
        with open(file_path, "w") as f:
            f.write(new_content)
        print(f"Patched {file_path} successfully", flush=True)
