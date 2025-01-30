from pydantic import BaseModel
from typing import Optional, List, Literal
from utils.openai_data_models import *
from multimodal_processing_pipeline.data_models import *
from ai_agents.azure_ai_agents.ai_agent_data_models import *



class AISearchConfig(BaseModel):
    index_name: str
    search_endpoint: str = os.getenv("AZURE_AI_SEARCH_SERVICE_NAME")
    search_api_key: str = os.getenv("AZURE_AI_SEARCH_API_KEY")
    embedding_model_info: EmbeddingModelnfo = EmbeddingModelnfo(model_name="text-embedding-3-large", dimensions=3072)
    convert_post_processing_units: bool = False
    vector_profile_name: Optional[str] = "myHnswProfile"


class SearchParams(BaseModel):
    search_mode: Literal["hybrid", "wide"] = "hybrid"
    vector_fields: str = "text_vector"
    unit_type: Optional[Literal["text", "image", "table"]] = None
    top: int = 3
    top_wide_search: int = 3
    exhaustive: bool = False
    query_type: Literal["semantic", "keyword"] = "semantic" # this will be ignored when using wide_search()
    use_code_interpreter: bool = True


class SearchExpansion(BaseModel):
    expanded_terms: List[str]
    related_areas: List[str]


class SearchUnit(BaseModel):
    """
    Search Unit for the AI Search resource.
    """
    metadata: PDFMetadata
    page_number: int
    page_image_path: str  # Path to the saved image file
    unit_type: Literal["text", "image", "table"]
    text_file_cloud_storage_path: Optional[str] = None  # Path to the text file in cloud storage
    page_image_cloud_storage_path: Optional[str] = None  # Path to the image file in cloud storage
    text: str
    text_vector: Optional[List[float]] = None  



class SearchResult(BaseModel):    
    final_answer: str
    table_list: List[str]
    references: List[int]


class MultiModalSearchResponse(BaseModel):
    search_response: SearchResult
    agent_response: Optional[ChatResponse] = None


class UISearchResult(BaseModel):    
    search_unit: SearchUnit
    reference_id: int


class UISearchResults(BaseModel):
    search_results: List[UISearchResult]
    search_expansion: Optional[SearchExpansion] = None
    search_params: SearchParams
    search_time: float
    search_mode: Literal["hybrid", "wide"]
    search_query: str
    search_query_type: Literal["semantic", "keyword"]


    