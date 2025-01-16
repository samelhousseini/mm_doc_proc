import os
import json
import datetime
import uuid
import pandas as pd
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Type,
    Union,
)
from pydantic import BaseModel

# Azure Cognitive Search imports
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
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
from azure.search.documents import SearchIndexingBufferedSender
from azure.search.documents.models import (
    VectorizableTextQuery,
    QueryType
)


import sys
sys.path.append("../")

from utils.openai_utils import *
from utils.data_models import EmbeddingModelnfo


###############################################################################
# DYNAMIC INDEX BUILDER
###############################################################################
def is_pydantic_model(type_hint: Any) -> bool:
    """
    Check if a given type hint is a subclass of pydantic.BaseModel.
    """
    return isinstance(type_hint, type) and issubclass(type_hint, BaseModel)

def map_primitive_to_search_data_type(type_hint: Any) -> SearchFieldDataType:
    """
    Map Python primitive/standard types to Azure Cognitive Search data types.
    Extend or adjust as needed for your application.
    """
    from typing import get_origin, get_args
    import datetime

    if type_hint == str:
        return SearchFieldDataType.String
    if type_hint == int:
        return SearchFieldDataType.Int64  # or Int32
    if type_hint == float:
        return SearchFieldDataType.Double
    if type_hint == bool:
        return SearchFieldDataType.Boolean
    if type_hint in (datetime.date, datetime.datetime):
        return SearchFieldDataType.DateTimeOffset
    # Fallback
    return SearchFieldDataType.String



def build_search_fields_for_model(
    model: Type[BaseModel],
    key_field_name: Optional[str] = None,
    is_in_collection: bool = False,
    embedding_dimensions: int = 1536,
    vector_profile_name: str = "myHnswProfile"
):
    """
    Recursively build a hierarchical Azure Cognitive Search schema from a Pydantic model.

    - Nested models -> ComplexField with subfields
    - List of nested models -> ComplexField(collection=True)
    - List of primitives -> either SimpleField or SearchableField(collection=True)
    - List of float -> interpret as a Vector field (SearchField with vector config)
    - If 'key_field_name' matches the field, we mark it as the key (top-level only).
    - If 'is_in_collection' is True, we disable sorting to avoid multi-valued sorting errors.
    - We also disable sorting on vector fields.
    """
    from azure.search.documents.indexes.models import (
        ComplexField,
        SimpleField,
        SearchableField,
        SearchField,
        SearchFieldDataType
    )
    from typing import get_origin, get_args, Union
    import datetime

    def is_vector_field(outer_type: Any) -> bool:
        """
        Return True if the type is List[float] or Optional[List[float]] or similar.
        """
        # For example, if outer_type is List[float], or Union[List[float], None], etc.
        if get_origin(outer_type) in (list, List):
            (inner_type,) = get_args(outer_type)
            return inner_type == float
        if get_origin(outer_type) is Union:
            union_args = get_args(outer_type)
            # e.g. Union[List[float], None]
            # We'll check if there's exactly 1 non-None arg which is List[float].
            non_none_args = [arg for arg in union_args if arg is not type(None)]
            if len(non_none_args) == 1 and get_origin(non_none_args[0]) in (list, List):
                (inner_type,) = get_args(non_none_args[0])
                return inner_type == float
        return False

    fields = []

    for field_name, model_field in model.__fields__.items():
        use_as_key = (field_name == key_field_name)
        outer_type = model_field.annotation  # For Pydantic 2.x

        # 1) Check if it's a vector field (list of floats)
        if is_vector_field(outer_type):
            # This field is a vector. We'll define a SearchField with vector properties.
            fields.append(
                SearchField(
                    name=field_name,
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,   # vector fields must be 'searchable=True'
                    filterable=False,
                    facetable=False,
                    sortable=False,    # no sorting on a vector
                    key=use_as_key,
                    vector_search_dimensions=embedding_dimensions,
                    vector_search_profile_name=vector_profile_name
                )
            )
            continue

        # 2) Otherwise, check if it's a generic list
        origin = get_origin(outer_type)
        if origin in (list, List):
            (inner_type,) = get_args(outer_type)

            # If the inner type is another Pydantic model => Complex collection
            if is_pydantic_model(inner_type):
                subfields = build_search_fields_for_model(
                    inner_type,
                    key_field_name=None,
                    is_in_collection=True,
                    embedding_dimensions=embedding_dimensions,
                    vector_profile_name=vector_profile_name
                )
                fields.append(
                    ComplexField(
                        name=field_name,
                        fields=subfields,
                        collection=True
                    )
                )
            else:
                # It's a list of primitives
                data_type = map_primitive_to_search_data_type(inner_type)
                if data_type == SearchFieldDataType.String:
                    fields.append(
                        SearchableField(
                            name=field_name,
                            type=data_type,
                            collection=True,
                            searchable=True,
                            filterable=True,
                            facetable=False,
                            sortable=False,  # multi-valued => no sorting
                            key=use_as_key
                        )
                    )
                else:
                    fields.append(
                        SimpleField(
                            name=field_name,
                            type=data_type,
                            collection=True,
                            filterable=True,
                            facetable=True,
                            sortable=False,  # multi-valued => no sorting
                            key=use_as_key
                        )
                    )
            continue

        # 3) If it's a nested Pydantic model (single object)
        if is_pydantic_model(outer_type):
            subfields = build_search_fields_for_model(
                outer_type,
                key_field_name=None,
                is_in_collection=is_in_collection,
                embedding_dimensions=embedding_dimensions,
                vector_profile_name=vector_profile_name
            )
            fields.append(
                ComplexField(
                    name=field_name,
                    fields=subfields,
                    collection=False
                )
            )
            continue

        # 4) Otherwise, possibly a primitive or optional
        if get_origin(outer_type) is Union:
            union_args = get_args(outer_type)
            non_none_args = [arg for arg in union_args if arg is not type(None)]
            chosen_type = non_none_args[0] if non_none_args else str
        else:
            chosen_type = outer_type

        data_type = map_primitive_to_search_data_type(chosen_type)

        if data_type == SearchFieldDataType.String:
            fields.append(
                SearchableField(
                    name=field_name,
                    type=data_type,
                    searchable=True,
                    filterable=True,
                    facetable=False,
                    sortable=(False if is_in_collection else True),
                    key=use_as_key
                )
            )
        else:
            fields.append(
                SimpleField(
                    name=field_name,
                    type=data_type,
                    filterable=True,
                    facetable=True,
                    sortable=(False if is_in_collection else True),
                    key=use_as_key
                )
            )

    return fields



