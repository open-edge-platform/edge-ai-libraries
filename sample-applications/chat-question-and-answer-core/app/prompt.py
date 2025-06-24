
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