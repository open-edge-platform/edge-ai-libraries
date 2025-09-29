import gradio as gr

from gstpipeline import PipelineLoader
from device import DeviceDiscovery

with gr.Blocks() as home:
    # Header
    gr.HTML(
        "<div class='spark-header'>"
        "  <div class='spark-header-line'></div>"
        "  <img src='https://www.intel.com/content/dam/logos/intel-header-logo.svg' class='spark-logo'></img>"
        "  <div class='spark-title'>Visual Pipeline and Platform Evaluation Tool</div>"
        "</div>"
    )

    gr.Markdown(
        """
        ## Recommended Pipelines

        Below is a list of recommended pipelines you can use to evaluate video analytics performance.
        Click on "Configure and Run" to get started with customizing and benchmarking a pipeline for your
        use case.
        """
    )

    with gr.Row():
        for pipeline in PipelineLoader.list():
            pipeline_info = PipelineLoader.config(pipeline)

            with gr.Column(scale=1, min_width=100):
                gr.Image(
                    value=lambda x=pipeline: f"./pipelines/{x}/thumbnail.png",
                    show_label=False,
                    show_download_button=False,
                    show_fullscreen_button=False,
                    interactive=False,
                    width=710,
                )

                gr.Markdown(
                    f"### {pipeline_info['name']}\n{pipeline_info['definition']}"
                )

                is_enabled = pipeline_info.get("metadata", {}).get("enabled", False)

                gr.Button(
                    value=("Configure and Run" if is_enabled else "Coming Soon"),
                    elem_classes="configure-and-run-button",
                    interactive=is_enabled,
                    link=f"/{pipeline}",
                )

    gr.Markdown(
        """
        ## Your System

        This section provides information about your system's hardware and software configuration.
        """
    )

    device_discovery = DeviceDiscovery()
    devices = device_discovery.list_devices()
    if devices:
        device_table_md = "| Name | Description |\n|------|-------------|\n"
        for device in devices:
            device_table_md += f"| {device.device_name} | {device.full_device_name} |\n"
    else:
        device_table_md = "No devices found."

    gr.Markdown(
        value=device_table_md,
        elem_id="device_table",
    )

    # Footer
    gr.HTML(
        "<div class='spark-footer'>"
        "  <div class='spark-footer-info'>"
        "    ©2025 Intel Corporation  |  Terms of Use  |  Cookies  |  Privacy"
        "  </div>"
        "</div>"
    )
