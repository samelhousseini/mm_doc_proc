import os
import sys
import logging
import openai
from openai import AzureOpenAI, OpenAI
import base64
import tiktoken
import requests
import json
from typing import List
from PIL import Image

from rich.console import Console
console = Console()

from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    stop_after_delay,
    after_log
)

from env_vars import *
from utils.text_utils import recover_json
from utils.data_models import MulitmodalProcessingModelInfo, TextProcessingModelnfo
from utils.file_utils import convert_png_to_jpg, get_image_base64

AZURE_OPENAI_API_VERSION = os.getenv('AZURE_OPENAI_API_VERSION')


azure_gpt_4o_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_4O'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_4O'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_4O'),
    "API_VERSION": AZURE_OPENAI_API_VERSION
}


azure_o1_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_O1'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_O1'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_O1'),
    "API_VERSION": AZURE_OPENAI_API_VERSION
}


azure_o1_mini_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_O1_MINI'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_O1_MINI'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_O1_MINI'),
    "API_VERSION": AZURE_OPENAI_API_VERSION
}

azure_embedding_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_EMBEDDING'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_EMBEDDING'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_EMBEDDING'),
    "DIMS": 3072 if os.getenv('AZURE_OPENAI_MODEL_EMBEDDING') == "text-embedding-3-large" else 1536
}


openai_gpt_4o_model_info = {
    "KEY": os.getenv('OPENAI_API_KEY'),
    "MODEL": os.getenv('OPENAI_MODEL_4O')
}

openai_o1_model_info = {
    "KEY": os.getenv('OPENAI_API_KEY'),
    "MODEL": os.getenv('OPENAI_MODEL_O1')
}

openai_o1_mini_model_info = {
    "KEY": os.getenv('OPENAI_API_KEY'),
    "MODEL": os.getenv('OPENAI_MODEL_O1_MINI')
}

openai_embedding_model_info = {
    "KEY": os.getenv('OPENAI_API_KEY'),
    "MODEL": os.getenv('OPENAI_MODEL_EMBEDDING'),
    "DIMS": 3072 if os.getenv('AZURE_OPENAI_MODEL_EMBEDDING') == "text-embedding-3-large" else 1536
}


def get_azure_endpoint(resource):
    return f"https://{resource}.openai.azure.com" if not "https://" in resource else resource


azure_oai_client_4o = AzureOpenAI(
    azure_endpoint = get_azure_endpoint(azure_gpt_4o_model_info["RESOURCE"]),
    api_key= azure_gpt_4o_model_info["KEY"],
    api_version= AZURE_OPENAI_API_VERSION,
)

azure_oai_client_o1 = AzureOpenAI(
    azure_endpoint = get_azure_endpoint(azure_o1_model_info["RESOURCE"]),
    api_key= azure_o1_model_info["KEY"],  
    api_version= AZURE_OPENAI_API_VERSION,
)

azure_oai_client_o1_mini = AzureOpenAI(
    azure_endpoint = get_azure_endpoint(azure_o1_mini_model_info["RESOURCE"]),
    api_key= azure_o1_mini_model_info["KEY"],
    api_version= AZURE_OPENAI_API_VERSION,
)


azure_embeding_client = AzureOpenAI(
    azure_endpoint = get_azure_endpoint(azure_embedding_model_info["RESOURCE"]),
    api_key= azure_embedding_model_info["KEY"],
    api_version= AZURE_OPENAI_API_VERSION,
)


openai_client = OpenAI(
    api_key = openai_gpt_4o_model_info["KEY"],
)



def get_encoder(model = "gpt-4o"):
    if model == "gpt-4o":
        return tiktoken.get_encoding("o200k_base")       
    if model == "o1":
        return tiktoken.get_encoding("o200k_base")       
    if model == "mini":
        return tiktoken.get_encoding("o200k_base")       
    else:
        return tiktoken.get_encoding("o200k_base")


def get_token_count(text, model = "gpt-4o"):
    enc = get_encoder(model)
    return len(enc.encode(text))


def prepare_image_messages(imgs):
    img_arr = imgs if isinstance(imgs, list) else [imgs]
    img_msgs = []

    for image_path_or_url in img_arr:
        image_path_or_url = os.path.abspath(image_path_or_url)
        try:
            if os.path.splitext(image_path_or_url)[1] == ".png":
                image_path_or_url = convert_png_to_jpg(image_path_or_url)
            image = f"data:image/jpeg;base64,{get_image_base64(image_path_or_url)}"
        except:
            image = image_path_or_url

        img_msgs.append({ 
            "type": "image_url",
            "image_url": {
                "url": image
            }
        })

    return img_msgs



def get_embeddings(text, model_info):
    if model_info.provider == "azure":
        client = azure_embeding_client
        model = azure_embedding_model_info["MODEL"]
    else:
        client = openai_client
        model = openai_embedding_model_info["MODEL"]

    return get_text_embeddings(text, client, model)


def get_text_embeddings(text, client = azure_embeding_client, embedding_model = openai_embedding_model_info["MODEL"]):
    return client.embeddings.create(input=[text], model=embedding_model).data[0].embedding



def call_llm(prompt_or_messages, model_info, temperature = 0.2):
    if isinstance(prompt_or_messages, str):
        messages = []
        messages.append({"role": "user", "content": "You are a helpful assistant, who helps the user with their query."})     
        messages.append({"role": "user", "content": prompt_or_messages})     
    else:
        messages = prompt_or_messages

    if model_info.provider == "azure":
        if model_info.model_name == "gpt-4o":
            client = azure_oai_client_4o
            model = azure_gpt_4o_model_info['MODEL']
            return call_4o(messages, client, model, temperature)
        elif model_info.model_name == "o1":
            client = azure_oai_client_o1
            model = azure_o1_model_info['MODEL']
            reasoning_effort = model_info.reasoning_efforts
            return call_o1(messages, client, model, reasoning_effort)
        elif model_info.model_name == "o1-mini":
            client = azure_oai_client_o1_mini
            model = azure_o1_mini_model_info['MODEL']
            return call_o1_mini(messages, client, model)
        else:
            client = azure_oai_client_4o
            model = azure_gpt_4o_model_info['MODEL']
            return call_4o(messages, client, model, temperature)
    else:
        if model_info.model_name == "gpt-4o":
            client = openai_client
            model = openai_gpt_4o_model_info['MODEL']
            return call_4o(messages, client, model, temperature)
        elif model_info.model_name == "o1":
            client = openai_client
            model = openai_o1_model_info['MODEL']
            return call_o1(messages, client, model)
        elif model_info.model_name == "o1-mini":
            client = openai_client
            model = openai_o1_mini_model_info['MODEL']
            return call_o1_mini(messages, client, model)
        else:
            client = openai_client
            model = openai_gpt_4o_model_info['MODEL']
            return call_4o(messages, client, model, temperature)



def call_4o(messages, client, model, temperature = 0.2):
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    result = client.chat.completions.create(model = model, temperature = temperature, messages = messages)
    return result.choices[0].message.content
      

def call_o1(messages,  client, model, reasoning_effort ="medium"): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")

    response = client.chat.completions.create(
        model=model, 
        messages=messages,
        reasoning_effort=reasoning_effort,
    )

    return response.model_dump()['choices'][0]['message']['content']


def call_o1_mini(messages,  client, model): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")

    response = client.chat.completions.create(
        model=model, 
        messages=messages
    )

    return response.model_dump()['choices'][0]['message']['content']
       




def call_llm_structured_outputs(imgs, prompt, model_info, response_format):
    content = [{"type": "text", "text": prompt}]
    content = content + prepare_image_messages(imgs)
    messages = [
        {"role": "user", "content": "You are a helpful assistant that processes images to generate structured outputs."},
        {"role": "user", "content": content},
    ]

    if model_info.provider == "azure":
        if model_info.model_name == "gpt-4o":
            client = azure_oai_client_4o
            model = azure_gpt_4o_model_info['MODEL']
            return call_llm_structured_4o(messages, client, model, response_format)
        elif model_info.model_name == "o1":
            client = azure_oai_client_o1
            model = azure_o1_model_info['MODEL']
            return call_llm_structured_o1(messages, client, model, response_format, model_info.reasoning_efforts)
        elif model_info.model_name == "o1-mini":
            client = azure_oai_client_o1_mini
            model = azure_o1_mini_model_info['MODEL']
            return call_llm_structured_o1_mini(messages, client, model, response_format)
        else:
            client = azure_oai_client_4o
            model = azure_gpt_4o_model_info['MODEL']
            return call_llm_structured_4o(messages, client, model, response_format)
    else:
        if model_info.model_name == "gpt-4o":
            client = openai_client
            model = openai_gpt_4o_model_info['MODEL']
            return call_llm_structured_4o(messages, client, model, response_format)
        elif model_info.model_name == "o1":
            client = openai_client
            model = openai_o1_model_info['MODEL']
            return call_llm_structured_o1(messages, client, model, response_format, model_info.reasoning_efforts)
        elif model_info.model_name == "o1-mini":
            client = openai_client
            model = openai_o1_mini_model_info['MODEL']
            return call_llm_structured_o1_mini(messages, client, model, response_format)
        else:
            client = openai_client
            model = openai_gpt_4o_model_info['MODEL']
            return call_llm_structured_4o(messages, client, model, response_format)


def call_llm_structured_4o(messages, client, model, response_format):
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=response_format,
    )
    return completion.choices[0].message.parsed


def call_llm_structured_o1(messages, client, model, response_format, reasoning_effort ="medium"): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    response = client.beta.chat.completions.parse(
        model=model, 
        messages=messages,
        reasoning_effort=reasoning_effort,
        response_format=response_format
    )
    return response.choices[0].message.parsed

 
def call_llm_structured_o1_mini(messages, client, model, response_format): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    response = client.beta.chat.completions.parse(
        model=model, 
        messages=messages,
        response_format=response_format
    )
    return response.choices[0].message.parsed

