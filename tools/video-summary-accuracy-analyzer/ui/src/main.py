# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import gradio as gr
import json
import logging
import requests
import os
import pandas as pd
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

APP_BACKEND_URL = os.getenv("APP_BACKEND_URL", "http://localhost:9000/v1/eval")

# Bound outbound calls to the backend so a hung/slow backend cannot stall the UI indefinitely (SDL423/DoS).
REQUEST_TIMEOUT = float(os.getenv("APP_REQUEST_TIMEOUT", "300"))

# Define the sample markdown string
SAMPLE_MARKDOWN = """
**Instructions:** To use this application, please provide a markdown file with two sections titled 'Reference' and 'Generated', as shown in the example below.

### Example Markdown Format

```markdown
## Reference
<Your reference text goes here.>

## Generated
<Your machine-generated text goes here.>
```
---
"""


# Map dropdown options to API endpoints
METRIC_ENDPOINTS = {
    "bert-score": f"{APP_BACKEND_URL}/bert-score",
    "semantic-score": f"{APP_BACKEND_URL}/semantic-score",
    "rouge-score": f"{APP_BACKEND_URL}/rouge-score",
    "factual-consistency": f"{APP_BACKEND_URL}/factual-entailment"
}

METRIC_DESC= {
    "bert-score": "BERTScore leverages pre-trained contextual embeddings from BERT and similar models to evaluate text generation quality. It captures semantic similarity between texts by comparing their token-level embeddings, providing a more nuanced assessment than traditional metrics.",
    "semantic-score": "Captures meaning alignment beyond exact words; handles paraphrasing and synonyms.",
    "rouge-score": "Recall-Oriented Understudy for Gisting Evaluation. Measures how much of the important content/events are captured in the summary.",
    "factual-consistency": "Determines logical relationships between two text pieces. Evaluates how texts relate to each other."
}


def show_metric_description(choice):
    """Function to display the description for the selected option."""
    return METRIC_DESC.get(choice, "No description available.")


def preview_uploaded_file(file):
    """Extract and display Reference/Generated sections from uploaded markdown."""
    if file is None:
        return (
            gr.update(value="", visible=False),
            gr.update(value="", visible=False),
        )

    file_ext = os.path.splitext(file.name)[1].lower()
    if file_ext != ".md":
        return (
            gr.update(value="Unsupported file format. Please upload a .md file.", visible=True),
            gr.update(value="Unsupported file format. Please upload a .md file.", visible=True),
        )

    try:
        with open(file.name, "r", encoding="utf-8") as f:
            content = f.read()

        # Split content by markdown headings like: ## Reference / ## Generated
        parts = re.split(r"(?im)^\s{0,3}#{1,6}\s*(Reference|Generated)\s*$", content)

        sections = {}
        for i in range(1, len(parts), 2):
            key = parts[i].strip().lower()
            value = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections[key] = value

        reference_text = sections.get("reference", "")
        generated_text = sections.get("generated", "")

        if not reference_text:
            reference_text = "Reference section not found in uploaded file."
        if not generated_text:
            generated_text = "Generated section not found in uploaded file."

        return (
            gr.update(value=reference_text, visible=True),
            gr.update(value=generated_text, visible=True),
        )
    except Exception:
        logger.exception("Failed to read uploaded file")
        error_msg = "Failed to read the uploaded file. Please verify the file and try again."
        return (
            gr.update(value=error_msg, visible=True),
            gr.update(value=error_msg, visible=True),
        )

