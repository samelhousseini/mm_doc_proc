import os
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Type, Union
from pathlib import Path
from openai import AzureOpenAI, OpenAI
from dotenv import load_dotenv
load_dotenv()


from rich.console import Console
console = Console()

AZURE_OPENAI_API_VERSION = os.getenv('AZURE_OPENAI_API_VERSION')


def get_azure_endpoint(resource):
    return f"https://{resource}.openai.azure.com" if not "https://" in resource else resource



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

azure_ada_embedding_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_EMBEDDING_ADA'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_EMBEDDING_ADA'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_EMBEDDING_ADA'),
    "DIMS": 1536
}

azure_small_embedding_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_EMBEDDING_SMALL'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_EMBEDDING_SMALL'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_EMBEDDING_SMALL'),
    "DIMS": 1536
}

azure_large_embedding_model_info = {
    "RESOURCE": os.getenv('AZURE_OPENAI_RESOURCE_EMBEDDING_LARGE'),
    "KEY": os.getenv('AZURE_OPENAI_KEY_EMBEDDING_LARGE'),
    "MODEL": os.getenv('AZURE_OPENAI_MODEL_EMBEDDING_LARGE'),
    "DIMS": 3072
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



class MulitmodalProcessingModelInfo(BaseModel):
    """
    Information about the multimodal model name.
    """
    provider: Literal["azure", "openai"] = "azure"
    model_name: Literal["gpt-4o", "o1"] = "gpt-4o"
    reasoning_efforts: Optional[Literal["low", "medium", "high"]] = "medium"    
    endpoint: str = ""
    key: str = ""
    model: str = ""
    api_version: str = "2024-12-01-preview"
    client: Union[AzureOpenAI, OpenAI] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TextProcessingModelnfo(BaseModel):
    """
    Information about the multimodal model name.
    """
    provider: Literal["azure", "openai"] = "azure"
    model_name: Literal["gpt-4o", "o1", "o1-mini"] = "gpt-4o"
    reasoning_efforts: Optional[Literal["low", "medium", "high"]] = "medium"    
    endpoint: str = ""
    key: str = ""
    model: str = ""
    api_version: str = "2024-12-01-preview"
    client: Union[AzureOpenAI, OpenAI] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EmbeddingModelnfo(BaseModel):
    """
    Information about the multimodal model name.
    """
    provider: Literal["azure"] = "azure"
    model_name: Literal["text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large"] = "text-embedding-3-small"
    dimensions: Literal[1536, 3072] = 1536
    endpoint: str = ""
    key: str = ""
    model: str = ""
    api_version: str = "2024-12-01-preview"
    client: Union[AzureOpenAI, OpenAI] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)




def instantiate_model(model_info: Union[MulitmodalProcessingModelInfo, 
                                   TextProcessingModelnfo, 
                                   EmbeddingModelnfo]):
     
    if model_info.model_name == "gpt-4o":
        model_info.endpoint = get_azure_endpoint(azure_gpt_4o_model_info["RESOURCE"])
        model_info.key = azure_gpt_4o_model_info["KEY"]
        model_info.model = azure_gpt_4o_model_info["MODEL"]
        model_info.api_version = AZURE_OPENAI_API_VERSION

    elif model_info.model_name == "o1":
        model_info.endpoint = get_azure_endpoint(azure_o1_model_info["RESOURCE"])
        model_info.key = azure_o1_model_info["KEY"]
        model_info.model = azure_o1_model_info["MODEL"]
        model_info.api_version = AZURE_OPENAI_API_VERSION

    elif model_info.model_name == "o1-mini":
        model_info.endpoint = get_azure_endpoint(azure_o1_mini_model_info["RESOURCE"])
        model_info.key = azure_o1_mini_model_info["KEY"]
        model_info.model = azure_o1_mini_model_info["MODEL"]
        model_info.api_version = AZURE_OPENAI_API_VERSION

    elif model_info.model_name == "text-embedding-ada-002":
        model_info.endpoint = get_azure_endpoint(azure_ada_embedding_model_info["RESOURCE"])
        model_info.key = azure_ada_embedding_model_info["KEY"]
        model_info.model = azure_ada_embedding_model_info["MODEL"]
        model_info.api_version = AZURE_OPENAI_API_VERSION

    elif model_info.model_name == "text-embedding-3-small":
        model_info.endpoint = get_azure_endpoint(azure_small_embedding_model_info["RESOURCE"])
        model_info.key = azure_small_embedding_model_info["KEY"]
        model_info.model = azure_small_embedding_model_info["MODEL"]
        model_info.api_version = AZURE_OPENAI_API_VERSION

    elif model_info.model_name == "text-embedding-3-large":
        model_info.endpoint = get_azure_endpoint(azure_large_embedding_model_info["RESOURCE"])
        model_info.key = azure_large_embedding_model_info["KEY"]
        model_info.model = azure_large_embedding_model_info["MODEL"]
        model_info.api_version = AZURE_OPENAI_API_VERSION

    if model_info.provider == "azure":
        model_info.client = AzureOpenAI(azure_endpoint=model_info.endpoint, 
                                        api_key=model_info.key, 
                                        api_version=model_info.api_version)
    else:
        model_info.client = OpenAI(api_key=model_info.key)


    # console.print("Requested", model_info)
    
    return model_info
