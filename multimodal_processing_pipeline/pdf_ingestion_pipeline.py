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
    IMPORTANT: Code lines remain exactly the same; only the order of methods has changed
               and additional comments were added. No existing lines were altered.
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
          - Pages folder (for each page’s data)
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
        if state_file.is_file():
            console.print("[green]Loading pipeline state from disk...[/green]")
            data = read_json_file(state_file)
            self.pipeline_state = PipelineState(**data)
        else:
            self.pipeline_state = PipelineState()

    def _save_pipeline_state(self) -> None:
        """
        Saves the current pipeline_state to 'pipeline_state.json'
        so progress can be resumed later if needed.
        """
        state_file = self.output_directory / "pipeline_state.json"
        console.print("[blue]Saving pipeline state to disk...[/blue]")

        # 1) Dump to a Python dict:
        data = self.pipeline_state.model_dump()

        # 2) Convert that dict to JSON with your desired formatting:
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        # 3) Write to disk:
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(json_str)

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

        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)

        text_filename = page_dir / f"page_{page_number}.txt"
        write_to_file(text, text_filename, mode="w")

        extracted_text = ExtractedText(
            page_number=page_number,
            text=DataUnit(
                text=text,
                text_file_path=convert_path(str(text_filename)),
                page_image_path=convert_path(str(page_image_path))
            )
        )
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
            # ensure subfolder: pages/page_{page_number}/images
            images_dir = self.output_directory / "pages" / f"page_{page_number}" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            for i, img in enumerate(image_results.detected_visuals):
                text_filename = images_dir / f"page_{page_number}_{img.visual_type}_{i+1}.txt"
                full_image_text = (
                    f"{img.visual_description}\n\n"
                    f"{img.contextual_relevance}\n\n"
                    f"{img.analysis}"
                )

                write_to_file(full_image_text, text_filename, mode="w")

                extracted_image = ExtractedImage(
                    page_number=page_number,
                    image_path=convert_path(str(page_image_path)),
                    image_type=img.visual_type,
                    text=DataUnit(
                        text=full_image_text,
                        text_file_path=convert_path(str(text_filename)),
                        page_image_path=convert_path(str(page_image_path))
                    )
                )
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
            tables_dir = self.output_directory / "pages" / f"page_{page_number}" / "tables"
            tables_dir.mkdir(parents=True, exist_ok=True)

            for i, tbl in enumerate(table_results.detected_tables_detailed_markdown):
                text_filename = tables_dir / f"page_{page_number}_table_{i+1}.txt"
                full_table_text = (
                    f"{tbl.markdown}\n\n"
                    f"{tbl.contextual_relevance}\n\n"
                    f"{tbl.analysis}"
                )

                write_to_file(full_table_text, text_filename, mode="w")

                extracted_table = ExtractedTable(
                    page_number=page_number,
                    text=DataUnit(
                        text=tbl.markdown,
                        text_file_path=convert_path(str(text_filename)),
                        page_image_path=convert_path(str(page_image_path))
                    ),
                    summary=f"{tbl.contextual_relevance}\n\n{tbl.analysis}"
                )
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
        combined = f"##### --- Page {extracted_text.page_number} ---\n\n"
        combined += "# Extracted Text\n\n"
        if extracted_text.text and extracted_text.text.text:
            combined += f"{extracted_text.text.text}\n\n"

        if images:
            combined += "\n# Embedded Images:\n\n"
            for i, image in enumerate(images):
                combined += f"### - Image {i+1}:\n"
                if image.text and image.text.text:
                    combined += f"{image.text.text}\n\n"

        if tables:
            combined += "\n# Tables:\n\n"
            for i, table in enumerate(tables):
                combined += f"### - Table {i+1}:\n\n"
                if table.text and table.text.text:
                    combined += f"{table.text.text}\n\n"
                if table.summary:
                    combined += f"Summary:\n{table.summary}\n\n"

        combined += (
            f'<br/>\n<br/>\n<img src="{page_image_path}" '
            f'alt="Page Number {page_number}" width="300" height="425">'
        )
        combined += "\n\n\n\n"
        return combined


    def apply_page_processing_steps(self, page_text: str, page_number: int, page_dir: str, page_image_path: str) -> List[DataUnit]:
        # Custom page processing
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
                
                write_to_file(custom_processed_text, custom_processed_text_path, mode="w")        
            else:
                custom_processed_text = read_asset_file(custom_processed_text_path)[0]

            data_units.append(DataUnit(
                text=custom_processed_text,
                text_file_path=convert_path(str(custom_processed_text_path)),
                page_image_path=convert_path(page_image_path)
            ))
        
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
        text_str = text_file.read_text(encoding="utf-8") if text_file.is_file() else ""
        return ExtractedText(
            page_number=page_number,
            text=DataUnit(
                text=text_str,
                text_file_path=convert_path(str(text_file)) if text_file.is_file() else None,
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
            text_for_img = text_file.read_text(encoding="utf-8")

            extracted_image = ExtractedImage(
                page_number=int(page_num_str),
                image_path=convert_path(str(page_image_path)),  # re-use the main page image path
                image_type=visual_type_str,
                text=DataUnit(
                    text=text_for_img,
                    text_file_path=convert_path(str(text_file)),
                    page_image_path=convert_path(str(page_image_path))
                )
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

            page_num_str, table_idx_str = match.groups()
            tbl_content = tbl_file.read_text(encoding="utf-8")

            extracted_table = ExtractedTable(
                page_number=int(page_num_str),
                text=DataUnit(
                    text=tbl_content,
                    text_file_path=convert_path(str(tbl_file)),
                    page_image_path=convert_path(str(page_image_path))
                ),
                summary=None
            )
            tables_list.append(extracted_table)

        return tables_list

    def _load_post_processing_files(self, document_content: DocumentContent) -> None:
        """
        Loads any existing post-processing files from the pipeline’s output directory
        into document_content.post_processing_content. This includes:
          - text_twin.md
          - condensed_text.md
          - table_of_contents.md
          - document_content.json reference
          - translations in /translations
        """
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        # -----------------
        # 1) text_twin.md
        # -----------------
        text_twin_path = self.output_directory / "text_twin.md"
        if text_twin_path.is_file():
            twin_text = text_twin_path.read_text(encoding="utf-8")
            document_content.full_text = twin_text
            document_content.post_processing_content.full_text = DataUnit(
                text=twin_text,
                text_file_path=str(text_twin_path)
            )

        # ----------------------
        # 2) condensed_text.md
        # ----------------------
        condensed_path = self.output_directory / "condensed_text.md"
        if condensed_path.is_file():
            condensed_text = condensed_path.read_text(encoding="utf-8")
            document_content.post_processing_content.condensed_text = DataUnit(
                text=condensed_text,
                text_file_path=str(condensed_path)
            )

        # -------------------------
        # 3) table_of_contents.md
        # -------------------------
        toc_path = self.output_directory / "table_of_contents.md"
        if toc_path.is_file():
            toc_text = toc_path.read_text(encoding="utf-8")
            document_content.post_processing_content.table_of_contents = DataUnit(
                text=toc_text,
                text_file_path=str(toc_path)
            )

        # -------------------------
        # 4) Post-processing steps
        # -------------------------
        for step in self.processing_pipeline_config.custom_document_processing_steps:
            custom_proc_dir = self.output_directory / "custom_processing"

            if step.data_model is None:
                custom_processed_text_path = custom_proc_dir / f"step_{step.name}.txt"
            else:
                custom_processed_text_path = custom_proc_dir /  f"step_{step.name}.json"

            if custom_processed_text_path.is_file():
                custom_document_processing_text = custom_processed_text_path.read_text(encoding="utf-8")
                document_content.post_processing_content.custom_document_page_text = DataUnit(
                    text=custom_document_processing_text,
                    text_file_path=str(custom_processed_text_path)
            )

        # ------------------------------------------------
        # 5) document_content.json (document_json DataUnit)
        # ------------------------------------------------
        doc_json_path = self.output_directory / "document_content.json"
        if doc_json_path.is_file():
            document_content.post_processing_content.document_json = DataUnit(
                text="",  # or store the JSON string if you prefer
                text_file_path=str(doc_json_path)
            )

        # ------------------------------------
        # 6) translations in ./translations/
        # ------------------------------------
        translations_dir = self.output_directory / "translations"
        if translations_dir.is_dir():
            if not document_content.post_processing_content.translated_full_texts:
                document_content.post_processing_content.translated_full_texts = []
            if not document_content.post_processing_content.translated_condensed_texts:
                document_content.post_processing_content.translated_condensed_texts = []

            for file in translations_dir.glob("*.txt"):
                filename = file.name
                file_text = file.read_text(encoding="utf-8")
                # e.g. "full_text_fr.txt" => group(1)="full_text", group(2)="fr"
                m = re.match(r"^(full_text|condensed_text)_(\w+)\\.txt$", filename)
                if m:
                    text_type = m.group(1)  # "full_text" or "condensed_text"
                    lang = m.group(2)      # e.g. "fr"

                    data_unit = DataUnit(
                        text=file_text,
                        language=lang,
                        text_file_path=str(file)
                    )

                    if text_type == "full_text":
                        document_content.post_processing_content.translated_full_texts.append(data_unit)
                    else:
                        document_content.post_processing_content.translated_condensed_texts.append(data_unit)

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
        
        # Save translated text 
        translated_text_filename = translate_dir / f"{filename_prefix}_{lang}.txt"
        write_to_file(translated_text, translated_text_filename, mode="w")
    
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()
        
        if not document_content.post_processing_content.translated_full_texts:
            document_content.post_processing_content.translated_full_texts = []

        document_content.post_processing_content.translated_full_texts.append(DataUnit(
            text=translated_text,
            language=lang,
            text_file_path=convert_path(str(translated_text_filename))
        ))

    def translate_full_text(self, document_content: DocumentContent):
        """
        Translates the entire document’s full text into each language specified 
        in the pipeline configuration. Each translation is saved separately.
        """
        if not self.processing_pipeline_config.translate_full_text:
            return
    
        for lang in self.processing_pipeline_config.translate_full_text:
            self._translate_text(document_content, document_content.full_text, lang, "full_text")

    def translate_condensed_text(self, document_content: DocumentContent):
        """
        Translates the condensed version of the document’s text (if generated) into 
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

        twin_path = self.output_directory / "text_twin.md"
        write_to_file(document_content.full_text or "", twin_path, mode="w")

        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.full_text = DataUnit(
            text=document_content.full_text or "",
            text_file_path=convert_path(str(twin_path))
        )
        console.print(f"Document-level text twin saved at: {twin_path}")

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

        condensed_path = self.output_directory / "condensed_text.md"
        write_to_file(condensed_text_result, condensed_path, mode="w")

        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.condensed_text = DataUnit(
            text=condensed_text_result,
            text_file_path=convert_path(str(condensed_path))
        )
        console.print(f"Condensed text saved at: {condensed_path}")

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

        toc_text_path = self.output_directory / "table_of_contents.md"
        write_to_file(toc_text, toc_text_path, mode="w")

        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.table_of_contents = DataUnit(
            text=toc_text,
            text_file_path=convert_path(str(toc_text_path))
        )
        console.print(f"Table of contents saved at: {toc_text_path}")


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
                custom_processed_text_path = custom_proc_dir / f"document_step_{step.name}.txt"
            else:
                custom_processed_text_path = custom_proc_dir /  f"document_step_{step.name}.json"
            
            # Custom page processing
            custom_processed_text = apply_custom_document_processing_prompt(document_text=document_content.full_text,
                                                                            custom_document_processing_prompt=step.prompt,
                                                                            response_format=step.data_model,
                                                                            model_info=step.ai_model
                                                                        )
            
            write_to_file(custom_processed_text, custom_processed_text_path, mode="w")
            console.print(f"Custom Document Processing saved at: {custom_processed_text_path}")

            if not document_content.post_processing_content:
                document_content.post_processing_content = PostProcessingContent()
            
            data_units.append(DataUnit(
                text=custom_processed_text,
                text_file_path=convert_path(str(custom_processed_text_path))
            ))

        document_content.post_processing_content.custom_document_processing_steps = data_units 
        


    def save_document_content_json(self, document_content: Optional[DocumentContent] = None):
        """
        Serializes the entire DocumentContent object to JSON and saves it 
        in document_content.json at the root of the output directory.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document

        doc_json_path = self.output_directory / "document_content.json"
    
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        document_content.post_processing_content.document_json = DataUnit(
            text="",  # If you prefer to store the actual JSON string, you can do so
            text_file_path=convert_path(str(doc_json_path))
        )

        document_dict = document_content.dict()
        write_json_file(document_dict, doc_json_path)
        console.print(f"DocumentContent JSON saved at: {doc_json_path}")

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

        # Save combined text as page_{page_number}_twin.txt
        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        page_text_filename = page_dir / f"page_{page_number}_twin.txt"
        write_to_file(combined_str, page_text_filename, mode="w")

        # 6) Custom Document Processing
        page_processing_steps = self.apply_page_processing_steps(combined_str, page_number, page_dir, page_image_path)

        # 7) Create the PageContent object
        page_content = PageContent(
            page_number=page_number,
            text=extracted_text,
            page_image_path=convert_path(page_image_path),
            images=images,
            tables=tables,
            page_text=DataUnit(
                text=combined_str,
                text_file_path=convert_path(str(page_text_filename)),
                page_image_path=convert_path(page_image_path)
            ),
            custom_page_processing_steps = page_processing_steps
        )

        return page_content

    def process_pdf(self) -> DocumentContent:
        """
        Main entry point to process the entire PDF. Iterates over each page:
          - Extracts data (text, images, tables)
          - Combines and saves results
          - Updates pipeline state so we can resume if interrupted
        Then runs post-processing (condensing, table of contents, translations) 
        unless they’ve already been done, and saves a final JSON representation 
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
        If a text_twin.md file is found, it also populates the full_text field.
        
        Recommended for consistent re-loading of previously processed results.
        """
        folder_path = Path(folder_path)
        doc_json_path = folder_path / "document_content.json"

        if not doc_json_path.is_file():
            raise FileNotFoundError(
                f"Could not find the JSON file containing DocumentContent at {doc_json_path}"
            )

        document_dict = read_json_file(doc_json_path)
        doc_content = DocumentContent(**document_dict)

        # If there's a text_twin.md, read it into doc_content.full_text
        twin_path = folder_path / "text_twin.md"
        if twin_path.is_file():
            doc_content.full_text = twin_path.read_text(encoding="utf-8")

        return doc_content

    ## IMPORTANT
    ## DO NOT USE THIS FUNCTION UNLESS IT IS A LAST RESORT
    ## IT IS NOT RECOMMENDED TO USE THIS FUNCTION
    ## PLEASE USE load_document_content_from_json INSTEAD
    @staticmethod
    def load_document_content_from_folder(folder_path: Union[str, Path]) -> DocumentContent:
        """
        Rebuilds DocumentContent purely by scanning the directory structure:
          {folder_path}/pages/page_{n}/ ...
        This method re-assembles text, images, tables, and the final combined text 
        for each page, and attempts to guess total pages, etc.

        Not recommended if a JSON file was saved. Use load_document_content_from_json instead.
        """
        folder_path = Path(folder_path)
        pages_dir = folder_path / "pages"

        # Attempt to reconstruct PDFMetadata from partial info
        document_id = folder_path.name
        pdf_fake_path = folder_path / f"{document_id}.pdf"
        page_numbers = []
        for child in pages_dir.iterdir():
            if child.is_dir() and child.name.startswith("page_"):
                match = re.search(r"page_(\d+)$", child.name)
                if match:
                    page_numbers.append(int(match.group(1)))
        page_numbers.sort()

        metadata = PDFMetadata(
            document_id=document_id,
            document_path=convert_path(str(pdf_fake_path)),
            filename=convert_path(pdf_fake_path.name),
            total_pages=len(page_numbers),
            output_directory=convert_path(str(folder_path))
        )

        full_text_path = folder_path / "text_twin.md"
        full_text = None
        if full_text_path.is_file():
            full_text = full_text_path.read_text(encoding="utf-8")

        pages: List[PageContent] = []
        for page_num in page_numbers:
            page_subdir = pages_dir / f"page_{page_num}"
            main_img = page_subdir / f"page_{page_num}.png"
            if not main_img.is_file():
                # Maybe it was saved as jpg
                alt_img = page_subdir / f"page_{page_num}.jpg"
                if alt_img.is_file():
                    main_img = alt_img

            extracted_text_file = page_subdir / f"page_{page_num}.txt"
            extracted_text_str = ""
            if extracted_text_file.is_file():
                extracted_text_str = extracted_text_file.read_text(encoding="utf-8")

            extracted_text = ExtractedText(
                page_number=page_num,
                text=DataUnit(
                    text=extracted_text_str,
                    text_file_path=convert_path(str(extracted_text_file)) if extracted_text_file.is_file() else None,
                    page_image_path=convert_path(str(main_img)) if main_img.is_file() else None
                )
            )

            combined_file = page_subdir / f"page_{page_num}_twin.txt"
            combined_text_str = ""
            if combined_file.is_file():
                combined_text_str = combined_file.read_text(encoding="utf-8")

            images_dir = page_subdir / "images"
            images_list: List[ExtractedImage] = []
            if images_dir.is_dir():
                for img_text_file in images_dir.glob("page_{}_image_*.txt".format(page_num)):
                    text_for_img = img_text_file.read_text(encoding="utf-8")
                    ex_img = ExtractedImage(
                        page_number=page_num,
                        image_path=convert_path(str(main_img)) if main_img.is_file() else "",
                        image_type="unknown",
                        text=DataUnit(
                            text=text_for_img,
                            text_file_path=convert_path(str(img_text_file)),
                            page_image_path=convert_path(str(main_img)) if main_img.is_file() else None
                        )
                    )
                    images_list.append(ex_img)

            tables_dir = page_subdir / "tables"
            tables_list: List[ExtractedTable] = []
            if tables_dir.is_dir():
                for tbl_file in tables_dir.glob("page_{}_table_*.txt".format(page_num)):
                    tbl_content = tbl_file.read_text(encoding="utf-8")
                    ex_tbl = ExtractedTable(
                        page_number=page_num,
                        text=DataUnit(
                            text=tbl_content,
                            text_file_path=convert_path(str(tbl_file)),
                            page_image_path=convert_path(str(main_img)) if main_img.is_file() else None
                        ),
                        summary=None
                    )
                    tables_list.append(ex_tbl)

            page_content = PageContent(
                page_number=page_num,
                text=extracted_text,
                page_image_path=convert_path(str(main_img)) if main_img.is_file() else "",
                images=images_list,
                tables=tables_list,
                page_text=DataUnit(
                    text=combined_text_str,
                    text_file_path=convert_path(str(combined_file)) if combined_file.is_file() else None,
                    page_image_path=convert_path(str(main_img)) if main_img.is_file() else None
                ) if combined_text_str else None
            )

            pages.append(page_content)

        doc_content = DocumentContent(
            metadata=metadata,
            pages=pages,
            full_text=full_text
        )

        return doc_content
