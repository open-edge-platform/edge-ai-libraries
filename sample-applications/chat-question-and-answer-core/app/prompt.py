# Defaul prompt template for RAG (Retrieval-Augmented Generation)
default_rag_prompt_template = """
    Use the following pieces of context from retrieved
    dataset to answer the question. Do not make up an answer if there is no
    context provided to help answer it.

    Context:
    ---------
    {context}

    ---------
    Question: {question}
    ---------

    Answer:
    """

# Define the prompt templates for validated model IDs
model_prompt_templates = {
    "microsoft/Phi-3.5-mini-instruct": """
    <|system|>
    Use the following pieces of context from retrieved
    dataset to answer the question. Do not make up an answer if there is no
    context provided to help answer it.<|end|>

    <|context|>
    Context:
    ---------
    {context}
    <|end|>

    <|user|>
    ---------
    Question: {question}
    ---------
    <|end|>

    <|assistant|>
    Answer:
    """,
    "Intel/neural-chat-7b-v3-3": """
    ### System:
    Use the following pieces of context from retrieved
    dataset to answer the question. Do not make up an answer if there is no
    context provided to help answer it.

    ### Context:
    {context}

    ### User:
    {question}

    ### Assistant:
    """,
    "meta-llama/Llama-3.1-8B-Instruct":
    """
    <|start_header_id|>system<|end_header_id|>
    Use the following pieces of context from retrieved
    dataset to answer the question. Do not make up an answer if there is no
    context provided to help answer it.

    <context>
    Context:
    {context}
    </context>

    <|start_header_id|>user<|end_header_id|>
    Question: {question}
    <|eot_id|>

    <|start_header_id|>assistant<|end_header_id|>
    """,
    "Qwen/Qwen2.5-7B-Instruct": """
    <|im_start|>
    system:
    Use the following pieces of context from retrieved
    dataset to answer the question. Do not make up an answer if there is no
    context provided to help answer it.

    context:
    {context}
    <|im_end|>

    <|im_start|>
    user:
    {question}
    <|im_end|>

    <|im_start|>assistant
    """
}

def get_prompt_template(llm_model_id: str) -> str:
    """
    Get the prompt template for a given model ID.

    Args:
        model_id (str): The model ID to get the prompt template for.

    Returns:
        str: The prompt template for the specified model ID.
    """

    # If the model ID is not in the predefined templates, return the default RAG prompt template
    return model_prompt_templates.get(llm_model_id, default_rag_prompt_template)
