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

from typing import get_origin, get_args, Union
import datetime

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
    SearchField,
    SearchableField,
    ComplexField
)
from azure.search.documents import SearchIndexingBufferedSender
from azure.search.documents.models import (
    VectorizableTextQuery,
    QueryType
)


import sys
sys.path.append("../")

from utils.openai_utils import *
from multimodal_processing_pipeline.data_models import *
from multimodal_processing_pipeline.pdf_ingestion_pipeline import *
from search_data_models import *
from search_helpers import *

from multiprocessing.dummy import Pool as ThreadPool
pool = ThreadPool(25)



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
        embedding_model_info: EmbeddingModelnfo,
        vector_profile_name: str = "myHnswProfile"
    ):
        """
        :param endpoint: Your Azure Cognitive Search endpoint (e.g. https://<NAME>.search.windows.net)
        :param api_key: The Admin key for the search service
        :param index_name: The name of your index (must be lowercase in Azure Search)
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.index_name = index_name.lower()
        self.embedding_model_info = embedding_model_info
        self.vector_profile_name = vector_profile_name
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

        self.search_clients = [SearchClient(
            endpoint=endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(api_key)
        ) for _ in range(25)]

    def build_index(
        self,
        model: Type[BaseModel],
        key_field_name: Optional[str] = None,
        vector_search: Optional[VectorSearch] = None,
        semantic_search: Optional[SemanticSearch] = None,
        vector_profile_index: Optional[int] = 0
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
            embedding_dimensions=self.embedding_model_info.dimensions,
            vector_profile_name=self.vector_profile_name
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
        key_field_name: Optional[str] = None,
        vector_search: Optional[VectorSearch] = None,
        semantic_search: Optional[SemanticSearch] = None,
        vector_profile_index: Optional[int] = 0
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
        index_def = self.build_index(model, key_field_name, vector_search, semantic_search, vector_profile_index)
        result = self.index_client.create_or_update_index(index=index_def)
        print(f"Index '{result.name}' created/updated successfully.")
        return result

    ###########################################################################
    # 1) UPLOAD MODEL INSTANCES WITH EMBEDDINGS
    # https://github.com/Azure/azure-search-vector-samples/blob/main/demo-python/code/basic-vector-workflow/azure-search-vector-python-sample.ipynb
    ###########################################################################
    def upload_documents(
        self,
        model_objects: List[BaseModel],
        embedding_fields: Optional[dict] = None
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
                    vector = get_embeddings(doc[field_name], self.embedding_model_info)
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
    # https://github.com/Azure/azure-search-vector-samples/blob/main/demo-python/code/basic-vector-workflow/azure-search-vector-python-sample.ipynb
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
    # https://github.com/Azure/azure-search-vector-samples/blob/main/demo-python/code/basic-vector-workflow/azure-search-vector-python-sample.ipynb
    ###########################################################################
    def hybrid_search(
        self,
        query: str,
        search_client: SearchClient = None,
        vector_query: Optional[VectorizableTextQuery] = None,
        search_params: SearchParams = SearchParams()
    ) -> List[Dict[str, Any]]:
        """
        Perform a hybrid search, combining a keyword-based search with a 
        vector-based retrieval (RRF re-ranking).

        :param query: The user query string
        :param vector_field: The name of the vector field (e.g. "contentVector")
        :param top: Number of results to return
        :return: A pandas DataFrame with columns ["id", ... , "@search.score"]
        """      

        if search_client is None:
            search_client = self.search_client

        if (vector_query is None) and (search_params.query_type == "semantic"):
            vector_query = VectorizableTextQuery(
                    text=query, 
                    k_nearest_neighbors=50,  # large recall set for better re-ranking
                    fields=search_params.vector_fields,
                    exhaustive=search_params.exhaustive
                )

        results = search_client.search(
            search_text=query,  # the keyword part
            vector_queries=[vector_query] if vector_query is not None else None,
            filter=f"unit_type eq '{search_params.unit_type}'" if search_params.unit_type is not None else None,
            top=search_params.top,
            semantic_configuration_name="my-semantic-config",
            query_type=QueryType.SEMANTIC if search_params.query_type == "semantic" else QueryType.SIMPLE,
        )

        # console.print("Query type:", QueryType.SEMANTIC if search_params.query_type == "semantic" else QueryType.SIMPLE)

        return [r for r in results]



    def widen_step_search(self,
        query: str,
        search_client: SearchClient = None,
        search_params: SearchParams = SearchParams(),
    ) -> List[Dict[str, Any]]:
        
        if search_client is None:
            search_client = self.search_client

        composite_results = []

        # console.print(f"Starting search for query: {query}")

        start_time = datetime.now()

        search_params.query_type = "keyword"
        results = self.hybrid_search(query, search_client=search_client, search_params=search_params)
        composite_results.extend(results)

        search_params.query_type = "semantic"
        results = self.hybrid_search(query, search_client=search_client, search_params=search_params)
        composite_results.extend(results)

        finish_time = datetime.now()

        console.print(f"Search took {finish_time - start_time} for query: {query}")

        return list(composite_results)
    

    def widen_search(
        self,
        query: str,
        search_params: SearchParams = SearchParams(),
        model_info: TextProcessingModelnfo = TextProcessingModelnfo(),
    ) -> List[Dict[str, Any]]:
        """
        Perform a hybrid search, combining a keyword-based search with a 
        vector-based retrieval (RRF re-ranking).

        :param query: The user query string
        :param vector_field: The name of the vector field (e.g. "contentVector")
        :param top: Number of results to return
        :return: A pandas DataFrame with columns ["id", ... , "@search.score"]
        """      
        expanded_terms = expand_searh_terms(query, model_info=model_info)
        console.print("Expanded Terms:", expanded_terms)

        search_terms = [query] + expanded_terms.expanded_terms[:search_params.top_wide_search] + expanded_terms.related_areas[:search_params.top_wide_search]
        search_results = pool.starmap(self.widen_step_search, zip(search_terms, 
                                                                  self.search_clients[:len(search_terms)], 
                                                                  [search_params]*len(search_terms)))

        composite_results = []
        for r in search_results: composite_results.extend(r)

        # Deduplicate results based on index_id
        unique_results = {result['index_id']: result for result in composite_results}.values()
        console.print(f"Total Results: {len(composite_results)} reduced to {len(unique_results)} unique documents.")

        return list(unique_results)
    


    @staticmethod
    def format_search_results(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format the search results for display in a front-end application.
        """
        formatted_results = []
        for result in search_results:
            formatted_result = {}
            for key, value in result.items():
                if key == "index_id":
                    formatted_result["id"] = value
                elif key == "@search.score":
                    formatted_result["score"] = value
                else:
                    formatted_result[key] = value
            formatted_results.append(formatted_result)
        return formatted_results
    







    @staticmethod
    def document_content_to_search_units(doc_content: DocumentContent, convert_post_processing_units: bool = False) -> List[SearchUnit]:
        """
        Generate a list of SearchUnit entries for indexing (text, images, tables).
        """
        search_units: List[SearchUnit] = []
        metadata = doc_content.metadata

        for page in doc_content.pages:
            # 1) The main text
            if page.text and page.text.text and page.text.text.text.strip():
                search_units.append(
                    SearchUnit(
                        metadata=metadata.model_dump(),
                        page_number=page.page_number,
                        page_image_path=convert_path(str(page.page_image_path)),
                        unit_type="text",
                        text=page.text.text.text,
                        text_file_cloud_storage_path=page.text.text.text_file_cloud_storage_path,
                        page_image_cloud_storage_path=page.text.text.page_image_cloud_storage_path
                    )
                )

            # 2) Each embedded image's text
            for image in page.images:
                if image.text and image.text.text and image.text.text.strip():
                    search_units.append(
                        SearchUnit(
                            metadata=metadata.model_dump(),
                            page_number=page.page_number,
                            page_image_path=convert_path(str(page.page_image_path)),
                            unit_type="image",
                            text=image.text.text,
                            text_file_cloud_storage_path=image.text.text_file_cloud_storage_path,
                            page_image_cloud_storage_path=image.text.page_image_cloud_storage_path
                        )
                    )

            # 3) Each table's content
            for table in page.tables:
                if table.text and table.text.text and table.text.text.strip():
                    search_units.append(
                        SearchUnit(
                            metadata=metadata.model_dump(),
                            page_number=page.page_number,
                            page_image_path=convert_path(str(page.page_image_path)),
                            unit_type="table",
                            text=table.text.text,
                            text_file_cloud_storage_path=table.text.text_file_cloud_storage_path,
                            page_image_cloud_storage_path=table.text.page_image_cloud_storage_path
                        )
                    )

        
        if convert_post_processing_units:
            ppc = doc_content.post_processing_content
            if ppc.condensed_text and ppc.condensed_text.text and ppc.condensed_text.text.strip():
                search_units.append(
                    SearchUnit(
                        metadata=metadata.model_dump(),
                        page_number=-1,
                        page_image_path="",
                        unit_type="text",
                        text=ppc.condensed_text.text,
                        text_file_cloud_storage_path=ppc.condensed_text.text_file_cloud_storage_path,
                        page_image_cloud_storage_path=ppc.condensed_text.page_image_cloud_storage_path
                    )
                )

            if ppc.table_of_contents and ppc.table_of_contents.text and ppc.table_of_contents.text.strip():
                search_units.append(
                    SearchUnit(
                        metadata=metadata.model_dump(),
                        page_number=-2,
                        page_image_path="",
                        unit_type="text",
                        text=ppc.table_of_contents.text,
                        text_file_cloud_storage_path=ppc.table_of_contents.text_file_cloud_storage_path,
                        page_image_cloud_storage_path=ppc.table_of_contents.page_image_cloud_storage_path
                    )
                )

            if ppc.full_text and ppc.full_text.text and ppc.full_text.text.strip():
                search_units.append(
                    SearchUnit(
                        metadata=metadata.model_dump(),
                        page_number=-3,
                        page_image_path="",
                        unit_type="text",
                        text=ppc.full_text.text,
                        text_file_cloud_storage_path=ppc.full_text.text_file_cloud_storage_path,
                        page_image_cloud_storage_path=ppc.full_text.page_image_cloud_storage_path
                    )
                )

        return search_units
    
    @staticmethod
    def load_search_units_from_folder(folder_path: Union[str, Path], convert_post_processing_units: bool = False) -> List[DataUnit]:
        """
        Load a DocumentContent from the given folder path, then convert it into DataUnits
        by calling 'document_content_to_data_units'.
        """
        # 1) Reconstruct the DocumentContent using the pipeline's loader method
        doc_content = PDFIngestionPipeline.load_document_content_from_json(folder_path)

        # 2) Convert to DataUnits
        data_units = DynamicAzureIndexBuilder.document_content_to_search_units(doc_content, convert_post_processing_units=convert_post_processing_units)
        return data_units    