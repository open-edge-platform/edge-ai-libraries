# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np

SYSTEM = (
    'Judge whether the Document meets the requirements based on the Query '
    'and the Instruct provided. Note that the answer can only be "yes" or "no".'
)
INSTRUCTION = "Given a search query, retrieve relevant candidates that answer the query."
VISUAL_SIZE = (160, 160)


def pad_frames(frames, count):
    """Exactly `count` frames: repeat the last one when a clip decodes short."""
    frames = list(frames)
    if not frames:
        raise ValueError("video produced no frames")
    if len(frames) >= count:
        return frames[:count]
    return frames + [frames[-1]] * (count - len(frames))


def pad_pair(values, positions, seq_len, pad_token_id):
    """Left-pad a scored pair to `seq_len` so one compiled graph serves all query lengths."""
    length = len(values["input_ids"][0])
    if length > seq_len:
        raise ValueError(f"pair is {length} tokens, beyond the {seq_len} bucket")
    pad = seq_len - length
    padded = dict(values)
    padded["input_ids"] = np.pad(
        np.asarray(values["input_ids"]), ((0, 0), (pad, 0)),
        constant_values=int(pad_token_id),
    )
    padded["attention_mask"] = np.pad(
        np.asarray(values["attention_mask"]), ((0, 0), (pad, 0)),
        constant_values=0,
    )
    padded_positions = np.pad(
        np.asarray(positions), ((0, 0), (0, 0), (pad, 0)), constant_values=0
    )
    return padded, padded_positions


def normalize_document(document):
    """Use the fixed visual grid traced into the current OpenVINO graphs."""
    from PIL import Image, ImageOps

    result = dict(document)

    def normalize(image):
        if not isinstance(image, Image.Image):
            raise TypeError("visual reranker inputs must be decoded PIL images")
        return ImageOps.pad(image.convert("RGB"), VISUAL_SIZE, color=(0, 0, 0))

    if "image" in result:
        result["image"] = normalize(result["image"])
    if "video" in result:
        result["video"] = [normalize(frame) for frame in result["video"]]
    return result


def _content(prefix, text=None, image=None, video=None):
    content = [{"type": "text", "text": prefix}]
    if video is not None:
        content.append({"type": "video", "video": video})
    if image is not None:
        content.append({
            "type": "image", "image": image,
            "min_pixels": 4 * 32 * 32, "max_pixels": 1280 * 32 * 32,
        })
    if text:
        content.append({"type": "text", "text": text})
    elif image is None and video is None:
        content.append({"type": "text", "text": "NULL"})
    return content


def encode(processor, query, document):
    from qwen_vl_utils import process_vision_info

    document = normalize_document(document)

    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM}]},
        {"role": "user", "content": [
            {"type": "text", "text": "<Instruct>: " + INSTRUCTION},
            *_content("<Query>:", text=query),
            *_content("\n<Document>:", **document),
        ]},
    ]
    text = processor.apply_chat_template(
        [messages], tokenize=False, add_generation_prompt=True
    )
    images, videos, video_kwargs = process_vision_info(
        [messages], image_patch_size=16,
        return_video_kwargs=True, return_video_metadata=True,
    )
    video_metadata = None
    if videos is not None:
        videos, video_metadata = zip(*videos)
        videos, video_metadata = list(videos), list(video_metadata)
    values = processor(
        text=text, images=images, videos=videos,
        video_metadata=video_metadata, truncation=False, padding=False,
        do_resize=False, **video_kwargs,
    )
    # Truncation keeps special tokens and the last five answer-prefix tokens.
    ids = list(values["input_ids"][0])
    if len(ids) > 8192:
        special = set(processor.tokenizer.all_special_ids)
        head, tail = ids[:-5], ids[-5:]
        budget = 8192 - len(tail) - sum(token in special for token in head)
        kept = []
        for token in head:
            if token in special:
                kept.append(token)
            elif budget > 0:
                kept.append(token)
                budget -= 1
        values["input_ids"] = [kept + tail]
    padded = processor.tokenizer.pad(
        {"input_ids": values["input_ids"]}, padding=True,
        return_tensors="np", max_length=8192,
    )
    values.update(padded)
    return values


def rope_position_ids(values, config):
    """Qwen3-VL three-axis rope positions for one unpadded pair (as Qwen3VLModel.get_rope_index)."""
    tokens = np.asarray(values["input_ids"])[0].tolist()
    image_id = int(config["image_token_id"])
    video_id = int(config["video_token_id"])
    vision_start_id = int(config["vision_start_token_id"])
    merge = int(config["vision_config"]["spatial_merge_size"])
    images = iter(np.asarray(values.get("image_grid_thw", [])).reshape(-1, 3).tolist())
    videos = np.asarray(values.get("video_grid_thw", [])).reshape(-1, 3)
    video_grids = iter(
        (1, int(h), int(w))
        for t, h, w in videos.tolist()
        for _ in range(int(t))
    )
    vision_types = [
        tokens[index + 1]
        for index, token in enumerate(tokens[:-1])
        if token == vision_start_id
    ]
    chunks = []
    start = 0
    offset = 0
    for kind in vision_types:
        if kind == image_id:
            grid = next(images)
        elif kind == video_id:
            grid = next(video_grids)
        else:
            continue
        end = tokens.index(kind, start)
        text_length = end - start
        chunks.append(np.broadcast_to(
            np.arange(text_length, dtype=np.int64) + offset, (3, text_length)
        ))
        offset += text_length
        t, h, w = map(int, grid)
        h //= merge
        w //= merge
        coordinates = np.stack(np.meshgrid(
            np.arange(t), np.arange(h), np.arange(w), indexing="ij"
        )).reshape(3, -1)
        chunks.append(coordinates + offset)
        offset = int(chunks[-1].max()) + 1
        start = end + t * h * w
    if start < len(tokens):
        tail = len(tokens) - start
        chunks.append(np.broadcast_to(
            np.arange(tail, dtype=np.int64) + offset, (3, tail)
        ))
    positions = np.concatenate(chunks, axis=1)
    if positions.shape[1] != len(tokens):
        raise ValueError("Qwen3-VL position count differs from token count")
    return positions[:, None, :]
