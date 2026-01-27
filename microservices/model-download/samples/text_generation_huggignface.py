from transformers import pipeline

#text generation
generator = pipeline('text-generation', model='../tmp/models/all_folder/huggingface/Qwen_Qwen2.5-7B-Instruct')
results = generator("Hello, I'm a language model")
for i, result in enumerate(results):
    print(f"Result {i+1}: {result['generated_text']}")

#text-2-text generation
text2text_generator = pipeline('text2text-generation', model='../tmp/models/hf_folder/huggingface/Intel_neural-chat-7b-v3-3')
results = text2text_generator("question: What is 42 ? context: 42 is the answer to life, the universe and everything")
for i, result in enumerate(results):
    print(f"Result {i+1}: {result['generated_text']}")

