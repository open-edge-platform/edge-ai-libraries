# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import logging
import traceback
import tempfile
import requests
import gradio as gr
from app.config import Settings

config = Settings()

# Add the parent directory to the Python path to allow importing from parent modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get API URL from environment variable or default to localhost
API_URL = config.API_URL

def summarize_document(file_obj, custom_query=None):
    """
    Function to summarize a document by sending it to the FastAPI backend.
    
    Args:
        file_obj: The uploaded file object from Gradio
        custom_query (str, optional): Custom query for summarization. Defaults to None.
        
    Returns:
        str: The summary of the document
    """
    if file_obj is None:
        return f"Error: Please upload a file of type: {', '.join(config.SUPPORTED_FILE_EXTENSIONS)}."
        
    logger.info(f"Received file: {getattr(file_obj, 'name', 'unknown')}")
    
    # Check file extension
    file_extension = os.path.splitext(file_obj.name)[1].lower()
    if file_extension not in config.SUPPORTED_FILE_EXTENSIONS:
        return f"Error: Only {', '.join(config.SUPPORTED_FILE_EXTENSIONS)} files are allowed."
    
    # Define the API endpoint
    docsum_endpoint = f"{API_URL}/summarize/"
    
    # Prepare the query
    query = custom_query if custom_query and custom_query.strip() else "Summarize the document"
    
    try:
        
        if file_extension not in config.MIME_TYPES:
            raise Exception("Unsupported file type")
        mime_type = config.MIME_TYPES[file_extension]
        # Prepare the files and data for the request
        files = {"file": (os.path.basename(file_obj.name), open(file_obj.name, "rb"), mime_type)}
        data = {"query": query}
        
        logger.info(f"Sending request to {docsum_endpoint} with query: {query}")
        
        # Send the request to the API
        response = requests.post(docsum_endpoint, files=files, data=data)
        
        # Check if the request was successful
        if response.status_code == 200:
            logger.info("Successfully received summary from API")
            return response.text
        else:
            logger.error(f"Error from API: Status code {response.status_code}")
            error_message = response.json().get("message", "Unknown error")
            return f"Error: {error_message}"
            
    except Exception as e:
        logger.error(f"Error sending request to API: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Error: {str(e)}"

def create_ui():
    """Create and return the Gradio interface"""
    with gr.Blocks(title="Document Summarizer") as demo:
        gr.Markdown(f"# Document Summarization Tool")
        gr.Markdown(f"Upload a {', '.join(config.SUPPORTED_FILE_TYPES)} and get a summary using advanced AI models.")
        
        with gr.Row():
            with gr.Column(scale=1):
                # Input components
                file_input = gr.File(
                    label="Upload Document",
                    file_types=list(config.SUPPORTED_FILE_EXTENSIONS),
                    file_count="single"
                )
                submit_btn = gr.Button("Generate Summary", variant="primary")
                
            with gr.Column(scale=2):
                # Output component
                output = gr.Textbox(
                    label="Generated Summary",
                    lines=15,
                    max_lines=30,
                    show_copy_button=True
                )
                
        # Set up the event handler
        submit_btn.click(
            fn=summarize_document,
            inputs=[file_input],
            outputs=output
        )
        
        gr.Markdown("### Notes")
        gr.Markdown(f"- Only {', '.join(config.SUPPORTED_FILE_TYPES)} files are supported")
        gr.Markdown("- For large documents, summarization may take some time")
        gr.Markdown("- This tool uses LLM models to generate summaries")
    
    return demo

if __name__ == "__main__":
    # Get port and host from environment or use defaults
    port = int(config.GRADIO_PORT)
    # For containers, we need to bind to all interfaces so nginx can reach us
    host = "0.0.0.0"
    
    # Create and launch the UI
    demo = create_ui()
    logger.info(f"Starting Gradio UI on {host}:{port}")
    demo.launch(
        server_name=host,
        server_port=port,
        share=False,
        inbrowser=False,
        show_error=True
    )
