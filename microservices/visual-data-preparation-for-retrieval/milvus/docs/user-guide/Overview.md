# Visual data preparation microservice

Preprocess visual data including images and videos and store their feature embeddings into a vector DB

## Overview
The Dataprep microservice is designed to preprocess visual data, including images and videos, and store their feature embeddings in a vector database for efficient retrieval. It leverages the CLIP model's image encoder to extract embeddings, enabling advanced search capabilities for large-scale datasets.

Key Features:

-    Video Processing:

        Extracts frames at configurable intervals for embedding generation.
    
-    Image/Frame Processing:

        Performs resizing, color conversion, normalization, and object detection with cropping.

        Object detection and cropping enhance retrieval performance for complex scene images, ensuring that key objects remain recognizable after resizing.

**Programming Language:** Python


## How It Works

The Dataprep microservice efficiently preprocesses visual data, including images and videos, and stores their feature embeddings in a vector database for advanced retrieval. It leverages the CLIP model's image encoder to extract embeddings, enabling robust search capabilities for large-scale datasets.

-    Video Processing:
        Frames are extracted at configurable intervals to ensure efficient embedding generation for video data.

-    Image/Frame Processing:
        Images and video frames undergo preprocessing steps such as resizing, color conversion, normalization, and object detection with cropping.
        Object detection and cropping enhance retrieval performance for complex scene images by preserving key objects that might otherwise become unrecognizable after resizing.

-    Metadata Linking:
        Cropped images are linked to their original images via metadata. During retrieval, if a cropped image matches, the original image is returned for context.


-    Host-Based Data Sources:
        Instead of uploading data, users can specify directories on the host machine as data sources. This approach is optimized for large datasets, allowing the microservice to process files sequentially or in batches.as input so that the microservice can process one-after-another or in batches.  


## Learn More
-    Start with the [Get Started](./get-started.md).