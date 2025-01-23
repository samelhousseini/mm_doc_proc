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

from data_models import (
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
from configuration_models import *
from utils.file_utils import *
from pipeline_utils import (
    analyze_images,
    analyze_tables,
    process_text,
    condense_text,
    generate_table_of_contents,
    translate_text
)
from utils.text_utils import *
from utils.file_utils import *
from rich.console import Console
console = Console()

from configuration_models import ProcessingPipelineConfiguration


class PDFIngestionPipeline:
    """
    Ingests a PDF and saves page images, extracted text, and so on, 
    mirroring the folder structure used by AzureBlobStorage when uploading.
    """

    def __init__(self, processing_pipeline_config: ProcessingPipelineConfiguration):
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


    def _delete_pipeline_state(self) -> None:
        """
        Deletes the existing 'pipeline_state.json' from the output directory,
        and resets the in-memory pipeline_state to a blank PipelineState.
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
        Loads the pipeline_state from 'pipeline_state.json' if it exists;
        otherwise initializes a blank PipelineState.
        """
        state_file = self.output_directory / "pipeline_state.json"
        if state_file.is_file():
            console.print("[green]Loading pipeline state from disk...[/green]")
            data = read_json_file(state_file)
            self.pipeline_state = PipelineState(**data)
        else:
            self.pipeline_state = PipelineState()


    def _save_pipeline_state(self) -> None:
        state_file = self.output_directory / "pipeline_state.json"
        console.print("[blue]Saving pipeline state to disk...[/blue]")

        # 1) Dump to a Python dict:
        data = self.pipeline_state.model_dump()

        # 2) Convert that dict to JSON with your desired formatting:
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        # 3) Write to disk:
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(json_str)


    def _validate_paths(self):
        """Ensure the provided PDF path is valid."""
        if not self.pdf_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    def _prepare_directories(self):
        """
        Create necessary output directories mirroring the structure used in AzureBlobStorage:
        - root output folder
        - pages folder (no separate top-level text/images/tables/combined)
        - doc-level files (text_twin, condensed, etc.) go in root
        - each page's assets go in pages/page_{page_number}/
        """
        os.makedirs(self.output_directory, exist_ok=True)
        os.makedirs(self.output_directory / "pages", exist_ok=True)

    def _load_metadata(self):
        """Load PDF metadata (document ID, total pages, etc.)."""
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

    def _save_page_as_image(self, page, page_number: int) -> str:
        """
        Render the given PDF page as an image (PNG) and save it under:
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
        Render the given PDF page as a high-quality JPEG and save it under:
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
        Extract raw text from a PDF page, process it using GPT (if configured),
        and save to: pages/page_{page_number}/page_{page_number}.txt
        """
        processed_or_raw_text = False
        text = page.get_text()

        if self.processing_pipeline_config.process_text:
            console.print("Processing text with GPT...")
            text = process_text(text, page_image_path, model_info=self._text_model)
            processed_or_raw_text = True

        console.print("[bold magenta]Extracted/Processed Text:[/bold magenta]", text)

        page_dir = self.output_directory / "pages" / f"page_{page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)

        text_filename = page_dir / f"page_{page_number}.txt"
        write_to_file(text, text_filename, mode="w")

        extracted_text = ExtractedText(
            page_number=page_number,
            processed_or_raw_text=processed_or_raw_text,
            text=DataUnit(
                text=text,
                text_file_path=convert_path(str(text_filename)),
                page_image_path=convert_path(str(page_image_path))
            )
        )
        return extracted_text

    def _extract_images_from_page(self, page_image_path: str, page_number: int) -> List[ExtractedImage]:
        """
        Use an LLM-based function to detect/describe embedded images.
        Save each description in:
            pages/page_{page_number}/images/page_{page_number}_image_{i+1}.txt
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
        Use an LLM-based function to detect/describe embedded tables.
        Save each table's description in:
            pages/page_{page_number}/tables/page_{page_number}_table_{i+1}.txt
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
        Combine the page's extracted text, image descriptions, table markdown 
        into one big string block, to be saved as page_{page_number}_twin.txt.
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
    

    def _translate_text(self, document_content: DocumentContent, text: str, lang: str, filename_prefix: str = "full_text") -> str:
        """
        Translate text to a target language using the Azure Text Translation API.
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
        Translate the full text of the document into the languages specified in the configuration.
        """
        if not self.processing_pipeline_config.translate_full_text:
            return
    
        for lang in self.processing_pipeline_config.translate_full_text:
            self._translate_text(document_content, document_content.full_text, lang, "full_text")


    def translate_condensed_text(self, document_content: DocumentContent):
        """
        Translate the condensed text of the document into the languages specified in the configuration.
        """
        if not self.processing_pipeline_config.translate_condensed_text:
            return
    
        for lang in self.processing_pipeline_config.translate_condensed_text:
            self._translate_text(document_content, document_content.post_processing_content.condensed_text.text, lang, "condensed_text")


    def _load_extracted_text(self, page_number: int, page_image_path: str) -> ExtractedText:
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
        Load previously-extracted images (their text) for the given page_number 
        from the local files matching:
            pages/page_{page_number}/images/page_{page_number}_{visual_type}_{i+1}.txt
        """
        images_dir = self.output_directory / "pages" / f"page_{page_number}" / "images"
        if not images_dir.is_dir():
            return []

        # Example filename pattern: "page_3_graph_1.txt" or "page_3_photo_2.txt"
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
        Load previously-extracted tables (their text) for the given page_number
        from the local files matching:
            pages/page_{page_number}/tables/page_{page_number}_table_{i+1}.txt
        """
        tables_dir = self.output_directory / "pages" / f"page_{page_number}" / "tables"
        if not tables_dir.is_dir():
            return []

        # Example filename pattern: "page_4_table_1.txt", "page_4_table_2.txt"
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
                # If you previously stored a combined "analysis" or "summary" in the same file,
                # you could parse it out. Here, we simply store the entire text in data_unit.
                summary=None
            )
            tables_list.append(extracted_table)

        return tables_list


    def _process_page_with_state(self, page_number: int) -> PageContent:
        """
        Checks pipeline_state to see which steps have already been done
        for this page, then only runs the missing steps.
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
                # Already done, re-load from disk or create an ExtractedText placeholder
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
            )
        )

        return page_content

    

    def _post_processing_steps(self, document: DocumentContent):
        """
        Run all post-processing steps (only once) 
        after pages are fully processed.
        """
        # If we want finer granularity (like skip only condense_text if done),
        # we could store separate booleans in pipeline_state. 
        # For brevity, we do them all once if not post_processing_done:
        
        if self.processing_pipeline_config.save_text_files:
            self.save_text_twin(document)

        if self.processing_pipeline_config.generate_condensed_text:
            self.condense_text(document)

        if self.processing_pipeline_config.generate_table_of_contents:
            self.generate_table_of_contents(document)

        # Translate the document contents
        self.translate_full_text(document)
        self.translate_condensed_text(document)




    def process_pdf(self) -> DocumentContent:
        """
        Process the entire PDF, page by page. Optionally performs post-processing steps
        (e.g. text twin, condensed text, table of contents) and saves them in the output root.
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

        # Save the entire DocumentContent as JSON in the output root
        self.save_document_content_json(document)

        self.document = document

        return document

    def save_text_twin(self, document_content: Optional[DocumentContent] = None):
        """
        Generate a doc-level 'text twin' (all pages combined) 
        and save it to text_twin.md in the root output directory.
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
        Condense the entire doc-level text content, storing the result in 
        condensed_text.md in the root output directory.
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
        Generate a table of contents for the doc-level text, store it in 
        table_of_contents.md in the root output directory.
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

    def save_document_content_json(self, document_content: Optional[DocumentContent] = None):
        """
        Serialize the entire DocumentContent to JSON and store in 
        document_content.json at the root of the output directory.
        """
        if not document_content: # If not provided, use the one stored in the instance
            document_content = self.document

        doc_json_path = self.output_directory / "document_content.json"
    
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        # We store the path to the JSON, but not the raw JSON text
        document_content.post_processing_content.document_json = DataUnit(
            text="",  # If you prefer to store the actual JSON string, you can do so
            text_file_path=convert_path(str(doc_json_path))
        )

        document_dict = document_content.dict()
        write_json_file(document_dict, doc_json_path)
        console.print(f"DocumentContent JSON saved at: {doc_json_path}")

    # ----------------------------------------------------------------------
    # Loading methods (unchanged, except we reference pages/page_{n} structure)
    # ----------------------------------------------------------------------
    @staticmethod
    def load_document_content_from_json(folder_path: Union[str, Path]) -> DocumentContent:
        """
        Load a DocumentContent instance by reading the JSON file in the root folder
        (i.e. 'document_content.json').
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
        Rebuild DocumentContent by reading from pages/page_{n} subfolders and root files.
        """
        folder_path = Path(folder_path)
        pages_dir = folder_path / "pages"

        # Attempt to reconstruct PDFMetadata from partial info
        document_id = folder_path.name
        pdf_fake_path = folder_path / f"{document_id}.pdf"
        # We'll gather page_numbers from subfolders named page_X
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

        # Rebuild full_text from text_twin.md if present
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

            # Rebuild combined text from page_{num}_twin.txt
            combined_file = page_subdir / f"page_{page_num}_twin.txt"
            combined_text_str = ""
            if combined_file.is_file():
                combined_text_str = combined_file.read_text(encoding="utf-8")

            # Rebuild images
            images_dir = page_subdir / "images"
            images_list: List[ExtractedImage] = []
            if images_dir.is_dir():
                for img_text_file in images_dir.glob("page_{}_image_*.txt".format(page_num)):
                    text_for_img = img_text_file.read_text(encoding="utf-8")
                    # We store the reference to the main page image (we do not have separate cropped images)
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

            # Rebuild tables
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


