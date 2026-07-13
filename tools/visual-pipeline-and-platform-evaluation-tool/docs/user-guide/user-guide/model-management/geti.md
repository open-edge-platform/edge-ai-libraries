# Using Models from Geti

Geti™ is a model development platform for training and fine-tuning computer vision models with a guided workflow.
It helps teams prepare datasets, annotate samples, train models, review accuracy, and export results
without building the full training pipeline by hand.

In the context of ViPPET, Geti™ is a practical way to create custom models that can later be exported
in OpenVINO™ IR format and uploaded to the platform.

## Training a model in Geti

The exact steps depend on the task type, but the typical workflow is:

1. Create a project in Geti™ and choose the task type, such as classification, detection, or segmentation.
2. Upload your training images or video frames and organize the dataset.
3. Annotate the data using Geti™'s labeling tools, then review the annotations for quality and consistency.
4. Start a training job and let Geti™ train the model on the labeled dataset.
5. Evaluate the training results and, if needed, improve the dataset with more samples or corrected labels.
6. Export the trained model in OpenVINO™ format and download the generated files.

After export, package the model files and upload them through the ViPPET model upload flow described in the
[Model Management](../model-management.md) section.

For detailed project creation, annotation, and training instructions, refer to the
[Geti™ documentation](https://docs.geti.intel.com/).
