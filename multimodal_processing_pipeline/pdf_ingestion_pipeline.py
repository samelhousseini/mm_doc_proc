import os
import fitz
import shutil
from pathlib import Path
from utils.data_models import (
    PDFMetadata,
    ExtractedText,
    ExtractedImage,
    ExtractedTable,
    PageContent,
    DocumentContent,
    MulitmodalProcessingModelName, 
    TextProcessingModelName
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

    def __init__(self, pdf_path: str, output_directory: str, multimodal_model: MulitmodalProcessingModelName = None, text_model: TextProcessingModelName = None):
        self.pdf_path = Path(pdf_path)
        self.output_directory = Path(output_directory)
        self.metadata = None

        self._validate_paths()
        self._prepare_directories()
        self._load_metadata()

        self._mm_model = multimodal_model if multimodal_model else MulitmodalProcessingModelName(model_name="gpt-4o")
        self._text_model = text_model if text_model else TextProcessingModelName(model_name="gpt-4o")


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
            document_path=self.pdf_path,
            filename=self.pdf_path.name,
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
                    self.output_directory, "images", f"page_{page_number}_image_{i+1}.txt"
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
                        image_path=page_image_path,
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
            page_image_path=page_image_path,
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