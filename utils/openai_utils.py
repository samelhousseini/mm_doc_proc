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

from utils.text_utils import recover_json
from multimodal_processing_pipeline.data_models import *
from utils.openai_data_models import *
from utils.file_utils import convert_png_to_jpg, get_image_base64



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



def get_embeddings(text : str, model_info: EmbeddingModelnfo = EmbeddingModelnfo()):
    if model_info.client is None: model_info = instantiate_model(model_info)
    return model_info.client.embeddings.create(input=[text], model=model_info.model_name).data[0].embedding



def call_llm(prompt: str, model_info: Union[MulitmodalProcessingModelInfo, TextProcessingModelnfo], temperature = 0.2, imgs=[]):
    content = [{"type": "text", "text": prompt}]
    content = content + prepare_image_messages(imgs)
    messages = [
        {"role": "user", "content": "You are a helpful assistant that processes text and images."},
        {"role": "user", "content": content},
    ]

    if model_info.client is None: model_info = instantiate_model(model_info)

    if model_info.model_name == "gpt-4o":
        return call_4o(messages, model_info.client, model_info.model, temperature)
    elif model_info.model_name == "o1":
        return call_o1(messages, model_info.client, model_info.model, model_info.reasoning_efforts)
    elif model_info.model_name == "o1-mini":
        return call_o1_mini(messages, model_info.client, model_info.model)
    else:
        return call_4o(messages, model_info.client, model_info.model, temperature)



def call_4o(messages, client, model, temperature = 0.2):
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    result = client.chat.completions.create(model = model, temperature = temperature, messages = messages)
    return result.choices[0].message.content
      

def call_o1(messages,  client, model, reasoning_effort ="medium"): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    response = client.chat.completions.create(model=model, messages=messages, reasoning_effort=reasoning_effort)
    return response.model_dump()['choices'][0]['message']['content']


def call_o1_mini(messages,  client, model): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    response = client.chat.completions.create(model=model, messages=messages)
    return response.model_dump()['choices'][0]['message']['content']
       


def call_llm_structured_outputs(prompt: str, model_info: Union[MulitmodalProcessingModelInfo, TextProcessingModelnfo], response_format, imgs=[]):
    content = [{"type": "text", "text": prompt}]
    content = content + prepare_image_messages(imgs)
    messages = [
        {"role": "user", "content": "You are a helpful assistant that processes text and images to generate structured outputs."},
        {"role": "user", "content": content},
    ]

    if model_info.client is None: model_info = instantiate_model(model_info)

    if model_info.model_name == "gpt-4o":
        return call_llm_structured_4o(messages, model_info.client, model_info.model, response_format)
    elif model_info.model_name == "o1":
        return call_llm_structured_o1(messages, model_info.client, model_info.model, response_format, model_info.reasoning_efforts)
    elif model_info.model_name == "o1-mini":
        return call_llm_structured_o1_mini(messages, model_info.client, model_info.model, response_format)
    else:
        return call_llm_structured_4o(messages, model_info.client, model_info.model, response_format)



def call_llm_structured_4o(messages, client, model, response_format):
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    completion = client.beta.chat.completions.parse(model=model, messages=messages, response_format=response_format)
    return completion.choices[0].message.parsed


def call_llm_structured_o1(messages, client, model, response_format, reasoning_effort ="medium"): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    response = client.beta.chat.completions.parse(model=model, messages=messages, reasoning_effort=reasoning_effort, response_format=response_format)
    return response.choices[0].message.parsed

 
def call_llm_structured_o1_mini(messages, client, model, response_format): 
    # print(f"\nCalling OpenAI APIs with {len(messages)} messages - Model: {model} - Endpoint: {client._base_url}\n")
    response = client.beta.chat.completions.parse(model=model, messages=messages, response_format=response_format)
    return response.choices[0].message.parsed

