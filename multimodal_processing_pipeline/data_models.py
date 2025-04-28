from pydantic import BaseModel
from typing import Set
from typing import Optional, List, Literal, Dict, Any, ClassVar, Type, Union
from pathlib import Path
import json
import os
import re

from utils.openai_data_models import *


###############################################################################
# Base Serializable Model
###############################################################################

class SerializableModel(BaseModel):
    """
    Base class for models that can be serialized to/from JSON files and handle
    their own persistence in both file system and blob storage.
    """
    
    @classmethod
    def from_json(cls, file_path: Union[str, Path]) -> "SerializableModel":
        """
        Create an instance from a JSON file
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)
    
    def to_json(self, file_path: Union[str, Path]) -> str:
        """
        Serialize this instance to a JSON file and return the file path
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
        
        return str(file_path)


###############################################################################
# Pipeline State models 
###############################################################################


class PipelineState(SerializableModel):
    text_extracted_pages: List[int] = []
    custom_page_processing: List[int] = []
    images_extracted_pages: List[int] = []
    tables_extracted_pages: List[int] = []
    post_processing_done: bool = False
    
    class Config:
        json_encoders = {
            set: list
        }
    
    @classmethod
    def load_from_json(cls, file_path: Union[str, Path]) -> "PipelineState":
        """
        Load pipeline state from a JSON file. If file doesn't exist, return a new instance.
        """
        file_path = Path(file_path)
        if file_path.is_file():
            return cls.from_json(file_path)
        return cls()
    
    def save_to_json(self, file_path: Union[str, Path]) -> str:
        """
        Save pipeline state to a JSON file
        """
        return self.to_json(file_path)


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
    visual_description: str
    contextual_relevance: str
    analysis: str
    visual_type: Literal[
            "graph", 
            "photo", 
            "infographic", 
            "generic",                          
            "hardware layout",
            "installation diagram",
            "signal flow",
            "network topology",
            "tool usage",
            "warning sign",
            "safety icon",
            "device front/back panel",
            "UI screen",
            "photo reference"
    ]


class EmbeddedImages(BaseModel):
    """
    Used in LLM call structured output for image analysis.
    """
    detected_visuals: Optional[List[EmbeddedImage]] 


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


