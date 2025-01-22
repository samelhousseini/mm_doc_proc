from pydantic import BaseModel
from typing import Optional, List, Literal
from pathlib import Path

from utils.openai_data_models import *

###############################################################################
# Working data models - used in LLM Structured Outputs calls
###############################################################################

class EmbeddedText(BaseModel):
    """
    Used in LLM call structured output for text analysis.
    """
    processed_text: str
    


class EmbeddedImage(BaseModel):
    """
    Used in LLM call structured output for image analysis.
    """
    graph_or_photo_explanation: str
    contextual_relevance: str
    analysis: str
    image_type: Literal["graph", "photo"]


class EmbeddedImages(BaseModel):
    """
    Used in LLM call structured output for image analysis.
    """
    detected_graphs_or_photos: Optional[List[EmbeddedImage]] 


class EmbeddedTable(BaseModel):
    """
    Used in LLM call structured output for table analysis.
    """
    markdown: str
    contextual_relevance: str
    analysis: str


class EmbeddedTables(BaseModel):
    """
    Used in LLM call structured output for table analysis.
    """
    detected_tables_detailed_markdown: Optional[List[EmbeddedTable]]



###############################################################################
# Document data models - used to store information about the processed document
###############################################################################


class DataUnit(BaseModel):
    text: str
    text_file_path: Optional[str] = None  # Path to the text file in cloud storage
    text_file_cloud_storage_path: Optional[str] = None  # Path to the text file in cloud storage
    page_image_path: Optional[str] = None  # Path to the saved image file
    page_image_cloud_storage_path: Optional[str] = None  # Path to the image file in cloud storage


class PDFMetadata(BaseModel):
    """
    Metadata about the PDF document being processed.
    """
    document_id: str
    document_path: str
    filename: str
    total_pages: int
    processed_pages: int = 0
    output_directory: str
    cloud_storage_path: Optional[str] = None  # Path to the file in cloud storage


class ExtractedText(BaseModel):
    """
    Extracted text content from a page.
    """
    page_number: int
    text: Optional[DataUnit] = None  # Text processed (e.g., cleaned up or summarized)
    processed_or_raw_text: Optional[bool] = False  # True if the text is processed, False if raw


class ExtractedImage(BaseModel):
    """
    Information about images extracted from a page.
    """
    page_number: int
    image_path: str  # Path to the saved image file
    image_type: str
    text: Optional[DataUnit] = None  # GPT-generated text of the image


class ExtractedTable(BaseModel):
    """
    Information about tables extracted from a page.
    """
    page_number: int
    text: Optional[DataUnit] = None  # Markdown representation of the table
    summary: Optional[str] = None  # Optional GPT-generated summary of the table


class PageContent(BaseModel):
    """
    Aggregated content for a single page.
    """
    page_number: int
    text: ExtractedText
    page_image_path: str  # Path to the saved image file
    images: List[ExtractedImage]
    tables: List[ExtractedTable]
    page_text: Optional[DataUnit] = None  # Final combined content for the page
    page_image_cloud_storage_path: Optional[str] = None  # Path to the image file in cloud storage




class PostProcessingContent(BaseModel):
    condensed_text: Optional[DataUnit] = None
    table_of_contents: Optional[DataUnit] = None
    full_text: Optional[DataUnit] = None
    document_json: Optional[DataUnit] = None
    

class DocumentContent(BaseModel):
    """
    Fully processed content of the document.
    """
    metadata: PDFMetadata
    pages: List[PageContent]  # List of processed page content
    full_text: Optional[str] = None  # Combined text from all pages
    post_processing_content: Optional[PostProcessingContent] = None




  