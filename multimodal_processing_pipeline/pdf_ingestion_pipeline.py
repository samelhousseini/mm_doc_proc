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

from multimodal_processing_pipeline.configuration_models import ProcessingPipelineConfiguration


class PDFIngestionPipeline:
    """
    ------------------------------------------------------------------------------------
    This class is responsible for ingesting a PDF and handling all steps such as:
      - Creating the output folder structure
      - Extracting pages as images
      - Extracting text from each page
      - Extracting images/tables using LLM-based methods
      - Combining extracted data
      - Performing post-processing like condensing and table of contents generation
      - Managing the pipeline state to allow resuming if interrupted

    The methods below are grouped into logical sections with detailed comments.
    ------------------------------------------------------------------------------------
    """

    # ========================================================================================
    # =========================  1) INITIALIZATION AND SETUP METHODS  =========================
    # ========================================================================================
    
    def __init__(self, processing_pipeline_config: ProcessingPipelineConfiguration):
        """
        The constructor for PDFIngestionPipeline:
          - Creates a directory "processed" if it doesn't exist
          - Sets up paths, output directory, pipeline state, models, and metadata.
        """
        os.makedirs("processed", exist_ok=True)

        self.pdf_path = Path(processing_pipeline_config.pdf_path)
        # Output directory at the root, not subdirs for text/images/etc.
        self.output_directory = (
            processing_pipeline_config.output_directory
            if processing_pipeline_config.output_directory
            else str(Path("processed") / self.pdf_path.stem)
        )
        self.output_directory = Path(self.output_directory.replace(" ", "_"))
        console.print("Output Directory for processing file: ", self.output_directory)

        self.metadata = None

        self._validate_paths()
        self._prepare_directories()
        self._load_metadata()

        self._mm_model = (
            processing_pipeline_config.multimodal_model
            if processing_pipeline_config.multimodal_model
            else MulitmodalProcessingModelInfo(model_name="gpt-4o")
        )
        self._text_model = (
            processing_pipeline_config.text_model
            if processing_pipeline_config.text_model
            else TextProcessingModelnfo(model_name="gpt-4o")
        )

        self.processing_pipeline_config = processing_pipeline_config
        self.pipeline_state = None  

    def _validate_paths(self):
        """
        Ensures the provided PDF path points to a valid file.
        Raises FileNotFoundError if the file doesn't exist.
        """
        if not self.pdf_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    def _prepare_directories(self):
        """
        Creates the output directory structure:
          - Root output folder
          - Pages folder (for each page's data)
        """
        os.makedirs(self.output_directory, exist_ok=True)
        os.makedirs(self.output_directory / "pages", exist_ok=True)

    def _load_metadata(self):
        """
        Loads essential PDF metadata, including:
          - Document ID
          - Path and filename
          - Total page count
          - Copies the PDF into the output directory
        """
        document_id = self.pdf_path.stem.replace(" ", "_") + "_" + generate_uuid_from_string(str(self.pdf_path))
        with fitz.open(self.pdf_path) as pdf:
            total_pages = pdf.page_count

        console.print(f"[bold blue]Document ID:[/bold blue] {document_id}")

        copied_file_path = copy_file(self.pdf_path, self.output_directory)
        console.print(f"[bold blue]Copying PDF to new directory:[/bold blue] {copied_file_path}")

        self.metadata = PDFMetadata(
            document_id=document_id,
            document_path=convert_path(str(self.pdf_path)),
            filename=convert_path(self.pdf_path.name),
            total_pages=total_pages,
            output_directory=convert_path(str(self.output_directory))
        )

    # ========================================================================================
    # =========================  2) PIPELINE STATE MANAGEMENT METHODS  ========================
    # ========================================================================================

    def _delete_pipeline_state(self) -> None:
        """
        Deletes the existing 'pipeline_state.json' file if present,
        and resets the in-memory pipeline_state to a new blank PipelineState.
        Used typically to restart the pipeline from scratch.
        """
        state_file = self.output_directory / "pipeline_state.json"
        if state_file.is_file():
            console.print("[red]Deleting pipeline state file from disk...[/red]")
            state_file.unlink()  # Remove the file
        
        # Reset pipeline_state in memory
        self.pipeline_state = PipelineState()
        console.print("[yellow]Pipeline state has been reset to default (in-memory).[/yellow]")

    def _load_pipeline_state(self) -> None:
        """
        Loads the pipeline_state from 'pipeline_state.json' if it exists.
        If not found, initializes a blank PipelineState.
        Helps resume processing if it was previously interrupted.
        """
        state_file = self.output_directory / "pipeline_state.json"
        self.pipeline_state = PipelineState.load_from_json(str(state_file))
        console.print("[green]Pipeline state loaded.[/green]")

    def _save_pipeline_state(self) -> None:
        """
        Saves the current pipeline_state to 'pipeline_state.json'
        so progress can be resumed later if needed.
        """
        state_file = self.output_directory / "pipeline_state.json"
        console.print("[blue]Saving pipeline state to disk...[/blue]")
        self.pipeline_state.save_to_json(state_file)

    # ========================================================================================
    # =======================  3) PAGE-LEVEL EXTRACTION/PROCESSING METHODS  ===================
    # ========================================================================================

    def _save_page_as_image(self, page, page_number: int) -> str:
        """
        Renders the given PDF page as a PNG image at:
          pages/page_{page_number}/page_{page_number}.png
        Returns the path to the saved image.
        """
        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)

        page_image_path = page_dir / f"page_{page_number}.png"
        pix = page.get_pixmap(dpi=300)
        pix.save(page_image_path)
        return str(page_image_path)

    def _save_page_as_image_jpg(self, page, page_number: int) -> str:
        """
        Renders the given PDF page as a high-quality JPEG image at:
          pages/page_{page_number}/page_{page_number}.jpg
        Returns the path to the saved image.
        """
        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)

        page_image_path = page_dir / f"page_{page_number}.jpg"
        pix = page.get_pixmap(dpi=300)
        pix.save(page_image_path, output="jpg", jpg_quality=80)
        return str(page_image_path)

    def _extract_text_from_page(self, page, page_number: int, page_image_path: str) -> ExtractedText:
        """
        Extracts raw text from a single PDF page using PyMuPDF's get_text().
        If configured, processes the text with an LLM model for cleanup/refinement.
        Saves the final text to: pages/page_{page_number}/page_{page_number}.txt

        Returns an ExtractedText object containing the text and file references.
        """
        text = page.get_text()

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

    def _extract_images_from_page(self, page_image_path: str, page_number: int) -> List[ExtractedImage]:
        """
        Uses an LLM-based vision method (analyze_images) to detect images 
        in the specified page image file. For each detected image, 
        a text description is stored in pages/page_{page_number}/images.

        Returns a list of ExtractedImage objects containing the textual details.
        """
        images = []
        image_results = analyze_images(page_image_path, model_info=self._mm_model)

        if image_results.detected_visuals:
            # Create each ExtractedImage and save it
            for i, img in enumerate(image_results.detected_visuals):
                full_image_text = (
                    f"{img.visual_description}\n\n"
                    f"{img.contextual_relevance}\n\n"
                    f"{img.analysis}"
                )

                extracted_image = ExtractedImage(
                    page_number=page_number,
                    image_path=convert_path(str(page_image_path)),
                    image_type=img.visual_type,
                    text=DataUnit(
                        text=full_image_text,
                        page_image_path=convert_path(str(page_image_path))
                    )
                )
                
                # Save the image using its built-in method
                extracted_image.save_to_directory(self.output_directory, i)
                images.append(extracted_image)

        console.print("[bold cyan]Extracted Images:[/bold cyan]", images)
        return images

    def _extract_tables_from_page(self, page_image_path: str, page_number: int) -> List[ExtractedTable]:
        """
        Uses an LLM-based function (analyze_tables) to detect tables in the specified 
        page image file. For each detected table, the markdown representation and 
        analysis are stored in pages/page_{page_number}/tables.

        Returns a list of ExtractedTable objects with relevant details.
        """
        tables = []
        table_results = analyze_tables(page_image_path, model_info=self._mm_model)

        if table_results.detected_tables_detailed_markdown:
            # Create each ExtractedTable and save it
            for i, tbl in enumerate(table_results.detected_tables_detailed_markdown):
                full_table_text = (
                    f"{tbl.markdown}\n\n"
                    f"{tbl.contextual_relevance}\n\n"
                    f"{tbl.analysis}"
                )

                extracted_table = ExtractedTable(
                    page_number=page_number,
                    text=DataUnit(
                        text=tbl.markdown,
                        page_image_path=convert_path(str(page_image_path))
                    ),
                    summary=f"{tbl.contextual_relevance}\n\n{tbl.analysis}"
                )
                
                # Save the table using its built-in method
                extracted_table.save_to_directory(self.output_directory, i)
                tables.append(extracted_table)

        console.print("[bold green]Extracted Tables:[/bold green]", tables)
        return tables

    def _combine_page_content(
        self,
        page_number: int,
        extracted_text: ExtractedText,
        page_image_path: str,
        images: List[ExtractedImage],
        tables: List[ExtractedTable]
    ) -> str:
        """
        Combines text, image descriptions, and table markdown into one string block 
        for easier reference. This block is saved as page_{page_number}_twin.txt in 
        the corresponding page directory.
        
        Returns the combined content as a string.
        """
        # Create a PageContent object to use its combine_content method
        page_content = PageContent(
            page_number=page_number,
            text=extracted_text,
            page_image_path=convert_path(page_image_path),
            images=images,
            tables=tables
        )
        
        # Generate combined text using model's built-in method
        combined_str = page_content.combine_content()
        
        # Create DataUnit for the combined content
        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        
        page_text_unit = DataUnit(
            text=combined_str,
            page_image_path=convert_path(page_image_path)
        )
        
        # Save the combined content
        page_text_filename = f"page_{page_number}_twin.txt"
        page_text_unit.save_to_file(page_dir, page_text_filename)
        
        # Update the page content with the combined text
        page_content.page_text = page_text_unit
        
        return combined_str


    def apply_page_processing_steps(self, page_text: str, page_number: int, page_dir: str, page_image_path: str) -> List[DataUnit]:
        """
        Applies custom page processing steps to the page text.
        """
        data_units = []

        custom_proc_dir = page_dir / "custom_processing"
        custom_proc_dir.mkdir(parents=True, exist_ok=True) 

        for step in self.processing_pipeline_config.custom_page_processing_steps:
            if step.data_model is None:
                custom_processed_text_path = custom_proc_dir / f"page_step_{step.name}.txt"
            else:
                custom_processed_text_path = custom_proc_dir /  f"page_step_{step.name}.json"
                
            if page_number not in self.pipeline_state.custom_page_processing:         
                if step.ai_model is None:
                    imgs = [page_image_path]
                elif isinstance(step.ai_model, MulitmodalProcessingModelInfo):
                    imgs = [page_image_path]
                else:
                    imgs = []       

                custom_processed_text = apply_custom_page_processing_prompt(page_text=page_text,
                                                                            custom_page_processing_prompt=step.prompt,
                                                                            response_format=step.data_model,
                                                                            model_info=step.ai_model,
                                                                            imgs = imgs
                                                                        )
                
                # Create DataUnit and save it using model's method
                data_unit = DataUnit(
                    text=custom_processed_text,
                    page_image_path=convert_path(page_image_path)
                )
                data_unit.save_to_file(custom_proc_dir, custom_processed_text_path.name)
                
            else:
                # Load existing data unit
                data_unit = DataUnit.load_from_file(custom_processed_text_path, page_image_path)
            
            data_units.append(data_unit)
        
        self.pipeline_state.custom_page_processing.append(page_number)

        return data_units

    # ========================================================================================
    # =============================  4) LOADING EXTRACTED DATA  ==============================
    # ========================================================================================

    def _load_extracted_text(self, page_number: int, page_image_path: str) -> ExtractedText:
        """
        Loads text that was previously extracted for the specified page 
        from pages/page_{page_number}/page_{page_number}.txt.

        Returns an ExtractedText object with the loaded text.
        """
        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        text_file = page_dir / f"page_{page_number}.txt"
        
        if text_file.is_file():
            return ExtractedText.load_from_file(text_file, page_number, page_image_path)
        else:
            # Return empty ExtractedText if file doesn't exist
            return ExtractedText(
                page_number=page_number,
                text=DataUnit(
                    text="",
                    page_image_path=convert_path(str(page_image_path))
                )
            )

    def _load_extracted_images(self, page_number: int, page_image_path: str) -> List[ExtractedImage]:
        """
        Loads image details (extracted text descriptions) for the specified page 
        from pages/page_{page_number}/images. Filenames follow the pattern:
          page_{page_number}_{visual_type}_{i+1}.txt

        Returns a list of ExtractedImage objects.
        """
        images_dir = self.output_directory / "pages" / f"page_{page_number}" / "images"
        if not images_dir.is_dir():
            return []

        filename_pattern = re.compile(r"^page_(\d+)_(.+)_(\d+)\.txt$")
        images_list: List[ExtractedImage] = []

        for text_file in images_dir.glob(f"page_{page_number}_*_*.txt"):
            match = filename_pattern.match(text_file.name)
            if not match:
                continue

            page_num_str, visual_type_str, idx_str = match.groups()
            # Use the model's load_from_file method
            extracted_image = ExtractedImage.load_from_file(
                text_file, 
                page_number, 
                convert_path(str(page_image_path)),
                visual_type_str
            )
            images_list.append(extracted_image)

        return images_list

    def _load_extracted_tables(self, page_number: int, page_image_path: str) -> List[ExtractedTable]:
        """
        Loads table details for the specified page from pages/page_{page_number}/tables.
        Filenames follow the pattern: page_{page_number}_table_{i+1}.txt

        Returns a list of ExtractedTable objects with the loaded markdown/summaries.
        """
        tables_dir = self.output_directory / "pages" / f"page_{page_number}" / "tables"
        if not tables_dir.is_dir():
            return []

        filename_pattern = re.compile(r"^page_(\d+)_table_(\d+)\.txt$")
        tables_list: List[ExtractedTable] = []

        for tbl_file in tables_dir.glob(f"page_{page_number}_table_*.txt"):
            match = filename_pattern.match(tbl_file.name)
            if not match:
                continue

            # Use the model's load_from_file method
            extracted_table = ExtractedTable.load_from_file(
                tbl_file,
                page_number,
                convert_path(str(page_image_path))
            )
            tables_list.append(extracted_table)

        return tables_list

    def _load_post_processing_files(self, document_content: DocumentContent) -> None:
        """
        Loads any existing post-processing files from the pipeline's output directory
        into document_content.post_processing_content.
        """
        # Use the PostProcessingContent's load_from_directory method
        document_content.post_processing_content = PostProcessingContent.load_from_directory(self.output_directory)
        
        # Load full_text into DocumentContent directly if available
        if document_content.post_processing_content and document_content.post_processing_content.full_text:
            document_content.full_text = document_content.post_processing_content.full_text.text

    # ========================================================================================
    # =============================  5) TRANSLATION METHODS  ==================================
    # ========================================================================================

    def _translate_text(self, document_content: DocumentContent, text: str, lang: str, filename_prefix: str = "full_text") -> str:
        """
        Core helper to translate any given text into a target language using 
        an external function (translate_text). Saves the translation under:
          /translations/{filename_prefix}_{lang}.txt
        """
        console.print(f"Translating {filename_prefix} to: {lang}")
        translate_dir = self.output_directory / "translations" 
        translate_dir.mkdir(parents=True, exist_ok=True)

        # Translate
        translated_text = translate_text(text, lang, model_info=self._text_model)
        
        # Create DataUnit for the translation
        translated_text_unit = DataUnit(
            text=translated_text,
            language=lang
        )
        
        # Save the translation using the DataUnit model's method
        filename = f"{filename_prefix}_{lang}.txt"
        translated_text_unit.save_to_file(translate_dir, filename)
    
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()
        
        if not document_content.post_processing_content.translated_full_texts:
            document_content.post_processing_content.translated_full_texts = []

        document_content.post_processing_content.translated_full_texts.append(translated_text_unit)

    def translate_full_text(self, document_content: DocumentContent):
        """
        Translates the entire document's full text into each language specified 
        in the pipeline configuration. Each translation is saved separately.
        """
        if not self.processing_pipeline_config.translate_full_text:
            return
    
        for lang in self.processing_pipeline_config.translate_full_text:
            self._translate_text(document_content, document_content.full_text, lang, "full_text")

    def translate_condensed_text(self, document_content: DocumentContent):
        """
        Translates the condensed version of the document's text (if generated) into 
        each language specified in the pipeline configuration. 
        Each translation is saved separately.
        """
        if not self.processing_pipeline_config.translate_condensed_text:
            return
    
        for lang in self.processing_pipeline_config.translate_condensed_text:
            self._translate_text(document_content, document_content.post_processing_content.condensed_text.text, lang, "condensed_text")
            

    # ========================================================================================
    # ===============================  6) POST-PROCESSING STEPS  ==============================
    # ========================================================================================

    def _post_processing_steps(self, document: DocumentContent):
        """
        Orchestrates additional steps to be performed once all pages are processed:
          - Save text twin (if configured)
          - Condense text (if configured)
          - Generate table of contents (if configured)
          - Translate the document content (if configured)
        """
        if self.processing_pipeline_config.save_text_files:
            self.save_text_twin(document)

        if self.processing_pipeline_config.generate_condensed_text:
            self.condense_text(document)

        if self.processing_pipeline_config.generate_table_of_contents:
            self.generate_table_of_contents(document)

        if len(self.processing_pipeline_config.custom_document_processing_steps) > 0:
            self.apply_custom_document_processing(document)

        # Translate the document contents
        self.translate_full_text(document)
        self.translate_condensed_text(document)


    def save_text_twin(self, document_content: Optional[DocumentContent] = None):
        """
        Creates a "text twin" by combining all extracted page text, images, and tables
        (which is stored in document_content.full_text). Saves it to text_twin.md.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document

        # Create DataUnit for the full text
        full_text_unit = DataUnit(
            text=document_content.full_text or ""
        )
        
        # Save the full text using the DataUnit model's method
        full_text_path = self.output_directory / "text_twin.md"
        full_text_unit.save_to_file(self.output_directory, "text_twin.md")

        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.full_text = full_text_unit
        console.print(f"Document-level text twin saved at: {full_text_path}")

    def condense_text(self, document_content: Optional[DocumentContent] = None):
        """
        Uses an LLM-based function (condense_text) to produce a shorter summary 
        of the entire document. The condensed text is stored in condensed_text.md.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document
        
        if not document_content.full_text:
            return
        condensed_text_result = condense_text(document_content.full_text, model_info=self._text_model)

        # Create DataUnit for the condensed text
        condensed_text_unit = DataUnit(
            text=condensed_text_result
        )
        
        # Save the condensed text using the DataUnit model's method
        condensed_text_unit.save_to_file(self.output_directory, "condensed_text.md")

        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.condensed_text = condensed_text_unit
        console.print(f"Condensed text saved at: {self.output_directory / 'condensed_text.md'}")

    def generate_table_of_contents(self, document_content: Optional[DocumentContent] = None):
        """
        Calls generate_table_of_contents (LLM-based) to produce a 
        table of contents from the entire document text. 
        The result is stored in table_of_contents.md.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document

        if not document_content.full_text:
            return
        toc_text = generate_table_of_contents(document_content.full_text, model_info=self._text_model)
        toc_text = toc_text.replace("```markdown", "").replace("```", "")

        # Create DataUnit for the table of contents
        toc_unit = DataUnit(
            text=toc_text
        )
        
        # Save the table of contents using the DataUnit model's method
        toc_unit.save_to_file(self.output_directory, "table_of_contents.md")

        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.table_of_contents = toc_unit
        console.print(f"Table of contents saved at: {self.output_directory / 'table_of_contents.md'}")


    def apply_custom_document_processing(self, document_content: Optional[DocumentContent] = None):
        """
        Applies custom document processing to the entire document content.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document

        if not document_content.full_text:
            return
        
        data_units = []

        custom_proc_dir = self.output_directory / "custom_processing"
        custom_proc_dir.mkdir(parents=True, exist_ok=True) 

        for step in self.processing_pipeline_config.custom_document_processing_steps:
            if step.data_model is None:
                filename = f"document_step_{step.name}.txt"
            else:
                filename = f"document_step_{step.name}.json"
            
            # Custom document processing
            custom_processed_text = apply_custom_document_processing_prompt(document_text=document_content.full_text,
                                                                            custom_document_processing_prompt=step.prompt,
                                                                            response_format=step.data_model,
                                                                            model_info=step.ai_model
                                                                        )
            
            # Create DataUnit and save it using the model's method
            data_unit = DataUnit(
                text=custom_processed_text
            )
            data_unit.save_to_file(custom_proc_dir, filename)
            console.print(f"Custom Document Processing saved at: {custom_proc_dir / filename}")

            if not document_content.post_processing_content:
                document_content.post_processing_content = PostProcessingContent()
            
            data_units.append(data_unit)

        document_content.post_processing_content.custom_document_processing_steps = data_units 
        


    def save_document_content_json(self, document_content: Optional[DocumentContent] = None):
        """
        Serializes the entire DocumentContent object to JSON and saves it 
        in document_content.json at the root of the output directory.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document

        # Use the DocumentContent model's save_to_json method
        json_path = document_content.save_to_json(self.output_directory / "document_content.json")
        
        # Ensure document_json is set in post_processing_content
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()
            
        document_content.post_processing_content.document_json = DataUnit(
            text="",  # We don't store the actual content
            text_file_path=json_path
        )
        
        console.print(f"DocumentContent JSON saved at: {json_path}")

    # ========================================================================================
    # =========================  7) PAGE PROCESSING ORCHESTRATION  ===========================
    # ========================================================================================

    def _process_page_with_state(self, page_number: int) -> PageContent:
        """
        Processes a single page (by page_number) using the pipeline state to skip 
        already-completed steps. Extracts text, images, and tables if enabled.
        Combines them into a single text block. Updates the pipeline state accordingly.
        """
        with fitz.open(self.pdf_path) as pdf_document:
            page = pdf_document[page_number - 1]

            # 1) Save the page as an image (png or jpg) 
            if self.processing_pipeline_config.process_pages_as_jpg:
                page_image_path = self._save_page_as_image_jpg(page, page_number)
            else:
                page_image_path = self._save_page_as_image(page, page_number)

            # 2) Extract text if not done
            if page_number not in self.pipeline_state.text_extracted_pages:
                extracted_text = self._extract_text_from_page(page, page_number, page_image_path)
                self.pipeline_state.text_extracted_pages.append(page_number)
            else:
                # Already done, re-load from disk
                extracted_text = self._load_extracted_text(page_number, page_image_path)

            images = []
            tables = []

            # 3) Extract images if not done
            if self.processing_pipeline_config.process_images:
                if page_number not in self.pipeline_state.images_extracted_pages:
                    images = self._extract_images_from_page(page_image_path, page_number)
                    self.pipeline_state.images_extracted_pages.append(page_number)
                else:
                    images = self._load_extracted_images(page_number, page_image_path)

            # 4) Extract tables if not done
            if self.processing_pipeline_config.process_tables:
                if page_number not in self.pipeline_state.tables_extracted_pages:
                    tables = self._extract_tables_from_page(page_image_path, page_number)
                    self.pipeline_state.tables_extracted_pages.append(page_number)
                else:
                    tables = self._load_extracted_tables(page_number, page_image_path)

        # 5) Combine results in a single text block
        combined_str = self._combine_page_content(
            page_number, extracted_text, page_image_path, images, tables
        )

        # Prepare page directory
        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        
        # Get the combined page text DataUnit
        page_text_filename = page_dir / f"page_{page_number}_twin.txt"
        page_text = DataUnit(
            text=combined_str,
            text_file_path=convert_path(str(page_text_filename)),
            page_image_path=convert_path(page_image_path)
        )

        # 6) Custom Page Processing
        page_processing_steps = self.apply_page_processing_steps(combined_str, page_number, page_dir, page_image_path)

        # 7) Create the PageContent object
        page_content = PageContent(
            page_number=page_number,
            text=extracted_text,
            page_image_path=convert_path(page_image_path),
            images=images,
            tables=tables,
            page_text=page_text,
            custom_page_processing_steps=page_processing_steps
        )

        return page_content

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

    # ========================================================================================
    # ========================  8) STATIC LOADING METHODS (LAST RESORT)  ======================
    # ========================================================================================

    @staticmethod
    def load_document_content_from_json(folder_path: Union[str, Path]) -> DocumentContent:
        """
        Loads a DocumentContent instance by reading the JSON file in the root folder:
          {folder_path}/document_content.json
        
        Recommended for consistent re-loading of previously processed results.
        """
        folder_path = Path(folder_path)
        doc_json_path = folder_path / "document_content.json"

        if not doc_json_path.is_file():
            raise FileNotFoundError(
                f"Could not find the JSON file containing DocumentContent at {doc_json_path}"
            )

        # Use the DocumentContent model's load_from_json method
        return DocumentContent.load_from_json(doc_json_path)

    ## IMPORTANT
    ## DO NOT USE THIS FUNCTION UNLESS IT IS A LAST RESORT
    ## IT IS NOT RECOMMENDED TO USE THIS FUNCTION
    ## PLEASE USE load_document_content_from_json INSTEAD
    @staticmethod
    def load_document_content_from_folder(folder_path: Union[str, Path]) -> DocumentContent:
        """
        Rebuilds DocumentContent purely by scanning the directory structure.
        Not recommended if a JSON file was saved. Use load_document_content_from_json instead.
        """
        # Use the DocumentContent model's load_from_directory method 
        return DocumentContent.load_from_directory(folder_path)
