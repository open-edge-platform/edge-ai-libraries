import os
from typing import List

import gradio as gr

from gstpipeline import PipelineLoader
from pipelines.pipeline_page import Pipeline
import home


def create_interface() -> gr.Blocks:
    with open(os.path.join(os.path.dirname(__file__), "app.css")) as f:
        css_code = f.read()

    theme = gr.themes.Default(  # pyright: ignore[reportPrivateImportUsage]
        primary_hue="blue",
        font=[gr.themes.GoogleFont("Montserrat"), "ui-sans-serif", "sans-serif"],  # pyright: ignore[reportPrivateImportUsage]
    )

    title: str = "Visual Pipeline and Platform Evaluation Tool"

    pipelines: List[Pipeline] = []
    for id, pipeline_dir in enumerate(PipelineLoader.list(), start=1):
        pipelines.append(Pipeline(id, pipeline_dir))

    with gr.Blocks(theme=theme, css=css_code, title=title) as vippet:
        # Header
        gr.HTML(
            "<div class='spark-header'>"
            "  <div class='spark-header-line'></div>"
            "  <img src='https://www.intel.com/content/dam/logos/intel-header-logo.svg' class='spark-logo'></img>"
            "  <div class='spark-title'>Visual Pipeline and Platform Evaluation Tool</div>"
            "</div>"
        )

        with gr.Tabs() as tabs:
            home.tab("Home", 0, pipelines, tabs)

            for pipeline in pipelines:
                if pipeline.enabled:
                    with gr.Tab(label=pipeline.config["name"], id=pipeline.id):
                        pipeline.tab()

        # Footer
        gr.HTML(
            "<div class='spark-footer'>"
            "  <div class='spark-footer-info'>"
            "    ©2025 Intel Corporation  |  Terms of Use  |  Cookies  |  Privacy"
            "  </div>"
            "</div>"
        )

    return vippet


if __name__ == "__main__":
    vippet = create_interface()
    vippet.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )
