import os

from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchFieldDataType,
    VectorSearch,
    SemanticSearch,
    VectorSearchAlgorithmConfiguration,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SimpleField,
    SearchFieldDataType,
    SearchableField
)


import sys
sys.path.append("../")

from utils.openai_utils import *
from utils.openai_data_models import EmbeddingModelnfo




def build_configurations(embedding_model_info):
    if embedding_model_info.client is None: 
        embedding_model_info = instantiate_model(embedding_model_info)

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="myHnsw"
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="myHnswProfile",
                algorithm_configuration_name="myHnsw",
                vectorizer_name="myVectorizer"
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="myVectorizer",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=embedding_model_info.endpoint,
                    deployment_name=embedding_model_info.model,
                    model_name=embedding_model_info.model,
                    api_key=embedding_model_info.key,
                )
            )
        ]
    )

    semantic_config = SemanticConfiguration(
        name="my-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="text"),
            content_fields=[
                SemanticField(field_name="text"),
            ],
            keywords_fields=[]
        )
    )
    semantic_search = SemanticSearch(configurations=[semantic_config])

    return vector_search, semantic_search
