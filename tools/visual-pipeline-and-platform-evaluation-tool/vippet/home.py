import gradio as gr
from typing import List

from device import DeviceDiscovery
from pipelines.pipeline_page import Pipeline


def tab(label: str, id: int, pipelines: List[Pipeline], tabs: gr.Tabs) -> gr.Tab:
    with gr.Tab(label=label, id=id) as home:
        gr.Markdown(
            """
            ## Recommended Pipelines

            Below is a list of recommended pipelines you can use to evaluate video analytics performance.
            Click on "Configure and Run" to get started with customizing and benchmarking a pipeline for your
            use case.
            """
        )

        with gr.Row():
            for pipeline in pipelines:
                with gr.Column(scale=1, min_width=100):
                    gr.Image(
                        value=f"./pipelines/{pipeline.dir}/thumbnail.png",
                        show_label=False,
                        show_download_button=False,
                        show_fullscreen_button=False,
                        interactive=False,
                        width=710,
                    )

                    gr.Markdown(
                        f"### {pipeline.config['name']}\n{pipeline.config['definition']}"
                    )

                    btn = gr.Button(
                        value=(
                            "Configure and Run" if pipeline.enabled else "Coming Soon"
                        ),
                        elem_classes="configure-and-run-button",
                        interactive=pipeline.enabled,
                    )
                    btn.click(
                        fn=lambda tab_id=pipeline.id: gr.Tabs(selected=tab_id),
                        outputs=tabs,
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
                device_table_md += (
                    f"| {device.device_name} | {device.full_device_name} |\n"
                )
        else:
            device_table_md = "No devices found."

        gr.Markdown(
            value=device_table_md,
            elem_id="device_table",
        )

    return home
