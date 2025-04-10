import os
from dotenv import load_dotenv
load_dotenv()

import uuid

import sys
sys.path.append('../')

from utils.file_utils import * 
from utils.text_utils import *
from utils.openai_utils import *

from multimodal_processing_pipeline.data_models import *
from multimodal_processing_pipeline.pipeline_utils import *
from multimodal_processing_pipeline.pdf_ingestion_pipeline import *

from search.search_data_models import *
from search.azure_ai_index_builder import *
from search.configure_ai_search import *
from search.search_data_models import *
from search.search_helpers import *
from database.cosmos_helpers import *
from storage.azure_blob_storage import *



class DocumentIngestionJob():

    def __init__(self, config: ProcessingPipelineConfiguration, search_config: AISearchConfig):
        self.config = config
        self.document = None
        self.index_builder = None
        self.search_config = search_config
        self.index_builder =  DynamicAzureIndexBuilder(self.search_config)
        self.cosmos = CosmosDBHelper()


    def process_pdf(self):
        # Instantiate the pipeline
        pipeline = PDFIngestionPipeline(self.config)

        # Process the PDF
        self.document = pipeline.process_pdf()  
    

    def store_pdf_content(self, container_name=None):
        self.storage = AzureBlobStorage()
        self.document = self.storage.upload_document_content(self.document, container_name=container_name)

    
    def index_pdf_content(self):             
        vector_search, semantic_search = build_configurations(embedding_model_info=self.index_builder.embedding_model_info)
        self.index_builder.create_or_update_index(SearchUnit, vector_search=vector_search, semantic_search=semantic_search)
        search_units = DynamicAzureIndexBuilder.document_content_to_search_units(self.document, convert_post_processing_units=self.search_config.convert_post_processing_units)
        result = self.index_builder.index_documents(search_units, {"text":"text_vector"})
        return result
    

    def save_document_to_cosmos(self):
        # Save the document to Cosmos DB
        json_doc = self.document.model_dump()
        json_doc[COSMOS_CATEGORYID] = COSMOS_CATEGORYID_VALUE
        if self.document.metadata and self.document.metadata.document_id:
            json_doc['id'] = self.document.metadata.document_id
        else:
            json_doc['id'] = str(uuid.uuid4())
        self.cosmos.create_document(document=json_doc)
        return json_doc
    

    def execute_job(self, container_name=None):
        print("[DocumentIngestionJob] execute_job() -> Starting PDF ingestion job...")
        self.process_pdf()
        print("[DocumentIngestionJob] execute_job() -> Storing PDF content...")
        self.store_pdf_content(container_name=container_name)
        print("[DocumentIngestionJob] execute_job() -> Indexing PDF content...")
        self.index_pdf_content()
        print("[DocumentIngestionJob] execute_job() -> Job complete, returning final DocumentContent.")
        self.save_document_to_cosmos()
        print("[DocumentIngestionJob] execute_job() -> Document saved to Cosmos DB.")
        return self.document