class DataUnit(SerializableModel):
    text: str
    language: str = "en"
    text_file_path: Optional[str] = None  # Path to the text file in local storage
    text_file_cloud_storage_path: Optional[str] = None  # Path to the text file in cloud storage
    page_image_path: Optional[str] = None  # Path to the saved image file
    page_image_cloud_storage_path: Optional[str] = None  # Path to the image file in cloud storage
    
    def save_to_file(self, directory_path: Union[str, Path], filename: Optional[str] = None) -> str:
        """
        Save the text content to a file and update the text_file_path.
        
        Args:
            directory_path: Directory to save the file in
            filename: Optional filename (if not provided, will generate one)
            
        Returns:
            Path to the saved file
        """
        directory_path = Path(directory_path)
        directory_path.mkdir(parents=True, exist_ok=True)
        
        if not filename:
            # Generate a unique filename based on content hash or timestamp
            import hashlib
            name_hash = hashlib.md5(self.text[:100].encode()).hexdigest()[:8]
            filename = f"content_{name_hash}.txt"
        
        file_path = directory_path / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.text)
        
        self.text_file_path = str(file_path)
        return self.text_file_path
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path], page_image_path: Optional[str] = None) -> "DataUnit":
        """
        Create a new DataUnit from a text file
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        
        return cls(
            text=text_content,
            text_file_path=str(file_path),
            page_image_path=page_image_path
        )
    
    def upload_to_blob(self, blob_storage, container_name: str, blob_prefix: Optional[str] = None) -> None:
        """
        Upload text file and page image to blob storage and update cloud paths
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
            blob_prefix: Optional prefix for blob names (e.g., "pages/page_1/")
        """
        if not self.text_file_path or not Path(self.text_file_path).is_file():
            return
        
        # 1. Upload text file
        file_path = Path(self.text_file_path)
        
        if blob_prefix:
            blob_name = f"{blob_prefix}/{file_path.name}"
        else:
            blob_name = file_path.name
            
        cloud_uri = blob_storage.upload_blob(container_name, blob_name, str(file_path))
        self.text_file_cloud_storage_path = cloud_uri
        
        # 2. Upload page image if present
        if self.page_image_path and Path(self.page_image_path).is_file():
            img_path = Path(self.page_image_path)
            
            if blob_prefix:
                img_blob_name = f"{blob_prefix}/{img_path.name}"
            else:
                img_blob_name = img_path.name
                
            img_cloud_uri = blob_storage.upload_blob(container_name, img_blob_name, str(img_path))
            self.page_image_cloud_storage_path = img_cloud_uri
    
    def download_from_blob(self, blob_storage, local_dir: Union[str, Path]) -> None:
        """
        Download content from blob storage to local directory
        
        Args:
            blob_storage: AzureBlobStorage instance
            local_dir: Local directory to download files to
        """
        local_dir = Path(local_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Download text file if cloud path exists
        if self.text_file_cloud_storage_path:
            try:
                local_text_path = blob_storage.download_blob_url(
                    self.text_file_cloud_storage_path, 
                    local_folder=str(local_dir)
                )
                self.text_file_path = local_text_path
            except Exception as e:
                print(f"Failed to download text file: {e}")
        
        # 2. Download image if cloud path exists
        if self.page_image_cloud_storage_path:
            try:
                local_image_path = blob_storage.download_blob_url(
                    self.page_image_cloud_storage_path,
                    local_folder=str(local_dir)
                )
                self.page_image_path = local_image_path
            except Exception as e:
                print(f"Failed to download image file: {e}")
    
    def create_embedding(self, model_info: TextProcessingModelnfo) -> List[float]:
        """
        Generate embeddings for this DataUnit's text content
        
        Args:
            model_info: Model information for generating embeddings
            
        Returns:
            List of embedding values
        """
        # This would call the appropriate embedding generation function
        # For now, we'll leave this as a placeholder
        # return create_embeddings_for_text(self.text, model_info)
        return []


class PDFMetadata(SerializableModel):
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
    
    def save_to_json(self, file_path: Union[str, Path]) -> str:
        """
        Save metadata to a JSON file
        """
        return self.to_json(file_path)
    
    @classmethod
    def load_from_json(cls, file_path: Union[str, Path]) -> "PDFMetadata":
        """
        Load metadata from a JSON file
        """
        return cls.from_json(file_path)
    
    def upload_pdf_to_blob(self, blob_storage, container_name: str) -> None:
        """
        Upload original PDF file to blob storage and update cloud_storage_path
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
        """
        if not self.document_path or not Path(self.document_path).is_file():
            return
        
        pdf_path = Path(self.document_path)
        blob_name = f"{self.document_id}/{pdf_path.name}"
        cloud_uri = blob_storage.upload_blob(container_name, blob_name, str(pdf_path))
        self.cloud_storage_path = cloud_uri


class ExtractedText(SerializableModel):
    """
    Extracted text content from a page.
    """
    page_number: int
    text: Optional[DataUnit] = None  # Text processed (e.g., cleaned up or summarized)
    
    def save_to_directory(self, directory: Union[str, Path]) -> str:
        """
        Save the extracted text to a directory
        
        Args:
            directory: Directory to save the text in
            
        Returns:
            Path to the saved file
        """
        directory_path = Path(directory) / "pages" / f"page_{self.page_number}"
        directory_path.mkdir(parents=True, exist_ok=True)
        
        if self.text:
            filename = f"page_{self.page_number}.txt"
            return self.text.save_to_file(directory_path, filename)
        return ""
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path], page_number: int, page_image_path: Optional[str] = None) -> "ExtractedText":
        """
        Load extracted text from a file
        
        Args:
            file_path: Path to the text file
            page_number: Page number
            page_image_path: Optional path to the page image
            
        Returns:
            ExtractedText instance
        """
        data_unit = DataUnit.load_from_file(file_path, page_image_path)
        return cls(
            page_number=page_number,
            text=data_unit
        )
    
    def upload_to_blob(self, blob_storage, container_name: str, blob_prefix: Optional[str] = None) -> None:
        """
        Upload text content to blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
            blob_prefix: Optional prefix for blob names (e.g., "pages/page_1/")
        """
        if self.text:
            if blob_prefix is None:
                prefix = f"pages/page_{self.page_number}"
            else:
                prefix = f"{blob_prefix}/pages/page_{self.page_number}"
                
            self.text.upload_to_blob(blob_storage, container_name, prefix)
    
    def download_from_blob(self, blob_storage, local_dir: Union[str, Path]) -> None:
        """
        Download content from blob storage to local directory
        
        Args:
            blob_storage: AzureBlobStorage instance
            local_dir: Local directory to download files to
        """
        if self.text:
            page_dir = Path(local_dir) / "pages" / f"page_{self.page_number}"
            page_dir.mkdir(parents=True, exist_ok=True)
            self.text.download_from_blob(blob_storage, page_dir)


class ExtractedImage(SerializableModel):
    """
    Information about images extracted from a page.
    """
    page_number: int
    image_path: str  # Path to the saved image file
    image_type: str
    text: Optional[DataUnit] = None  # GPT-generated text of the image
    
    def save_to_directory(self, directory: Union[str, Path], index: int) -> str:
        """
        Save the image information to a directory
        
        Args:
            directory: Directory to save the image information in
            index: Index of the image (for multiple images per page)
            
        Returns:
            Path to the saved file
        """
        images_dir = Path(directory) / "pages" / f"page_{self.page_number}" / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        if self.text:
            filename = f"page_{self.page_number}_{self.image_type}_{index+1}.txt"
            return self.text.save_to_file(images_dir, filename)
        return ""
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path], page_number: int, image_path: str, image_type: str) -> "ExtractedImage":
        """
        Load extracted image information from a file
        
        Args:
            file_path: Path to the text file with image description
            page_number: Page number
            image_path: Path to the image file
            image_type: Type of image
            
        Returns:
            ExtractedImage instance
        """
        data_unit = DataUnit.load_from_file(file_path, image_path)
        return cls(
            page_number=page_number,
            image_path=image_path,
            image_type=image_type,
            text=data_unit
        )
    
    def upload_to_blob(self, blob_storage, container_name: str, blob_prefix: Optional[str] = None) -> None:
        """
        Upload image information to blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
            blob_prefix: Optional prefix for blob names
        """
        if self.text:
            if blob_prefix is None:
                prefix = f"pages/page_{self.page_number}/images"
            else:
                prefix = f"{blob_prefix}/pages/page_{self.page_number}/images"
                
            self.text.upload_to_blob(blob_storage, container_name, prefix)
    
    def download_from_blob(self, blob_storage, local_dir: Union[str, Path]) -> None:
        """
        Download image information from blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            local_dir: Local directory to download files to
        """
        if self.text:
            images_dir = Path(local_dir) / "pages" / f"page_{self.page_number}" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)
            self.text.download_from_blob(blob_storage, images_dir)


class ExtractedTable(SerializableModel):
    """
    Information about tables extracted from a page.
    """
    page_number: int
    text: Optional[DataUnit] = None  # Markdown representation of the table
    summary: Optional[str] = None  # Optional GPT-generated summary of the table
    
    def save_to_directory(self, directory: Union[str, Path], index: int) -> str:
        """
        Save the table information to a directory
        
        Args:
            directory: Directory to save the table information in
            index: Index of the table (for multiple tables per page)
            
        Returns:
            Path to the saved file
        """
        tables_dir = Path(directory) / "pages" / f"page_{self.page_number}" / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        
        if self.text:
            filename = f"page_{self.page_number}_table_{index+1}.txt"
            return self.text.save_to_file(tables_dir, filename)
        return ""
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path], page_number: int, page_image_path: Optional[str] = None) -> "ExtractedTable":
        """
        Load extracted table information from a file
        
        Args:
            file_path: Path to the text file with table content
            page_number: Page number
            page_image_path: Optional path to the page image
            
        Returns:
            ExtractedTable instance
        """
        data_unit = DataUnit.load_from_file(file_path, page_image_path)
        
        # Try to split content into markdown and summary if possible
        content = data_unit.text
        summary = None
        
        # Look for summary sections
        summary_pattern = r"\n*Summary:\s*([\s\S]+)$"
        match = re.search(summary_pattern, content)
        if match:
            summary = match.group(1).strip()
            content = re.sub(summary_pattern, "", content).strip()
            data_unit.text = content
        
        return cls(
            page_number=page_number,
            text=data_unit,
            summary=summary
        )
    
    def upload_to_blob(self, blob_storage, container_name: str, blob_prefix: Optional[str] = None) -> None:
        """
        Upload table information to blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
            blob_prefix: Optional prefix for blob names
        """
        if self.text:
            if blob_prefix is None:
                prefix = f"pages/page_{self.page_number}/tables"
            else:
                prefix = f"{blob_prefix}/pages/page_{self.page_number}/tables"
                
            self.text.upload_to_blob(blob_storage, container_name, prefix)
    
    def download_from_blob(self, blob_storage, local_dir: Union[str, Path]) -> None:
        """
        Download table information from blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            local_dir: Local directory to download files to
        """
        if self.text:
            tables_dir = Path(local_dir) / "pages" / f"page_{self.page_number}" / "tables"
            tables_dir.mkdir(parents=True, exist_ok=True)
            self.text.download_from_blob(blob_storage, tables_dir)


class PageContent(SerializableModel):
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
    custom_page_processing_steps: Optional[List[DataUnit]] = []  # Custom processed page text
    
    def save_to_directory(self, directory: Union[str, Path]) -> Dict[str, str]:
        """
        Save all page content (text, images, tables) to structured folders
        
        Args:
            directory: Root directory for saving content
            
        Returns:
            Dictionary of saved file paths
        """
        directory_path = Path(directory)
        page_dir = directory_path / "pages" / f"page_{self.page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        
        saved_paths = {}
        
        # 1. Save ExtractedText
        if self.text:
            text_path = self.text.save_to_directory(directory_path)
            if text_path:
                saved_paths["text"] = text_path
        
        # 2. Save images
        for i, image in enumerate(self.images):
            img_path = image.save_to_directory(directory_path, i)
            if img_path:
                saved_paths[f"image_{i}"] = img_path
        
        # 3. Save tables
        for i, table in enumerate(self.tables):
            tbl_path = table.save_to_directory(directory_path, i)
            if tbl_path:
                saved_paths[f"table_{i}"] = tbl_path
        
        # 4. Save combined page text
        if self.page_text:
            twin_filename = f"page_{self.page_number}_twin.txt"
            page_text_path = self.page_text.save_to_file(page_dir, twin_filename)
            saved_paths["page_text"] = page_text_path
        
        # 5. Save custom page processing steps
        if self.custom_page_processing_steps:
            custom_proc_dir = page_dir / "custom_processing"
            custom_proc_dir.mkdir(parents=True, exist_ok=True)
            
            for i, step in enumerate(self.custom_page_processing_steps):
                step_path = step.save_to_file(custom_proc_dir, f"page_step_{i+1}.txt")
                saved_paths[f"custom_step_{i}"] = step_path
        
        return saved_paths
    
    @classmethod
    def load_from_directory(cls, directory: Union[str, Path], page_number: int) -> "PageContent":
        """
        Create PageContent from directory structure
        
        Args:
            directory: Root directory containing the page data
            page_number: Page number to load
            
        Returns:
            PageContent instance
        """
        directory_path = Path(directory)
        page_dir = directory_path / "pages" / f"page_{self.page_number}"
        
        # Try to find page image
        page_image_path = None
        for ext in [".png", ".jpg", ".jpeg"]:
            img_path = page_dir / f"page_{page_number}{ext}"
            if img_path.is_file():
                page_image_path = str(img_path)
                break
        
        if not page_image_path:
            raise FileNotFoundError(f"No image found for page {page_number}")
            
        # Load extracted text
        text_file = page_dir / f"page_{page_number}.txt"
        extracted_text = None
        if text_file.is_file():
            extracted_text = ExtractedText.load_from_file(
                text_file, 
                page_number, 
                page_image_path
            )
        else:
            # Create empty extracted text if file doesn't exist
            extracted_text = ExtractedText(
                page_number=page_number,
                text=DataUnit(text="")
            )
        
        # Load images
        images_dir = page_dir / "images"
        images = []
        if images_dir.is_dir():
            img_pattern = re.compile(r"^page_(\d+)_(.+)_(\d+)\.txt$")
            for text_file in sorted(images_dir.glob(f"page_{page_number}_*_*.txt")):
                match = img_pattern.match(text_file.name)
                if match:
                    page_num, img_type, idx = match.groups()
                    image = ExtractedImage.load_from_file(
                        text_file,
                        page_number,
                        page_image_path,
                        img_type
                    )
                    images.append(image)
        
        # Load tables
        tables_dir = page_dir / "tables"
        tables = []
        if tables_dir.is_dir():
            tbl_pattern = re.compile(r"^page_(\d+)_table_(\d+)\.txt$")
            for tbl_file in sorted(tables_dir.glob(f"page_{page_number}_table_*.txt")):
                match = tbl_pattern.match(tbl_file.name)
                if match:
                    table = ExtractedTable.load_from_file(
                        tbl_file,
                        page_number,
                        page_image_path
                    )
                    tables.append(table)
                    
        # Load combined page text
        page_text = None
        twin_file = page_dir / f"page_{page_number}_twin.txt"
        if twin_file.is_file():
            page_text = DataUnit.load_from_file(twin_file, page_image_path)
            
        # Load custom page processing steps
        custom_steps = []
        custom_proc_dir = page_dir / "custom_processing"
        if custom_proc_dir.is_dir():
            for step_file in sorted(custom_proc_dir.glob("page_step_*.txt")):
                step = DataUnit.load_from_file(step_file, page_image_path)
                custom_steps.append(step)
                
        return cls(
            page_number=page_number,
            text=extracted_text,
            page_image_path=page_image_path,
            images=images,
            tables=tables,
            page_text=page_text,
            custom_page_processing_steps=custom_steps
        )
    
    def upload_to_blob(self, blob_storage, container_name: str, blob_prefix: Optional[str] = None) -> None:
        """
        Upload all page content to blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
            blob_prefix: Optional prefix for blob names
        """
        if blob_prefix is None:
            page_prefix = f"pages/page_{self.page_number}"
        else:
            page_prefix = f"{blob_prefix}/pages/page_{self.page_number}"
        
        # 1. Upload the main page image
        if self.page_image_path and Path(self.page_image_path).is_file():
            img_path = Path(self.page_image_path)
            blob_name = f"{page_prefix}/{img_path.name}"
            cloud_uri = blob_storage.upload_blob(container_name, blob_name, str(img_path))
            self.page_image_cloud_storage_path = cloud_uri
        
        # 2. Upload the extracted text
        if self.text:
            self.text.upload_to_blob(blob_storage, container_name, blob_prefix)
        
        # 3. Upload the combined page_text
        if self.page_text:
            self.page_text.upload_to_blob(blob_storage, container_name, page_prefix)
        
        # 4. Upload custom processing steps
        for step in self.custom_page_processing_steps:
            step.upload_to_blob(blob_storage, container_name, f"{page_prefix}/custom_processing")
        
        # 5. Upload images
        for image in self.images:
            image.upload_to_blob(blob_storage, container_name, blob_prefix)
        
        # 6. Upload tables
        for table in self.tables:
            table.upload_to_blob(blob_storage, container_name, blob_prefix)
    
    def download_from_blob(self, blob_storage, container_name: str, local_dir: Union[str, Path]) -> None:
        """
        Download all page content from blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name where content is stored
            local_dir: Local directory to download files to
        """
        page_dir = Path(local_dir) / "pages" / f"page_{self.page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Download main page image
        if self.page_image_cloud_storage_path:
            try:
                local_img_path = blob_storage.download_blob_url(
                    self.page_image_cloud_storage_path,
                    local_folder=str(page_dir)
                )
                self.page_image_path = local_img_path
            except Exception as e:
                print(f"Failed to download page image: {e}")
        
        # 2. Download extracted text
        if self.text:
            self.text.download_from_blob(blob_storage, local_dir)
        
        # 3. Download combined page text
        if self.page_text:
            self.page_text.download_from_blob(blob_storage, page_dir)
        
        # 4. Download custom processing steps
        custom_proc_dir = page_dir / "custom_processing"
        custom_proc_dir.mkdir(parents=True, exist_ok=True)
        
        for step in self.custom_page_processing_steps:
            step.download_from_blob(blob_storage, custom_proc_dir)
        
        # 5. Download images
        for image in self.images:
            image.download_from_blob(blob_storage, local_dir)
        
        # 6. Download tables
        for table in self.tables:
            table.download_from_blob(blob_storage, local_dir)
    
    def combine_content(self) -> str:
        """
        Generate combined text representation of all page content
        
        Returns:
            Combined text content for the page
        """
        combined = f"##### --- Page {self.page_number} ---\n\n"
        
        # Add extracted text
        combined += "# Extracted Text\n\n"
        if self.text and self.text.text and self.text.text.text:
            combined += f"{self.text.text.text}\n\n"
        
        # Add images
        if self.images:
            combined += "\n# Embedded Images:\n\n"
            for i, image in enumerate(self.images):
                combined += f"### - Image {i+1}:\n"
                if image.text and image.text.text:
                    combined += f"{image.text.text}\n\n"
        
        # Add tables
        if self.tables:
            combined += "\n# Tables:\n\n"
            for i, table in enumerate(self.tables):
                combined += f"### - Table {i+1}:\n\n"
                if table.text and table.text.text:
                    combined += f"{table.text.text}\n\n"
                if table.summary:
                    combined += f"Summary:\n{table.summary}\n\n"
        
        # Add page image reference
        if self.page_image_path:
            combined += (
                f'<br/>\n<br/>\n<img src="{self.page_image_path}" '
                f'alt="Page Number {self.page_number}" width="300" height="425">'
            )
        
        combined += "\n\n\n\n"
        return combined
    
    def apply_custom_processing(self, processing_steps: List[Dict[str, Any]]) -> List[DataUnit]:
        """
        Apply custom processing steps to the page content
        
        Args:
            processing_steps: Configuration for custom processing
            
        Returns:
            List of DataUnit objects with processing results
        """
        # This would call the actual processing function with page content
        # For now returning placeholder/empty list
        return []


class PostProcessingContent(SerializableModel):
    condensed_text: Optional[DataUnit] = None
    table_of_contents: Optional[DataUnit] = None
    full_text: Optional[DataUnit] = None
    translated_full_texts: Optional[List[DataUnit]] = None
    translated_condensed_texts: Optional[List[DataUnit]] = None
    custom_document_processing_steps: Optional[List[DataUnit]] = []  # Custom processed document text
    document_json: Optional[DataUnit] = None
    
    def save_to_directory(self, directory: Union[str, Path]) -> Dict[str, str]:
        """
        Save all post-processing files to the specified directory
        
        Args:
            directory: Directory to save files in
            
        Returns:
            Dictionary of saved file paths
        """
        directory_path = Path(directory)
        saved_paths = {}
        
        # 1. Save condensed text
        if self.condensed_text:
            condensed_path = self.condensed_text.save_to_file(
                directory_path, 
                "condensed_text.md"
            )
            saved_paths["condensed_text"] = condensed_path
        
        # 2. Save table of contents
        if self.table_of_contents:
            toc_path = self.table_of_contents.save_to_file(
                directory_path, 
                "table_of_contents.md"
            )
            saved_paths["table_of_contents"] = toc_path
        
        # 3. Save full text
        if self.full_text:
            full_text_path = self.full_text.save_to_file(
                directory_path, 
                "text_twin.md"
            )
            saved_paths["full_text"] = full_text_path
        
        # 4. Save document JSON reference
        if self.document_json:
            doc_json_path = self.document_json.save_to_file(
                directory_path, 
                "document_content.json"
            )
            saved_paths["document_json"] = doc_json_path
        
        # 5. Save translations
        translations_dir = directory_path / "translations"
        translations_dir.mkdir(parents=True, exist_ok=True)
        
        # Save translated full texts
        if self.translated_full_texts:
            for i, trans in enumerate(self.translated_full_texts):
                lang = trans.language or f"lang_{i}"
                filename = f"full_text_{lang}.txt"
                trans_path = trans.save_to_file(translations_dir, filename)
                saved_paths[f"full_text_translation_{lang}"] = trans_path
        
        # Save translated condensed texts
        if self.translated_condensed_texts:
            for i, trans in enumerate(self.translated_condensed_texts):
                lang = trans.language or f"lang_{i}"
                filename = f"condensed_text_{lang}.txt"
                trans_path = trans.save_to_file(translations_dir, filename)
                saved_paths[f"condensed_text_translation_{lang}"] = trans_path
        
        # 6. Save custom document processing steps
        if self.custom_document_processing_steps:
            custom_proc_dir = directory_path / "custom_processing"
            custom_proc_dir.mkdir(parents=True, exist_ok=True)
            
            for i, step in enumerate(self.custom_document_processing_steps):
                step_filename = f"document_step_{i+1}.txt"
                step_path = step.save_to_file(custom_proc_dir, step_filename)
                saved_paths[f"custom_document_step_{i}"] = step_path
                
        return saved_paths
    
    @classmethod
    def load_from_directory(cls, directory: Union[str, Path]) -> "PostProcessingContent":
        """
        Load post-processing content from directory structure
        
        Args:
            directory: Directory containing post-processing files
            
        Returns:
            PostProcessingContent instance
        """
        directory_path = Path(directory)
        
        # Initialize post-processing content
        post_proc = cls()
        
        # 1. Load condensed text
        condensed_path = directory_path / "condensed_text.md"
        if condensed_path.is_file():
            post_proc.condensed_text = DataUnit.load_from_file(condensed_path)
        
        # 2. Load table of contents
        toc_path = directory_path / "table_of_contents.md"
        if toc_path.is_file():
            post_proc.table_of_contents = DataUnit.load_from_file(toc_path)
        
        # 3. Load full text
        full_text_path = directory_path / "text_twin.md"
        if full_text_path.is_file():
            post_proc.full_text = DataUnit.load_from_file(full_text_path)
        
        # 4. Load document JSON reference
        doc_json_path = directory_path / "document_content.json"
        if doc_json_path.is_file():
            post_proc.document_json = DataUnit(
                text="",  # We don't load the actual content here
                text_file_path=str(doc_json_path)
            )
        
        # 5. Load translations
        translations_dir = directory_path / "translations"
        if translations_dir.is_dir():
            # Initialize lists if they don't exist
            if post_proc.translated_full_texts is None:
                post_proc.translated_full_texts = []
            if post_proc.translated_condensed_texts is None:
                post_proc.translated_condensed_texts = []
                
            # Process translation files
            for file in translations_dir.glob("*.txt"):
                filename = file.name
                # Match pattern like "full_text_fr.txt" or "condensed_text_fr.txt"
                match = re.match(r"^(full_text|condensed_text)_(\w+)\.txt$", filename)
                if match:
                    text_type, lang = match.groups()
                    data_unit = DataUnit.load_from_file(file)
                    data_unit.language = lang
                    
                    if text_type == "full_text":
                        post_proc.translated_full_texts.append(data_unit)
                    else:  # condensed_text
                        post_proc.translated_condensed_texts.append(data_unit)
        
        # 6. Load custom document processing steps
        custom_proc_dir = directory_path / "custom_processing"
        if custom_proc_dir.is_dir():
            custom_steps = []
            for step_file in sorted(custom_proc_dir.glob("document_step_*.txt")):
                step = DataUnit.load_from_file(step_file)
                custom_steps.append(step)
            
            if custom_steps:
                post_proc.custom_document_processing_steps = custom_steps
                
        return post_proc
    
    def upload_to_blob(self, blob_storage, container_name: str, blob_prefix: Optional[str] = None) -> None:
        """
        Upload all post-processing content to blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name for uploads
            blob_prefix: Optional prefix for blob names
        """
        # 1. Upload condensed text
        if self.condensed_text:
            self.condensed_text.upload_to_blob(blob_storage, container_name, blob_prefix)
        
        # 2. Upload table of contents
        if self.table_of_contents:
            self.table_of_contents.upload_to_blob(blob_storage, container_name, blob_prefix)
        
        # 3. Upload full text
        if self.full_text:
            self.full_text.upload_to_blob(blob_storage, container_name, blob_prefix)
        
        # 4. Upload document JSON reference
        if self.document_json:
            self.document_json.upload_to_blob(blob_storage, container_name, blob_prefix)
        
        # 5. Upload translations
        translations_prefix = blob_prefix
        if blob_prefix:
            translations_prefix = f"{blob_prefix}/translations"
        else:
            translations_prefix = "translations"
            
        # Upload translated full texts
        if self.translated_full_texts:
            for trans in self.translated_full_texts:
                trans.upload_to_blob(blob_storage, container_name, translations_prefix)
        
        # Upload translated condensed texts
        if self.translated_condensed_texts:
            for trans in self.translated_condensed_texts:
                trans.upload_to_blob(blob_storage, container_name, translations_prefix)
        
        # 6. Upload custom document processing steps
        custom_prefix = blob_prefix
        if blob_prefix:
            custom_prefix = f"{blob_prefix}/custom_processing"
        else:
            custom_prefix = "custom_processing"
            
        if self.custom_document_processing_steps:
            for step in self.custom_document_processing_steps:
                step.upload_to_blob(blob_storage, container_name, custom_prefix)
    
    def download_from_blob(self, blob_storage, container_name: str, local_dir: Union[str, Path]) -> None:
        """
        Download all post-processing content from blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name where content is stored
            local_dir: Local directory to download files to
        """
        local_dir_path = Path(local_dir)
        
        # 1. Download condensed text
        if self.condensed_text and self.condensed_text.text_file_cloud_storage_path:
            self.condensed_text.download_from_blob(blob_storage, local_dir_path)
        
        # 2. Download table of contents
        if self.table_of_contents and self.table_of_contents.text_file_cloud_storage_path:
            self.table_of_contents.download_from_blob(blob_storage, local_dir_path)
        
        # 3. Download full text
        if self.full_text and self.full_text.text_file_cloud_storage_path:
            self.full_text.download_from_blob(blob_storage, local_dir_path)
        
        # 4. Download document JSON reference
        if self.document_json and self.document_json.text_file_cloud_storage_path:
            self.document_json.download_from_blob(blob_storage, local_dir_path)
        
        # 5. Download translations
        translations_dir = local_dir_path / "translations"
        translations_dir.mkdir(parents=True, exist_ok=True)
        
        # Download translated full texts
        if self.translated_full_texts:
            for trans in self.translated_full_texts:
                if trans.text_file_cloud_storage_path:
                    trans.download_from_blob(blob_storage, translations_dir)
        
        # Download translated condensed texts
        if self.translated_condensed_texts:
            for trans in self.translated_condensed_texts:
                if trans.text_file_cloud_storage_path:
                    trans.download_from_blob(blob_storage, translations_dir)
        
        # 6. Download custom document processing steps
        custom_proc_dir = local_dir_path / "custom_processing"
        custom_proc_dir.mkdir(parents=True, exist_ok=True)
        
        if self.custom_document_processing_steps:
            for step in self.custom_document_processing_steps:
                if step.text_file_cloud_storage_path:
                    step.download_from_blob(blob_storage, custom_proc_dir)


class DocumentContent(SerializableModel):
    """
    Fully processed content of the document.
    """
    metadata: PDFMetadata
    pages: List[PageContent]  # List of processed page content
    full_text: Optional[str] = None  # Combined text from all pages
    post_processing_content: Optional[PostProcessingContent] = None
    
    def save_to_directory(self, directory: Union[str, Path]) -> str:
        """
        Save entire document structure to directory
        
        Args:
            directory: Directory to save document content in
            
        Returns:
            Path to the saved document JSON file
        """
        directory_path = Path(directory)
        directory_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Save metadata
        metadata_file = directory_path / "metadata.json"
        self.metadata.save_to_json(metadata_file)
        
        # 2. Save each page
        for page in self.pages:
            page.save_to_directory(directory_path)
        
        # 3. Save full text if available
        if self.full_text:
            full_text_path = directory_path / "text_twin.md"
            with open(full_text_path, 'w', encoding='utf-8') as f:
                f.write(self.full_text)
            
            # Create DataUnit for full text if post_processing_content exists
            if self.post_processing_content and not self.post_processing_content.full_text:
                self.post_processing_content.full_text = DataUnit(
                    text=self.full_text,
                    text_file_path=str(full_text_path)
                )
        
        # 4. Save post-processing content
        if self.post_processing_content:
            self.post_processing_content.save_to_directory(directory_path)
        
        # 5. Save complete document content as JSON
        doc_json_path = directory_path / "document_content.json"
        self.to_json(doc_json_path)
        
        # Ensure post_processing_content.document_json is set
        if not self.post_processing_content:
            self.post_processing_content = PostProcessingContent()
            
        if not self.post_processing_content.document_json:
            self.post_processing_content.document_json = DataUnit(
                text="",
                text_file_path=str(doc_json_path)
            )
        
        return str(doc_json_path)
    
    def save_to_json(self, file_path: Union[str, Path]) -> str:
        """
        Serialize DocumentContent to a JSON file
        """
        return self.to_json(file_path)
    
    @classmethod
    def load_from_json(cls, file_path: Union[str, Path]) -> "DocumentContent":
        """
        Load DocumentContent from a JSON file
        """
        return cls.from_json(file_path)
    
    @classmethod
    def load_from_directory(cls, directory: Union[str, Path]) -> "DocumentContent":
        """
        Build document structure from directory
        
        Args:
            directory: Directory containing document data
            
        Returns:
            DocumentContent instance
        """
        directory_path = Path(directory)
        
        # Check if we have a document_content.json file, which is the preferred way to load
        doc_json_path = directory_path / "document_content.json"
        if doc_json_path.is_file():
            return cls.load_from_json(doc_json_path)
        
        # Otherwise rebuild from directory structure
        # 1. Load metadata
        metadata_file = directory_path / "metadata.json"
        if metadata_file.is_file():
            metadata = PDFMetadata.load_from_json(metadata_file)
        else:
            # Create minimal metadata from directory name
            metadata = PDFMetadata(
                document_id=directory_path.name,
                document_path=str(directory_path / f"{directory_path.name}.pdf"),
                filename=f"{directory_path.name}.pdf",
                total_pages=0,  # Will be updated later
                output_directory=str(directory_path)
            )
        
        # 2. Find all page directories and load pages
        pages_dir = directory_path / "pages"
        pages = []
        
        if pages_dir.is_dir():
            page_dirs = sorted([
                d for d in pages_dir.iterdir() 
                if d.is_dir() and d.name.startswith("page_")
            ], key=lambda d: int(d.name.split("_")[1]))
            
            for page_dir in page_dirs:
                try:
                    page_number = int(page_dir.name.split("_")[1])
                    page = PageContent.load_from_directory(directory_path, page_number)
                    pages.append(page)
                except Exception as e:
                    print(f"Error loading page {page_dir.name}: {e}")
        
        # Update metadata total_pages if needed
        if len(pages) > 0 and metadata.total_pages == 0:
            metadata.total_pages = len(pages)
            metadata.processed_pages = len(pages)
        
        # 3. Load full text
        full_text = None
        full_text_path = directory_path / "text_twin.md"
        if full_text_path.is_file():
            with open(full_text_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
        
        # 4. Load post-processing content
        post_processing_content = PostProcessingContent.load_from_directory(directory_path)
        
        return cls(
            metadata=metadata,
            pages=pages,
            full_text=full_text,
            post_processing_content=post_processing_content
        )
    
    def upload_to_blob(self, blob_storage, container_name: Optional[str] = None) -> None:
        """
        Upload entire document to blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Optional container name for uploads (defaults to document ID)
        """
        # 1. Determine container name
        if container_name is None:
            if self.metadata and self.metadata.document_id:
                container_name = self.metadata.document_id
            else:
                container_name = "document-content"
        
        # Ensure container exists and is sanitized by blob_storage
        safe_container = blob_storage._safe_container_name(container_name)
        blob_storage.create_container(safe_container)
        
        # Determine blob prefix (typically document_id)
        blob_prefix = None
        if self.metadata and self.metadata.document_id:
            blob_prefix = self.metadata.document_id
        
        # 2. Upload the PDF document if available
        if self.metadata and self.metadata.document_path:
            self.metadata.upload_pdf_to_blob(blob_storage, safe_container)
        
        # 3. Upload each page
        for page in self.pages:
            page.upload_to_blob(blob_storage, safe_container, blob_prefix)
        
        # 4. Upload post-processing content
        if self.post_processing_content:
            self.post_processing_content.upload_to_blob(blob_storage, safe_container, blob_prefix)
        
        # 5. Upload the complete document JSON
        # First save it locally if needed
        if not self.post_processing_content or not self.post_processing_content.document_json:
            temp_json_path = Path(self.metadata.output_directory) / "document_content.json"
            self.save_to_json(temp_json_path)
            
            if not self.post_processing_content:
                self.post_processing_content = PostProcessingContent()
            
            self.post_processing_content.document_json = DataUnit(
                text="",
                text_file_path=str(temp_json_path)
            )
        
        # Now upload the JSON file
        if self.post_processing_content and self.post_processing_content.document_json:
            json_path = self.post_processing_content.document_json.text_file_path
            if json_path and Path(json_path).is_file():
                if blob_prefix:
                    blob_name = f"{blob_prefix}/document_content.json"
                else:
                    blob_name = "document_content.json"
                    
                cloud_uri = blob_storage.upload_blob(safe_container, blob_name, json_path)
                self.post_processing_content.document_json.text_file_cloud_storage_path = cloud_uri
    
    def download_from_blob(self, blob_storage, container_name: str, local_dir: Union[str, Path]) -> None:
        """
        Download entire document from blob storage
        
        Args:
            blob_storage: AzureBlobStorage instance
            container_name: Container name where document is stored
            local_dir: Local directory to download files to
        """
        local_dir_path = Path(local_dir)
        local_dir_path.mkdir(parents=True, exist_ok=True)
        
        # 1. First try to download document_content.json to reconstruct everything
        doc_json_cloud_path = None
        
        if self.post_processing_content and self.post_processing_content.document_json:
            doc_json_cloud_path = self.post_processing_content.document_json.text_file_cloud_storage_path
        
        if not doc_json_cloud_path:
            # Try a common location
            blob_prefix = None
            if self.metadata and self.metadata.document_id:
                blob_prefix = self.metadata.document_id
                
            if blob_prefix:
                # List blobs to find document_content.json
                blobs = blob_storage.list_blobs(container_name, blob_prefix)
                for blob in blobs:
                    if blob.endswith("document_content.json"):
                        # Reconstruct the full URL
                        doc_json_cloud_path = f"{blob_storage.account_url}/{container_name}/{blob}"
                        break
        
        if doc_json_cloud_path:
            # Download and load the JSON
            try:
                local_json_path = blob_storage.download_blob_url(
                    doc_json_cloud_path,
                    local_folder=str(local_dir_path)
                )
                
                # Load content from the downloaded JSON
                updated_doc = DocumentContent.load_from_json(local_json_path)
                
                # Update this instance with downloaded data
                for key, value in updated_doc.model_dump().items():
                    setattr(self, key, value)
                
                # Now download all the referenced files
                if self.metadata:
                    # Download PDF file if available
                    if self.metadata.cloud_storage_path:
                        pdf_local_path = blob_storage.download_blob_url(
                            self.metadata.cloud_storage_path,
                            local_folder=str(local_dir_path)
                        )
                        self.metadata.document_path = pdf_local_path
                
                # Download page content
                for page in self.pages:
                    page.download_from_blob(blob_storage, container_name, local_dir_path)
                
                # Download post-processing content
                if self.post_processing_content:
                    self.post_processing_content.download_from_blob(blob_storage, container_name, local_dir_path)
                    
                # Ensure output directory is updated
                self.metadata.output_directory = str(local_dir_path)
                
                return
            
            except Exception as e:
                print(f"Error downloading document_content.json: {e}")
                # Continue with fallback approach if this fails
        
        # 2. Fallback: download files individually
        # Download PDF file if available
        if self.metadata and self.metadata.cloud_storage_path:
            try:
                pdf_local_path = blob_storage.download_blob_url(
                    self.metadata.cloud_storage_path,
                    local_folder=str(local_dir_path)
                )
                self.metadata.document_path = pdf_local_path
                self.metadata.output_directory = str(local_dir_path)
            except Exception as e:
                print(f"Error downloading PDF file: {e}")
        
        # Download page content
        for page in self.pages:
            page.download_from_blob(blob_storage, container_name, local_dir_path)
        
        # Download post-processing content
        if self.post_processing_content:
            self.post_processing_content.download_from_blob(blob_storage, container_name, local_dir_path)
    
    def to_search_units(self, include_post_processing: bool = True) -> List[Dict[str, Any]]:
        """
        Convert document content to search units for indexing
        
        Args:
            include_post_processing: Whether to include post-processing content
            
        Returns:
            List of search units (dictionaries ready for search indexing)
        """
        # This would implement conversion to search units
        # For now, returning empty list as placeholder
        return []
    
    def apply_post_processing(self, config) -> None:
        """
        Run post-processing operations on the document
        
        Args:
            config: Configuration for post-processing
        """
        # This would implement post-processing logic
        # Left as placeholder for now
        pass




