import os

import gradio as gr

from gstpipeline import PipelineLoader
from home_page import home
from pipelines.pipeline_page import Pipeline


def create_interface() -> gr.Blocks:
    with open(os.path.join(os.path.dirname(__file__), "app.css")) as f:
        css_code = f.read()

    theme = gr.themes.Default(  # pyright: ignore[reportPrivateImportUsage]
        primary_hue="blue",
        font=[gr.themes.GoogleFont("Montserrat"), "ui-sans-serif", "sans-serif"],  # pyright: ignore[reportPrivateImportUsage]
    )

    title: str = "Visual Pipeline and Platform Evaluation Tool"

    with gr.Blocks(theme=theme, css=css_code, title=title) as vippet:
        home.render()

    for p in PipelineLoader.list():
        pipeline = Pipeline(p)
        with vippet.route(pipeline.name, pipeline.route):
            pipeline.page.render()

    return vippet


if __name__ == "__main__":
    vippet = create_interface()
    vippet.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )
