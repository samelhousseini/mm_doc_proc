import os
import fitz
import re
from typing import Union, List
import shutil
from collections import defaultdict
from pathlib import Path
import uuid
import json
import sys
sys.path.append('..')


from utils.openai_data_models import (
    MulitmodalProcessingModelInfo, 
    TextProcessingModelnfo,
)
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Union
import content_understanding
   
from multimodal_processing_pipeline.data_models import (
    EmbeddedImages,
    EmbeddedTables,
    EmbeddedImage,
    EmbeddedTable,
    DataUnit,
    PDFMetadata,
    ExtractedText,
    ExtractedImage,
    ExtractedTable,
    PageContent,
    PostProcessingContent,
    DocumentContent,
    PipelineState
)
from multimodal_processing_pipeline.configuration_models import *
from utils.file_utils import *
from multimodal_processing_pipeline.pipeline_utils import (
    analyze_images,
    analyze_tables,
    process_text,
    condense_text,
    generate_table_of_contents,
    translate_text,
    apply_custom_page_processing_prompt,
    apply_custom_document_processing_prompt
)
from utils.text_utils import *
from utils.file_utils import *
from rich.console import Console
console = Console()


from content_understanding.content_analyzer import ContentAnalyzer
from multimodal_processing_pipeline.pdf_ingestion_pipeline import PDFIngestionPipeline


def get_resource_path(package: Union[str, ModuleType], filename: str) -> Path:
    with resources.as_file(resources.files(package) / filename) as fs_path:
        return fs_path




class PDFCUIngestionPipeline(PDFIngestionPipeline):

    def _extract_text_from_page(self, page, page_number: int, page_image_path: str) -> ExtractedText:
        """
        Extracts raw text from a single PDF page using Content Understanding.
        If configured, processes the text with an LLM model for cleanup/refinement.
        Saves the final text to: pages/page_{page_number}/page_{page_number}.txt

        Returns an ExtractedText object containing the text and file references.
        """
        page = self.cu_results[page_number]
        console.print(f">>> Reading in {page}")
        text = read_file(page)[0]

        if self.processing_pipeline_config.process_text:
            console.print("Processing text with GPT...")
            text = process_text(text, page_image_path, model_info=self._mm_model)

        console.print("[bold magenta]Extracted/Processed Text:[/bold magenta]", text)

        # Create ExtractedText object with DataUnit
        extracted_text = ExtractedText(
            page_number=page_number,
            text=DataUnit(
                text=text,
                page_image_path=convert_path(str(page_image_path))
            )
        )
        
        # Use the model's save_to_directory method to save the text to the right location
        extracted_text.save_to_directory(self.output_directory)
        
        return extracted_text


    def process_pages_with_content_understanding(self):
        self.input_file_paths = []
        self.cu_results = {}

        for page_number in range(1, self.metadata.total_pages + 1):
            with fitz.open(self.pdf_path) as pdf_document:
                if page_number not in self.pipeline_state.text_extracted_pages:
                    page = pdf_document[page_number - 1]

                    # 1) Save the page as an image (png or jpg) 
                    if self.processing_pipeline_config.process_pages_as_jpg:
                        page_image_path = self._save_page_as_image_jpg(page, page_number)
                    else:
                        page_image_path = self._save_page_as_image(page, page_number)
                    
                    self.input_file_paths.append(page_image_path)

        try:
            analyzer_id = "cu_page_image_analyzer"
            # Construct absolute path for the schema
            script_dir = get_resource_path(content_understanding, 'analyzer')
            analyzer_schema_path = os.path.join(script_dir, 'analyzer', f"{analyzer_id}.json")

            analyzer = ContentAnalyzer(
                analyzer_id=analyzer_id,
                analyzer_schema_path=analyzer_schema_path
            )

            # Run the analysis process
            success, temp_cu_results = analyzer.run_analysis(
                input_file_paths=self.input_file_paths
            )
        except Exception as e:
            console.print(f"[bold red]Error processing PDF: {e}[/bold red]")
            raise e

        for r in temp_cu_results:
            # Get the page number from the filename
            page_number = int(re.search(r"page_(\d+)", r).group(1))
            print(f"*********** Processing page number {page_number} from file {r}")
            self.cu_results[page_number] = temp_cu_results[r]


    def process_pdf(self) -> DocumentContent:
        """
        Main entry point to process the entire PDF. Iterates over each page:
          - Extracts data (text, images, tables)
          - Combines and saves results
          - Updates pipeline state so we can resume if interrupted
        Then runs post-processing (condensing, table of contents, translations) 
        unless they've already been done, and saves a final JSON representation 
        of the entire DocumentContent.
        
        Returns the DocumentContent object representing the fully processed PDF.
        """
        if not self.processing_pipeline_config.resume_processing_if_interrupted:
            # If the pipeline was interrupted, we can delete the state file to start fresh
            self._delete_pipeline_state()

        # Load or initialize pipeline_state
        self._load_pipeline_state()

        self.process_pages_with_content_understanding()

        pages = []
        for page_number in range(1, self.metadata.total_pages + 1):
            console.print(f"Processing page {page_number}/{self.metadata.total_pages}...")
            page_content = self._process_page_with_state(page_number)
            pages.append(page_content)
            
            # Save pipeline state after each page in case of interruption
            self._save_pipeline_state()

        # Build full_text from all pages
        full_text = "\n".join(
            p.page_text.text for p in pages if p.page_text and p.page_text.text
        )

        self.metadata.processed_pages = len(pages)

        document = DocumentContent(
            metadata=self.metadata,
            pages=pages,
            full_text=full_text
        )

        # Only do post-processing if not done
        if not self.pipeline_state.post_processing_done:
            self._post_processing_steps(document)
            self.pipeline_state.post_processing_done = True
            self._save_pipeline_state()
        else:
            # Load post-processing files if already done
            self._load_post_processing_files(document)

        # Save the entire DocumentContent as JSON in the output root
        self.save_document_content_json(document)

        self.document = document

        return document

  