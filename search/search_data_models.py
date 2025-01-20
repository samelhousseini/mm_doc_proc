from pydantic import BaseModel
from typing import Optional, List, Literal
from multimodal_processing_pipeline.data_models import *

class SearchParams(BaseModel):
    vector_fields: str = "text_vector"
    unit_type: Optional[Literal["text", "image", "table"]] = None
    top: int = 3
    top_wide_search: int = 3
    exhaustive: bool = False
    query_type: Literal["semantic", "keyword"] = "semantic"


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
    search_unit: SearchUnit
    reference_id: int
    