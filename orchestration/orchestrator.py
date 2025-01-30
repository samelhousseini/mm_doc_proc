import os
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.append('../')

from multimodal_processing_pipeline.utils.file_utils import * 
from multimodal_processing_pipeline.utils.text_utils import *
from multimodal_processing_pipeline.utils.openai_utils import *
from multimodal_processing_pipeline.data_models import *
from multimodal_processing_pipeline.pipeline_utils import *
from multimodal_processing_pipeline.pdf_ingestion_pipeline import *

from search.search_data_models import *
from search.azure_ai_index_builder import *
from search.configure_ai_search import *
from search.search_data_models import *
from search.search_helpers import *

from storage.azure_blob_storage import *



class DocumentIngestionJob():

    def __init__(self):
        self.index_builder = None

    def search_index(self, 
                     query: str, 
                     search_params: SearchParams = SearchParams(),
                     search_config: Optional[AISearchConfig] = None
                     ):
        
        if self.index_builder is None:
            if search_config is None:
                raise Exception("Index builder is not initialized. Please provide search_config.")
            else:
                self.index_builder =  DynamicAzureIndexBuilder(search_config)
                
        if search_params.search_mode == "hybrid":
            results = self.index_builder.hybrid_search(query=query, search_params=search_params)
        else:
            results = self.index_builder.wide_search(query=query, search_params=search_params)

        return results