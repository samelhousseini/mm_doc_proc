from pydantic import BaseModel
from typing import Optional, List, Literal
from pathlib import Path


class MulitmodalProcessingModelName(BaseModel):
    """
    Information about the multimodal model name.
    """
    model_name: Literal["gpt-4o", "o1"]
    reasoning_efforts: Optional[Literal["low", "medium", "high"]] = "medium"    


class TextProcessingModelName(BaseModel):
    """
    Information about the multimodal model name.
    """
    model_name: Literal["gpt-4o", "o1", "o1-mini"]
    reasoning_efforts: Optional[Literal["low", "medium", "high"]] = "medium"    


class PDFMetadata(BaseModel):
    """
    Metadata about the PDF document being processed.
    """
    document_id: str
    document_path: Path
    filename: str
    total_pages: int
    processed_pages: int = 0
    output_directory: Path


class ExtractedText(BaseModel):
    """
    Extracted text content from a page.
    """
    page_number: int
    text: Optional[str] = None  # Raw text extracted from the page
    processed_text: Optional[str] = None  # Text processed (e.g., cleaned up or summarized)


class ExtractedImage(BaseModel):
    """
    Information about images extracted from a page.
    """
    page_number: int
    image_path: Path  # Path to the saved image file
    image_type: str
    description: Optional[str] = None  # GPT-generated description of the image


class ExtractedTable(BaseModel):
    """
    Information about tables extracted from a page.
    """
    page_number: int
    table_content: Optional[str] = None  # Markdown representation of the table
    summary: Optional[str] = None  # Optional GPT-generated summary of the table


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


class PageContent(BaseModel):
    """
    Aggregated content for a single page.
    """
    page_number: int
    raw_text: ExtractedText
    page_image_path: Path  # Path to the saved image file
    images: List[ExtractedImage]
    tables: List[ExtractedTable]
    combined_text: Optional[str] = None  # Final combined content for the page
    condensed_text: Optional[str] = None  # Condensed version of the text


class DocumentContent(BaseModel):
    """
    Fully processed content of the document.
    """
    metadata: PDFMetadata
    pages: List[PageContent]  # List of processed page content
    full_text: Optional[str] = None  # Combined text from all pages
    condensed_full_text: Optional[str] = None  # Condensed version of the full text