def build_configurations():
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
                # The name must match the profile above
                vectorizer_name="myVectorizer",
                # Provide your Azure OpenAI settings (model, key, etc.) here:
                parameters=AzureOpenAIVectorizerParameters(
                    # Example placeholders. Replace with your real config:
                    resource_url=get_azure_endpoint(azure_embedding_model_info["RESOURCE"]),
                    deployment_name=azure_embedding_model_info["MODEL"],
                    model_name=azure_embedding_model_info["MODEL"],
                    api_key=azure_embedding_model_info["KEY"],
                )
            )
        ]
    )

    semantic_config = SemanticConfiguration(
        name="my-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="condensed_text"),
            content_fields=[
                SemanticField(field_name="condensed_text"),
            ],
            keywords_fields=[]
        )
    )
    semantic_search = SemanticSearch(configurations=[semantic_config])

    return vector_search, semantic_search




class DynamicAzureIndexBuilder:
    """
    A dynamic builder that can:
      1) Build & create/update an Azure Cognitive Search index from Pydantic models.
      2) Upload model instances (with optional embeddings) in bulk.
      3) Delete model instances from the index by their ID(s).
      4) Perform a hybrid search (keyword + vector).

    Use 'get_embeddings()' for generating vectors from your text fields,
    then store them in the index for vector/hybrid search.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        index_name: str,
        embedding_model_info: EmbeddingModelnfo = EmbeddingModelnfo()
    ):
        """
        :param endpoint: Your Azure Cognitive Search endpoint (e.g. https://<NAME>.search.windows.net)
        :param api_key: The Admin key for the search service
        :param index_name: The name of your index (must be lowercase in Azure Search)
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.index_name = index_name.lower()

        self.key_field_name = None

        # Clients
        self.index_client = SearchIndexClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key)
        )
        self.search_client = SearchClient(
            endpoint=endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(api_key)
        )

    def build_index(
        self,
        model: Type[BaseModel],
        key_field_name: Optional[str] = None
    ) -> SearchIndex:
        """
        Build a SearchIndex object from the given Pydantic model, optionally 
        including vector search and semantic search configurations.

        :param model: Pydantic model class describing your data schema
        :param key_field_name: 
            - If the model has a field with this name, mark that field as key=True
            - If not, create a new string field with that name as the key
            - If None, use "index_id" as a new key field
        :param vector_search: Optional VectorSearch configuration (Hnsw, etc.)
        :param semantic_search: Optional SemanticSearch configuration
        """
        
        vector_search, semantic_search = build_configurations()

        # Decide final key field
        if not key_field_name:
            final_key_field = "index_id"
            create_new_key = True
        else:
            if key_field_name in model.__fields__:
                final_key_field = key_field_name
                create_new_key = False
            else:
                final_key_field = key_field_name
                create_new_key = True

        self.key_field_name = final_key_field

        # Build fields from the model
        built_fields = build_search_fields_for_model(
            model,
            key_field_name=(final_key_field if not create_new_key else None),
            is_in_collection=False,
            embedding_dimensions=azure_embedding_model_info["DIMS"],
            vector_profile_name=vector_search.profiles[0].name
        )

        # If we need to create a brand-new key field
        extra_fields = []
        if create_new_key:
            extra_fields.append(
                SimpleField(
                    name=final_key_field,
                    type=SearchFieldDataType.String,
                    key=True,
                    filterable=False,
                    facetable=False,
                    sortable=False
                )
            )

        all_fields = extra_fields + built_fields

        # Construct the SearchIndex
        index_def = SearchIndex(
            name=self.index_name,
            fields=all_fields,
            vector_search=vector_search,
            semantic_search=semantic_search
        )
        return index_def

    def create_or_update_index(
        self,
        model: Type[BaseModel],
        key_field_name: Optional[str] = None
    ) -> SearchIndex:
        """
        High-level method to build and commit a new or updated index definition 
        to the Azure Search service.

        :param model: Pydantic model class.
        :param key_field_name: See docstring for build_index().
        :param vector_search: Optional VectorSearch configuration.
        :param semantic_search: Optional SemanticSearch configuration.
        :return: The created/updated SearchIndex object.
        """
        index_def = self.build_index(model, key_field_name)
        result = self.index_client.create_or_update_index(index=index_def)
        print(f"Index '{result.name}' created/updated successfully.")
        return result

    ###########################################################################
    # 1) UPLOAD MODEL INSTANCES WITH EMBEDDINGS
    ###########################################################################
    def upload_documents(
        self,
        model_objects: List[BaseModel],
        embedding_fields: Optional[dict] = None,
        embedding_model_info: EmbeddingModelnfo = EmbeddingModelnfo(), 
    ) -> None:
        """
        Takes a list of Pydantic model instances, optionally generates embeddings 
        for specified text fields, and uploads them to the index in bulk.

        :param model_objects: List of your Pydantic model instances
        :param embedding_fields: List of field names (strings) you want to embed
                                 e.g. ["title", "content"]
        :param embedding_model_info: Model name for get_embeddings()
        """
        if embedding_fields is None:
            embedding_fields = []

        # Convert each model to dict, optionally injecting vector embeddings
        documents_to_upload = []
        for obj in model_objects:
            doc = obj.dict()

            # For each field in embedding_fields, generate vector => store in e.g. "titleVector"
            for field_name in embedding_fields:
                if field_name in doc and isinstance(doc[field_name], str):
                    # generate embedding
                    vector = get_embeddings(doc[field_name], embedding_model_info)
                    # store as e.g. "titleVector"
                    vector_field_name = embedding_fields[field_name]
                    doc[vector_field_name] = vector
            
            documents_to_upload.append(doc)

        if self.key_field_name is not None:
            # Ensure the key field is present in each document
            for doc in documents_to_upload:
                if self.key_field_name not in doc:
                    doc[self.key_field_name] = str(uuid.uuid4())   # generate a new ID

        search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key),
        )
        result = search_client.upload_documents(documents_to_upload)
        print(f"Uploaded {len(documents_to_upload)} documents\nResult: {result}") 

    ###########################################################################
    # 2) DELETE MODEL INSTANCES
    ###########################################################################
    def delete_documents(self, doc_ids: List[str], key_field_name: str = "index_id") -> None:
        """
        Delete documents from the index by their ID values. The ID field must 
        match the index's key field or be mapped to it in your logic.

        :param doc_ids: The list of document IDs to delete
        :param key_field_name: The name of the key field in the index
        """
        # Prepare a set of delete actions
        delete_actions = []
        for doc_id in doc_ids:
            delete_actions.append({
                key_field_name: doc_id,
                "@search.action": "delete"
            })

        # Use buffered sender for batch deletion
        with SearchIndexingBufferedSender(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key),
        ) as batch_client:
            batch_client.upload_documents(documents=delete_actions)
        print(f"Deleted {len(doc_ids)} documents from '{self.index_name}'.")

    ###########################################################################
    # 3) HYBRID SEARCH (KEYWORD + VECTOR)
    ###########################################################################
    def hybrid_search(
        self,
        query: str,
        vector_field: str,
        top: int = 3
    ) -> pd.DataFrame:
        """
        Perform a hybrid search, combining a keyword-based search with a 
        vector-based retrieval (RRF re-ranking).

        :param query: The user query string
        :param vector_field: The name of the vector field (e.g. "contentVector")
        :param top: Number of results to return
        :return: A pandas DataFrame with columns ["id", ... , "@search.score"]
        """
        from azure.search.documents.models import VectorizableTextQuery

        results = self.search_client.search(
            search_text=query,  # the keyword part
            vector_queries=[
                VectorizableTextQuery(
                    text=query, 
                    k_nearest_neighbors=50,  # large recall set for better re-ranking
                    fields=vector_field
                )
            ],
            top=top,
            semantic_configuration_name="my-semantic-config",
            query_type=QueryType.SEMANTIC,
        )

        return results

        # Collect results
        rows = []
        for res in results:
            # We assume "id" is your actual key field or at least a unique ID
            # Adjust the field names (res["title"], res["content"], etc.) as appropriate
            row = {
                "id": res.get("id", None),
                "@search.score": res["@search.score"]
            }
            # If you know your documents contain 'title' or 'content', you can add:
            if "title" in res:
                row["title"] = res["title"]
            if "content" in res:
                row["content"] = res["content"]
            rows.append(row)

        df = pd.DataFrame(rows)
        return df
