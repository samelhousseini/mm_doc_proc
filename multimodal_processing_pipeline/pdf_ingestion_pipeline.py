import os
import fitz
import re
from typing import Union, List
import shutil
from collections import defaultdict
from pathlib import Path

import sys
sys.path.append('..')


from utils.data_models import (
    PDFMetadata,
    ExtractedText,
    ExtractedImage,
    ExtractedTable,
    PageContent,
    DocumentContent,
    MulitmodalProcessingModelInfo, 
    TextProcessingModelnfo,
    DataUnit
)
from utils.file_utils import (
    write_to_file,
    read_asset_file,
    replace_extension,
    save_to_pickle
)
from utils.pipeline_utils import *
from utils.text_utils import clean_up_text

from rich.console import Console
console = Console()



class PDFIngestionPipeline:

    def __init__(self, pdf_path: str, output_directory: str, multimodal_model: MulitmodalProcessingModelInfo = None, text_model: TextProcessingModelnfo = None):
        self.pdf_path = Path(pdf_path)
        self.output_directory = Path(output_directory)
        self.metadata = None

        self._validate_paths()
        self._prepare_directories()
        self._load_metadata()

        self._mm_model = multimodal_model if multimodal_model else MulitmodalProcessingModelInfo(model_name="gpt-4o")
        self._text_model = text_model if text_model else TextProcessingModelnfo(model_name="gpt-4o")


    def _validate_paths(self):
        """Ensure the provided PDF path is valid."""
        if not self.pdf_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    def _prepare_directories(self):
        """Create necessary output subdirectories if they do not exist."""
        os.makedirs(self.output_directory / "text", exist_ok=True)
        os.makedirs(self.output_directory / "images", exist_ok=True)
        os.makedirs(self.output_directory / "tables", exist_ok=True)
        os.makedirs(self.output_directory / "combined", exist_ok=True)

    def _load_metadata(self):
        """Load PDF metadata (document ID, total pages, etc.)."""
        document_id = self.pdf_path.stem.replace(" ", "_")
        total_pages = fitz.open(self.pdf_path).page_count
        self.metadata = PDFMetadata(
            document_id=document_id,
            document_path=str(self.pdf_path),
            filename=str(self.pdf_path.name),
            total_pages=total_pages,
            output_directory=self.output_directory
        )

    def _save_page_as_image(self, page, page_number: int) -> str:
        """
        Render the given PDF page as an image (PNG) and save it to disk.

        Returns the path to the saved image.
        """
        page_image_path = os.path.join(
            self.output_directory, "images", f"page_{page_number}.png"
        )
        pix = page.get_pixmap(dpi=300)
        pix.save(page_image_path)
        return page_image_path

    def _extract_text_from_page(self, page, page_number: int) -> ExtractedText:
        """
        Extract raw text from a PDF page, process it using a GPT prompt,
        and return an ExtractedText object.
        """
        raw_text = page.get_text()
        processed_text = process_text(raw_text, model_info=self._text_model)
        console.print("[bold magenta]Extracted Processed Text:[/bold magenta]", processed_text)
        text_filename = os.path.join(self.output_directory, "text", f"page_{page_number}.txt")
        write_to_file(processed_text, text_filename, mode="w")

        return ExtractedText(
            page_number=page_number,
            text=raw_text,
            processed_text=processed_text
        )

    def _extract_images_from_page(
        self, page_image_path: str, page_number: int
    ) -> list[ExtractedImage]:
        """
        Use a GPT-based function (analyze_images) to detect embedded images
        and return a list of ExtractedImage objects.
        """
        images = []
        image_results = analyze_images(page_image_path, model_info=self._mm_model)

        if image_results.detected_graphs_or_photos:
            for i, img in enumerate(image_results.detected_graphs_or_photos):
                text_filename = os.path.join(
                    self.output_directory, "images", f"page_{page_number}_{img.image_type}_{i+1}.txt"
                )

                full_image = (
                    f"{img.graph_or_photo_explanation}\n\n"
                    f"{img.contextual_relevance}\n\n"
                    f"{img.analysis}"
                )

                write_to_file(full_image, text_filename, mode="w")

                # NOTE: 'img.type' replaced with 'img.type' -> or 'img.type' if it's named differently
                # If the data model has 'type' as the literal field, rename accordingly
                images.append(
                    ExtractedImage(
                        page_number=page_number,
                        image_path=str(page_image_path),
                        image_type=img.image_type,  # or 'img.type'
                        description=full_image
                    )
                )

        console.print("[bold cyan]Extracted Images:[/bold cyan]", images)
        return images

    def _extract_tables_from_page(
        self, page_image_path: str, page_number: int
    ) -> list[ExtractedTable]:
        """
        Use a GPT-based function (analyze_tables) to detect embedded tables
        and return a list of ExtractedTable objects.
        """
        tables = []
        table_results = analyze_tables(page_image_path, model_info=self._mm_model)

        if table_results.detected_tables_detailed_markdown:
            for i, tbl in enumerate(table_results.detected_tables_detailed_markdown):
                text_filename = os.path.join(
                    self.output_directory, "tables", f"page_{page_number}_table_{i+1}.txt"
                )

                full_table = f"{tbl.markdown}\n\n{tbl.contextual_relevance}\n\n{tbl.analysis}"
                write_to_file(full_table, text_filename, mode="w")

                tables.append(
                    ExtractedTable(
                        page_number=page_number,
                        table_content=tbl.markdown,
                        summary=f"{tbl.contextual_relevance}\n\n{tbl.analysis}"
                    )
                )

        console.print("[bold green]Extracted Tables:[/bold green]", tables)
        return tables

    def _combine_page_content(
        self,
        page_number: int,
        extracted_text: ExtractedText,
        page_image_path: Path,
        images: list[ExtractedImage],
        tables: list[ExtractedTable]
    ) -> str:
        """
        Combine extracted text, images, and table content into a single string block
        that can be saved or returned.
        """
        combined = f"##### --- Page {extracted_text.page_number} ---\n\n"
        combined += f"# Extracted Text\n\n{extracted_text.processed_text}\n\n"

        if images:
            combined += "\n# Embedded Images:\n\n"
            for i, image in enumerate(images):
                combined += f"### - Image {i}:\n{image.description}\n\n"

        if tables:
            combined += "\n# Tables:\n\n"
            for i, table in enumerate(tables):
                combined += f"### - Table {i}:\n\n{table.table_content}\n\n"

        combined += f'<br/>\n<br/>\n<img src="{page_image_path}" alt="Page Number {page_number}" width="300" height="425">'
        combined += "\n\n\n\n"
        return combined

    def _process_page(self, page_number: int) -> PageContent:
        """
        Orchestrates the entire workflow for a single PDF page:
        1) Load the page and save it as an image
        2) Extract + process text
        3) Extract images
        4) Extract tables
        5) Combine results
        6) Return a PageContent object
        """

        # Load page from PDF
        with fitz.open(self.pdf_path) as pdf_document:
            page = pdf_document[page_number - 1]

            # Step 1: Save the page as an image
            page_image_path = self._save_page_as_image(page, page_number)

            # Step 2: Extract + process text
            extracted_text = self._extract_text_from_page(page, page_number)

            # Step 3: Extract images
            images = self._extract_images_from_page(page_image_path, page_number)

            # Step 4: Extract tables
            tables = self._extract_tables_from_page(page_image_path, page_number)

        # Step 5: Combine results
        combined_text = self._combine_page_content(page_number, extracted_text, page_image_path, images, tables)

        # Step 6: Create and return PageContent
        page_content = PageContent(
            page_number=page_number,
            raw_text=extracted_text,
            page_image_path=str(page_image_path),
            images=images,
            tables=tables,
            combined_text=combined_text
        )
        return page_content

    def process_pdf(self) -> DocumentContent:
        """
        Process the entire PDF, page by page, collecting text, images, and tables.
        Returns a DocumentContent that captures all content and metadata.
        """
        pages = []
        for page_number in range(1, self.metadata.total_pages + 1):
            print(f"Processing page {page_number}/{self.metadata.total_pages}...")
            page_content = self._process_page(page_number)
            pages.append(page_content)

        # Build full_text from all pages
        full_text = "\n".join([p.combined_text for p in pages])

        return DocumentContent(
            metadata=self.metadata,
            pages=pages,
            full_text=full_text
        )

    def save_text_twin(self, document_content: DocumentContent):
        """
        Generate a 'text twin' of the entire document content, saving it to disk.
        """
        twin_path = os.path.join(self.output_directory, "combined", "text_twin.md")
        write_to_file(document_content.full_text, twin_path, mode="w")
        print(f"Text twin saved at: {twin_path}")

    def save_page_text_twin(self, page_content: PageContent):
        """
        Generate a 'text twin' of a single page's content, saving it to disk.
        """
        twin_path = os.path.join(
            self.output_directory, "combined", f"page_{page_content.page_number}_twin.txt"
        )
        write_to_file(page_content.combined_text, twin_path, mode="w")
        print(f"Page {page_content.page_number} text twin saved at: {twin_path}")


    def condense_text(self, document_content: DocumentContent):
        """
        Condense the full text content by removing unnecessary whitespace and newlines.
        """
        condensed_text = condense_text(document_content.full_text, model_info=self._text_model)
        document_content.condensed_full_text = condensed_text

        condensed_path = os.path.join(self.output_directory, "combined", "condensed_text.md")
        write_to_file(condensed_text, condensed_path, mode="w")
        print(f"Condensed text saved at: {condensed_path}")


    def condense_page_text(self, page_content: PageContent):
        """
        Condense a single page's text content by removing unnecessary whitespace and newlines.
        """
        condensed_text = condense_text(page_content.combined_text, model_info=self._text_model)
        page_content.condensed_text = condensed_text

        condensed_path = os.path.join(self.output_directory, "combined", f"page_{page_content.page_number}_condensed.md")
        write_to_file(condensed_text, condensed_path, mode="w")
        print(f"Page {page_content.page_number} condensed text saved at: {condensed_path}")


    @staticmethod
    def load_document_content_from_folder(folder_path: Union[str, Path]) -> DocumentContent:
        """
        Reconstruct a DocumentContent instance by reading the subfolders/files
        created during PDF ingestion (text/, images/, tables/, combined/, etc.).
        
        This version parses the new filename pattern for images:
          'page_{page_number}_{image_type}_{i+1}.txt'
        to preserve the actual image_type (e.g., 'graph' or 'photo') in ExtractedImage.
        
        :param folder_path: The path to the parent folder containing the
                            'text', 'images', 'tables', 'combined' subfolders.
        :return: A DocumentContent instance with metadata and pages re-populated.
        """
        folder_path = Path(folder_path)

        # -----------------------------
        # 1) Identify existing page nums
        # -----------------------------
        text_dir = folder_path / "text"
        text_files = sorted(text_dir.glob("page_*.txt"))

        # "page_1.txt" -> page=1, etc.
        page_numbers = []
        for tf in text_files:
            match = re.search(r"page_(\d+)\.txt", tf.name)
            if match:
                page_numbers.append(int(match.group(1)))
        page_numbers.sort()

        # ------------------------------
        # 2) Reconstruct top-level metadata
        # ------------------------------
        # If you stored real metadata, load that instead. For now, we approximate:
        document_id = folder_path.name  # or parse from a known metadata file
        total_pages = len(page_numbers)
        pdf_fake_path = folder_path / f"{document_id}.pdf"  # fallback guess
        metadata = PDFMetadata(
            document_id=document_id,
            document_path=pdf_fake_path,
            filename=pdf_fake_path.name,
            total_pages=total_pages,
            output_directory=folder_path
        )

        # --------------------------------------------------
        # 3) Read the "text_twin.md" and "condensed_text.md"
        # --------------------------------------------------
        combined_dir = folder_path / "combined"
        full_text_path = combined_dir / "text_twin.md"
        condensed_text_path = combined_dir / "condensed_text.md"

        full_text = full_text_path.read_text(encoding="utf-8") if full_text_path.is_file() else None
        condensed_full_text = condensed_text_path.read_text(encoding="utf-8") if condensed_text_path.is_file() else None

        # -----------------------------------------
        # 4) Collect info for embedded IMAGES & PAGE PNG
        # -----------------------------------------
        images_dir = folder_path / "images"
        # We'll parse filenames like "page_2_photo_1.txt", "page_3_graph_2.txt", etc.
        # Then group them by (page_number) so we can attach them later to each PageContent.
        page_to_images = defaultdict(list)

        for img_desc_file in images_dir.glob("page_*_*.txt"):
            # e.g. "page_3_graph_1.txt" => page_num=3, image_type='graph', i=1
            match = re.match(r"page_(\d+)_(\w+)_(\d+)\.txt", img_desc_file.name)
            if not match:
                continue
            page_num_str, image_type_str, idx_str = match.groups()
            page_num = int(page_num_str)

            description = img_desc_file.read_text(encoding="utf-8")

            # The main page image is presumably "page_{page_num}.png"
            page_image_path = images_dir / f"page_{page_num}.png"
            if not page_image_path.is_file():
                # Possibly it doesn't exist; we'll just store an empty Path
                page_image_path = Path("")

            extracted_image = ExtractedImage(
                page_number=page_num,
                image_path=str(page_image_path),
                image_type=image_type_str,      # from filename
                description=description
            )
            page_to_images[page_num].append(extracted_image)

        # --------------------------------------
        # 5) Collect info for TABLES (unchanged)
        # --------------------------------------
        tables_dir = folder_path / "tables"
        # We'll keep the old naming scheme: "page_{n}_table_{i}.txt"
        page_to_tables = defaultdict(list)

        for tbl_file in tables_dir.glob("page_*_table_*.txt"):
            match = re.match(r"page_(\d+)_table_(\d+)\.txt", tbl_file.name)
            if not match:
                continue
            page_num_str, tbl_idx_str = match.groups()
            page_num = int(page_num_str)

            table_text = tbl_file.read_text(encoding="utf-8")
            # The pipeline lumps everything (markdown + summary) into one text file,
            # so we store it all in table_content
            extracted_table = ExtractedTable(
                page_number=page_num,
                table_content=table_text,
                summary=None
            )
            page_to_tables[page_num].append(extracted_table)

        # --------------------------------------------
        # 6) Now reconstruct each PageContent
        # --------------------------------------------
        pages: List[PageContent] = []

        for page_num in page_numbers:
            # Processed text from "text/page_{page_num}.txt"
            processed_text_file = text_dir / f"page_{page_num}.txt"
            processed_text = processed_text_file.read_text(encoding="utf-8") if processed_text_file.is_file() else None

            # Rebuild the "raw_text" (we only have processed text, so raw_text=None)
            extracted_text = ExtractedText(
                page_number=page_num,
                text=None,  
                processed_text=processed_text
            )

            # The main page image: "images/page_{page_num}.png"
            page_image_path = images_dir / f"page_{page_num}.png"
            if not page_image_path.is_file():
                page_image_path = Path("")

            # Grab the images & tables from our dictionaries
            images_for_page = page_to_images.get(page_num, [])
            tables_for_page = page_to_tables.get(page_num, [])

            # Combined text: "combined/page_{page_num}_twin.txt"
            combined_file = combined_dir / f"page_{page_num}_twin.txt"
            combined_text = combined_file.read_text(encoding="utf-8") if combined_file.is_file() else None

            # Condensed text: "combined/page_{page_num}_condensed.md"
            condensed_file = combined_dir / f"page_{page_num}_condensed.md"
            condensed_text = condensed_file.read_text(encoding="utf-8") if condensed_file.is_file() else None

            page_content = PageContent(
                page_number=page_num,
                raw_text=extracted_text,
                page_image_path=str(page_image_path),
                images=images_for_page,
                tables=tables_for_page,
                combined_text=combined_text,
                condensed_text=condensed_text
            )
            pages.append(page_content)

        # -------------------------------------------------
        # 7) Build final DocumentContent and return it
        # -------------------------------------------------
        doc_content = DocumentContent(
            metadata=metadata,
            pages=pages,
            full_text=full_text,
            condensed_full_text=condensed_full_text
        )

        return doc_content


    @staticmethod
    def document_content_to_data_units(doc_content: DocumentContent) -> List[DataUnit]:
        """
        Given a DocumentContent, generate a list of DataUnit entries.
        
        Rules:
          - For each page, create one DataUnit containing the page's processed_text.
          - For each image on that page, create a DataUnit with the image's description.
          - For each table on that page, create a DataUnit with the table's content.
        """
        data_units: List[DataUnit] = []

        # Metadata is the same for the entire DocumentContent
        metadata = doc_content.metadata

        for page in doc_content.pages:
            # 1) The main text unit (processed_text from raw_text)
            page_text = page.raw_text.processed_text or ""
            if page_text.strip():
                data_units.append(
                    DataUnit(
                        metadata=metadata,
                        page_number=page.page_number,
                        page_image_path=str(page.page_image_path),
                        unit_type="text",
                        text=page_text,
                        # e.g. text_vector or condensed_text_vector if you like
                        text_vector=None
                    )
                )

            # 2) Each image's description
            for image in page.images:
                if image.description and image.description.strip():
                    data_units.append(
                        DataUnit(
                            metadata=metadata,
                            page_number=page.page_number,
                            page_image_path=str(image.image_path),
                            unit_type="image",
                            text=image.description,
                            text_vector=None
                        )
                    )

            # 3) Each table's content
            for table in page.tables:
                # Combine table_content & summary if desired, or just use table_content
                table_text = table.table_content or ""
                if table_text.strip():
                    data_units.append(
                        DataUnit(
                            metadata=metadata,
                            page_number=page.page_number,
                            page_image_path=str(page.page_image_path),
                            unit_type="table",
                            text=table_text,
                            text_vector=None
                        )
                    )

        return data_units

    @staticmethod
    def load_data_units_from_folder(folder_path: Union[str, Path]) -> List[DataUnit]:
        """
        Load a DocumentContent from the given folder path, then convert it into DataUnits
        by calling 'document_content_to_data_units'.
        """
        # 1) Reconstruct the DocumentContent using the pipeline's loader method
        doc_content = PDFIngestionPipeline.load_document_content_from_folder(folder_path)

        # 2) Convert to DataUnits
        data_units = PDFIngestionPipeline.document_content_to_data_units(doc_content)
        return data_units