def submit_file(file):
    if file is None:
        return "Please upload a .md file."

    # Validate file format
    file_ext = os.path.splitext(file.name)[1].lower()
    if file_ext not in [".md"]:
        return "Unsupported file format. Please upload a .md file."

    eval_endpoint = f"{APP_BACKEND_URL}/evaluate"
    try:
        with open(file.name, "rb") as f:
            response = requests.post(eval_endpoint, files={"file": (file.name, f, "multipart/form-data")}, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            data = response.json()

            # ---------- A) Extract summaries FIRST from original `data` ----------
            summary = {}
            coherence_summary = {}

            # Defensive checks
            is_list = isinstance(data, list)

            # Factual summary is expected as the LAST item
            if is_list and len(data) >= 1 and isinstance(data[-1], dict) and "Factual Consistency Summary" in data[-1]:
                summary = data[-1]["Factual Consistency Summary"]
                data_wo_last = data[:-1]
            else:
                data_wo_last = data

            # Temporal coherence summary is expected as the SECOND LAST item (which is now the LAST of data_wo_last, after removing factual summary)
            if isinstance(data_wo_last, list) and len(data_wo_last) >= 1 and isinstance(data_wo_last[-1], dict) and "Temporal Coherence Summary" in data_wo_last[-1]:
                coherence_summary = data_wo_last[-1]["Temporal Coherence Summary"]
                rows_source = data_wo_last[:-1]   # drop that as well
            else:
                rows_source = data_wo_last

            # ---------- B) Build the comparisons table from `rows_source` ----------
            REQUIRED_KEYS = {"reference_sentence", "matched_sentence"}
            comparisons = [
                dict(r) for r in (rows_source or [])
                if isinstance(r, dict) and REQUIRED_KEYS.issubset(r.keys())
            ]

            # Pretty-print JSON fields without mutating the originals
            for row in comparisons:
                bs = row.get("bert_score")
                row["bert_score"] = (
                    json.dumps(bs, indent=2, ensure_ascii=False)
                    if isinstance(bs, dict) else ("" if bs is None else str(bs))
                )
                rs = row.get("rouge_score")
                row["rouge_score"] = (
                    json.dumps(rs, indent=2, ensure_ascii=False)
                    if isinstance(rs, dict) else ("" if rs is None else str(rs))
                )

            if not comparisons:
                df = pd.DataFrame()
            else:
                df = pd.DataFrame(comparisons)
                rename_map = {
                    "reference_sentence": "Reference Sentence",
                    "matched_sentence": "Matched Sentence",
                    "similarity_score": "Cosine Similarity",
                    "factual_consistency": "NLI Label",
                    "bert_score": "BERT Score",
                    "rouge_score": "ROUGE Score",
                }
                df = df.rename(columns=rename_map)

                # Safety: drop rows that are entirely empty in core columns
                core_cols = [c for c in ["Reference Sentence", "Matched Sentence", "NLI Label", "Cosine Similarity"] if c in df.columns]
                if core_cols:
                    df = df.dropna(subset=core_cols, how="all")

                # Insert running number
                df.insert(0, "No.", range(1, len(df) + 1))

                # Round numeric
                if "Cosine Similarity" in df.columns:
                    df["Cosine Similarity"] = pd.to_numeric(df["Cosine Similarity"], errors="coerce").round(4)

                # Desired order
                desired_cols = ["No.", "Reference Sentence", "Matched Sentence", "NLI Label", "Cosine Similarity", "BERT Score", "ROUGE Score"]
                df = df[[c for c in desired_cols if c in df.columns]]

            # Final guard, fix numbering after any drops
            if not df.empty:
                df = df.dropna(how="all").reset_index(drop=True)
                if "No." in df.columns:
                    df["No."] = range(1, len(df) + 1)

            # ---------- C) Build summary outputs ----------
            # Factual summary is a list-of-dicts (3 columns); coherence summary is a flat dict
            def as_summary_df(d) -> pd.DataFrame:
                if isinstance(d, list) and d:
                    return pd.DataFrame(d)
                if isinstance(d, dict) and d:
                    return pd.DataFrame(list(d.items()), columns=["Metric", "Value"])
                return pd.DataFrame(columns=["Metric", "Value"])

            factual_df = as_summary_df(summary)
            coherence_df = as_summary_df(coherence_summary)

            # Prepare updates (fix row_count so no blank trailing row appears)
            result_table_update = gr.update(value=df, row_count=(len(df), "fixed"))
            factual_update = gr.update(value=factual_df, row_count=(len(factual_df), "fixed"))
            coherence_update = gr.update(value=coherence_df, row_count=(len(coherence_df), "fixed"))

            # Titles (if you have Text components for titles)
            result_title_text = f"Sentence Comparisons ({len(df)} rows)" if not df.empty else "Sentence Comparisons"
            factual_title_text = "Factual Consistency Summary"
            coherence_title_text = "Temporal Coherence Summary"

            # Return in your expected order:
            # outputs=[result_table, output_summary, result_title, coherence_result_title, coherence_output_summary]
            return (
                result_table_update,
                factual_update,
                coherence_update,
            )

        else:
            error_df = pd.DataFrame([{"Error": f"{response.status_code}: {response.text}"}])
            empty_df = pd.DataFrame()
            return (
                gr.update(value=error_df, row_count=(1, "fixed")),
                gr.update(value=empty_df, row_count=(0, "fixed")),
                gr.update(value=empty_df, row_count=(0, "fixed")),
            )

    except Exception:
        logger.exception("Evaluation request failed")
        error_df = pd.DataFrame([{"Error": "Evaluation failed. Please try again or contact support if this persists."}])
        empty_df = pd.DataFrame()
        return (
            gr.update(value=error_df, row_count=(1, "fixed")),
            gr.update(value=empty_df, row_count=(0, "fixed")),
            gr.update(value=empty_df, row_count=(0, "fixed")),
        )


def evaluate_metrics(reference, generated, metric):
    if not reference or not generated:
        return "Please enter both reference and generated text."

    metric_endpoint = METRIC_ENDPOINTS.get(metric)
    if not metric_endpoint:
        return "Invalid metric selected."

    payload = {
        "reference": reference,
        "generated": generated
    }

    try:
        response = requests.post(metric_endpoint, json=payload, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            result = response.json()

            # Format the result as a readable string
            formatted = "\n".join([f"{key.capitalize()}: {value}" for key, value in result.items()])

            return formatted

    except Exception:
        logger.exception("Request to backend failed")
        return "Request failed. Please try again or contact support if this persists."



def create_ui():
    with gr.Blocks(title="Video-Accuracy Evaluation") as demo:
        gr.Markdown("# Video-Accuracy Evaluation Tool")
        gr.Markdown("Upload a .md file containing machine-generated and ground truth reference data for evaluation.")

        with gr.Tabs():
            with gr.TabItem("Summary Evaluation"):
                gr.Markdown(
                    "This tool evaluates factual consistency between a reference summary and a generated summary. "
                    "It compares sentences using similarity and Natural Language Inference (NLI), and provides detailed results and an overall summary."
                )
                gr.Markdown(SAMPLE_MARKDOWN)
                # Input file upload component
                file_input = gr.File(
                    label="Upload a .md file",
                    file_types=[".md"],
                    file_count="single"
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Reference")
                        reference_preview = gr.Markdown(
                            value="",
                            visible=False
                        )
                    with gr.Column(scale=1):
                        gr.Markdown("### Generated")
                        generated_preview = gr.Markdown(
                            value="",
                            visible=False
                        )

                submit_button = gr.Button("Submit")

                file_input.change(
                    fn=preview_uploaded_file,
                    inputs=[file_input],
                    outputs=[reference_preview, generated_preview]
                )

                # Output display component
                result_table = gr.Dataframe(
                    label="Sentence Comparisons",
                    interactive=False,
                    row_count=(0, "fixed")
                )

                # Factual consistency summary and temporal coherence summary as separate dataframes
                output_summary = gr.Dataframe(label="Factual Consistency Summary", interactive=False, row_count=(0, "fixed"))
                coherence_output_summary = gr.Dataframe(label="Temporal Coherence Summary", interactive=False, row_count=(0, "fixed"))

                # Set up button click event
                submit_button.click(
                    fn=submit_file,
                    inputs=[file_input],
                    outputs=[result_table, output_summary, coherence_output_summary]
                )

            with gr.TabItem("Metrics"):
                gr.Markdown("This section allow user to quickly understand what are the avaiable metrics provided.")

                with gr.Row():
                    with gr.Column(scale=1):
                        reference_input = gr.Textbox(label="Reference Text", lines=4, placeholder="Enter reference text here...")

                    with gr.Column(scale=2):
                        generated_input = gr.Textbox(label="Generated Text", lines=4, placeholder="Enter generated text here...")

                metric_selector = gr.Dropdown(
                    choices=["bert-score", "semantic-score", "rouge-score", "factual-consistency"],
                    label="Select evaluation metric",
                    info="Available Metrics Provided for Evaluation",
                    value="bert-score",
                    interactive=True
                )

                metric_desc = gr.Markdown("Select a metric to understand more.")

                metric_submit_button = gr.Button("Submit")

                metric_output = gr.Textbox(label="Metric Result", lines=10)

                # Set up dropdown click event
                metric_selector.select(
                    fn=show_metric_description,
                    inputs=metric_selector,
                    outputs=metric_desc
                )

                # Set up button click event
                metric_submit_button.click(
                    fn=evaluate_metrics,
                    inputs=[reference_input, generated_input, metric_selector],
                    outputs=[metric_output]
                )

    return demo

if __name__ == "__main__":
    demo = create_ui()
    logger.info(f"Starting Gradio UI...")
    demo.launch(
        # Bind address is configurable; defaults to all interfaces because the UI runs inside a
        # container published behind the NGINX gateway. Override APP_UI_HOST to restrict.
        server_name=os.getenv("APP_UI_HOST", "0.0.0.0"),  # nosec B104 - containerized service behind gateway
        server_port=int(os.getenv("APP_UI_PORT", "7860")),
        share=False,
        inbrowser=False,
        show_error=True
    )
