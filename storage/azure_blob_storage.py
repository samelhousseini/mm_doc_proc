import os
import sys
import datetime
import re
from pathlib import Path
from typing import List, Optional
import json
from datetime import datetime, timezone, timedelta

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContainerClient,
    BlobClient,
    generate_blob_sas,
    BlobSasPermissions
)

from pydantic import BaseModel

# Import your existing data models
from data_models import (
    DocumentContent,
    PageContent,
    PDFMetadata,
    ExtractedText,
    ExtractedImage,
    ExtractedTable
)



# The new data models with DataUnit, PostProcessingContent, etc.
from multimodal_processing_pipeline.data_models import (
    DataUnit,
    PostProcessingContent
)

blob_storage_account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")


class AzureBlobStorage:
    """
    Provides high-level methods for interacting with Azure Blob Storage
    while enforcing naming conventions for containers and lightly sanitizing blob names.
    """

    def __init__(self, account_name: str = blob_storage_account_name):
        """
        :param account_name (str): The name of the Azure Storage account.
        """
        self.account_name = account_name
        self.account_url = f"https://{account_name}.blob.core.windows.net"
        self.credential = DefaultAzureCredential()
        self.blob_service_client = BlobServiceClient(
            account_url=self.account_url,
            credential=self.credential
        )

    # --------------------------------------------------------------------------
    # Naming Helpers
    # --------------------------------------------------------------------------
    def _safe_container_name(self, original_name: str) -> str:
        """
        Transform the original container name into a valid Azure container name.
        Rules for container names (summarized from official docs):
          - Must contain only letters, digits, and hyphens.
          - Must start and end with a letter or digit.
          - All letters must be lowercase.
          - No consecutive hyphens allowed.
          - Length must be between 3 and 63 characters.
        Example: "my_container" => "my-container".
        """
        # 1) Convert to lowercase
        name = original_name.lower()

        # 2) Replace underscores with hyphens
        name = name.replace("_", "-")

        # 3) Filter out invalid chars (only [a-z0-9-] are allowed)
        name = re.sub(r"[^a-z0-9-]", "-", name)

        # 4) Remove consecutive hyphens
        name = re.sub(r"-+", "-", name)

        # 5) Ensure starts with letter or digit (trim leading hyphens)
        while len(name) > 0 and name[0] == "-":
            name = name[1:]

        # 6) Ensure ends with letter or digit (trim trailing hyphens)
        while len(name) > 0 and name[-1] == "-":
            name = name[:-1]

        # 7) Ensure minimum length 3
        if len(name) < 3:
            name = (name + "aaa")[:3]

        # 8) Trim to max length 63
        if len(name) > 63:
            name = name[:63]

        return name

    def _safe_blob_name(self, original_name: str) -> str:
        """
        Return a blob name that is valid and recommended by Azure.
        According to docs, a blob name can have many characters, but we do:
         - Trim length to <= 1024
         - Remove control characters (ASCII 0x00 - 0x1F, 0x7F, etc.)
         - Remove trailing dots or slashes or backslashes
         - We do NOT alter underscores, spaces, or non-ASCII letters,
           because blob names can be fairly flexible.
         - The Azure SDK will handle any needed percent-encoding automatically.
        """
        # 1) Remove control characters
        name = re.sub(r"[\x00-\x1F\x7F]", "", original_name)

        # 2) Remove trailing dots/slashes/backslashes
        name = re.sub(r"[./\\]+$", "", name)

        # 3) Enforce max length of 1024
        if len(name) > 1024:
            name = name[:1024]

        if not name:
            name = "unnamed-blob"

        return name

    # --------------------------------------------------------------------------
    # Container Management
    # --------------------------------------------------------------------------
    def create_container(self, container_name: str) -> None:
        """
        Create a new container if it doesn't exist, applying naming rules.
        """
        safe_name = self._safe_container_name(container_name)
        try:
            self.blob_service_client.create_container(safe_name)
        except Exception as ex:
            # e.g. ResourceExistsError if container already exists
            print(f"Warning: Could not create container '{safe_name}': {ex}")

    def delete_container(self, container_name: str) -> None:
        """
        Delete a container if it exists, applying naming rules.
        """
        safe_name = self._safe_container_name(container_name)
        try:
            self.blob_service_client.delete_container(safe_name)
        except Exception as ex:
            print(f"Warning: Could not delete container '{safe_name}': {ex}")

    def list_containers(self) -> List[str]:
        """
        List all containers in this storage account.
        """
        containers = self.blob_service_client.list_containers()
        return [c.name for c in containers]

    # --------------------------------------------------------------------------
    # Blob Operations
    # --------------------------------------------------------------------------
    def upload_blob(
        self,
        container_name: str,
        blob_name: str,
        file_path: str
    ) -> str:
        """
        Upload a single file as a blob, applying safe container name and
        safe blob name transformations.
        Returns the full blob URI.
        """
        safe_container = self._safe_container_name(container_name)
        safe_blob = self._safe_blob_name(blob_name)

        blob_client = self.blob_service_client.get_blob_client(
            container=safe_container, blob=safe_blob
        )
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        # Return the full URI to the uploaded blob
        return f"{self.account_url}/{safe_container}/{safe_blob}"

    def download_blob(
        self,
        container_name: str,
        blob_name: str,
        destination_file_path: str
    ) -> None:
        """
        Download a single blob into the local file system, creating directories as needed.
        """
        safe_container = self._safe_container_name(container_name)
        safe_blob = self._safe_blob_name(blob_name)

        blob_client = self.blob_service_client.get_blob_client(
            container=safe_container, blob=safe_blob
        )
        os.makedirs(os.path.dirname(destination_file_path), exist_ok=True)
        with open(destination_file_path, "wb") as file_data:
            download_stream = blob_client.download_blob()
            file_data.write(download_stream.readall())

    def delete_blob(self, container_name: str, blob_name: str) -> None:
        """
        Delete a specific blob from the container, applying naming rules.
        """
        safe_container = self._safe_container_name(container_name)
        safe_blob = self._safe_blob_name(blob_name)

        blob_client = self.blob_service_client.get_blob_client(
            container=safe_container, blob=safe_blob
        )
        blob_client.delete_blob()

    def list_blobs(self, container_name: str, prefix: Optional[str] = None) -> List[str]:
        """
        List all blobs in a container, with an optional prefix filter.
        """
        safe_container = self._safe_container_name(container_name)
        safe_prefix = self._safe_blob_name(prefix) if prefix else None

        container_client = self.blob_service_client.get_container_client(safe_container)
        blobs = container_client.list_blobs(name_starts_with=safe_prefix)
        return [b.name for b in blobs]

    # --------------------------------------------------------------------------
    # SAS URL Generation
    # --------------------------------------------------------------------------
    def create_sas_url(self, container_name: str, blob_name: str) -> str:
        """
        Generate a full SAS URL for a blob with 7-day duration and
        read/write/delete permissions, applying naming rules.
        """
        safe_container = self._safe_container_name(container_name)
        safe_blob = self._safe_blob_name(blob_name)

        key_start_time = datetime.now(timezone.utc)
        key_expiry_time = key_start_time + timedelta(days=7)
        print(f"Expiry time: {key_expiry_time}")
        user_delegation_key = self.blob_service_client.get_user_delegation_key(
            key_start_time=key_start_time,
            key_expiry_time=key_expiry_time,
        )

        sas_token = generate_blob_sas(
            account_name=self.blob_service_client.account_name,
            container_name=safe_container,
            blob_name=safe_blob,
            credential=self.credential,
            permission=BlobSasPermissions(
                read=True,
                write=True,
                delete=True,
                create=True,
                list=True
            ),
            user_delegation_key=user_delegation_key,
            protocol="https",
            start=key_start_time,
            expiry=key_expiry_time,  # timezone-aware datetime
        )
        return f"{self.account_url}/{safe_container}/{safe_blob}?{sas_token}"

    # --------------------------------------------------------------------------
    # Recursive Folder Upload/Download
    # (Optional if you still want to keep them, not strictly needed for the data model)
    # --------------------------------------------------------------------------
    def upload_folder(
        self,
        local_folder: str,
        container_name: Optional[str] = None
    ) -> None:
        """
        Recursively upload the entire contents of 'local_folder' to the container,
        preserving relative subdirectories in the blob name.
        """
        local_folder_path = Path(local_folder)
        if not container_name:
            container_name = local_folder_path.name

        safe_container = self._safe_container_name(container_name)
        self.create_container(safe_container)

        for root, _, files in os.walk(local_folder_path):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(local_folder_path)
                raw_blob_path = str(relative_path).replace("\\", "/")
                safe_blob_path = self._safe_blob_name(raw_blob_path)
                self.upload_blob(safe_container, safe_blob_path, str(file_path))

    def download_folder(
        self,
        container_name: Optional[str] = None,
        local_folder: Optional[str] = None
    ) -> None:
        """
        Recursively download all blobs in a container, preserving
        subfolder-like structure locally if possible.
        """
        if not container_name:
            raise ValueError("container_name is required for download_folder.")
        if not local_folder:
            local_folder = container_name

        safe_container = self._safe_container_name(container_name)
        local_folder_path = Path(local_folder)
        local_folder_path.mkdir(parents=True, exist_ok=True)

        blob_names = self.list_blobs(safe_container)
        for raw_blob_name in blob_names:
            destination_path = local_folder_path / raw_blob_name
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            # Attempt direct download first:
            try:
                self.download_blob(safe_container, raw_blob_name, str(destination_path))
            except Exception:
                # fallback to sanitized name
                safe_blob_name = self._safe_blob_name(raw_blob_name)
                if raw_blob_name != safe_blob_name:
                    self.download_blob(safe_container, safe_blob_name, str(destination_path))
                else:
                    raise

    # --------------------------------------------------------------------------
    # Helper: Upload a DataUnit
    # --------------------------------------------------------------------------
    def _upload_data_unit(
        self,
        container_name: str,
        data_unit: DataUnit,
        blob_prefix: Optional[str] = None
    ) -> None:
        """
        Uploads the text_file_path (if it exists) and page_image_path (if it exists)
        from this DataUnit into the container. Once uploaded, it updates:
            data_unit.text_file_cloud_storage_path
            data_unit.page_image_cloud_storage_path

        :param container_name: The container to upload into (ALREADY sanitized).
        :param data_unit:      The DataUnit to process.
        :param blob_prefix:    If provided, prefix the blob name with this (e.g. "pages/page_2/...").
                              For post-processing content that must go in the root, pass None or "".
        """
        if not data_unit:
            return

        # 1) Upload the text_file_path if present
        if data_unit.text_file_path and Path(data_unit.text_file_path).is_file():
            file_path = Path(data_unit.text_file_path)
            # If there's a prefix, create "prefix + / + filename"
            if blob_prefix:
                blob_name = f"{blob_prefix}/{file_path.name}"
            else:
                # root of the container
                blob_name = file_path.name

            cloud_uri = self.upload_blob(container_name, blob_name, str(file_path))
            data_unit.text_file_cloud_storage_path = cloud_uri

        # 2) Upload the page_image_path if present
        if data_unit.page_image_path and Path(data_unit.page_image_path).is_file():
            img_path = Path(data_unit.page_image_path)
            if blob_prefix:
                blob_name = f"{blob_prefix}/{img_path.name}"
            else:
                blob_name = img_path.name

            cloud_uri = self.upload_blob(container_name, blob_name, str(img_path))
            data_unit.page_image_cloud_storage_path = cloud_uri

    # --------------------------------------------------------------------------
    # Upload a DocumentContent
    # --------------------------------------------------------------------------
    def upload_document_content(
        self,
        document_content: DocumentContent,
        container_name: Optional[str] = None
    ) -> DocumentContent:
        """
        Creates (or re-uses) a container. Uploads:
          - The original PDF to the root (if it exists).
          - The post_processing_content data units to the root.
          - Each PageContent (images, text, tables) in subfolders.
        Updates the relevant fields in DocumentContent with Azure blob URIs.
        """
        if not container_name:
            # If there's a known output directory, use it to name the container
            if document_content.metadata and document_content.metadata.document_id:
                container_name = document_content.metadata.document_id # Path(document_content.metadata.output_directory).stem
            else:
                container_name = "default-container"

        # Ensure container exists
        safe_container = self._safe_container_name(container_name)
        self.create_container(safe_container)

        # 1) Upload the original PDF file to the root of the container
        pdf_path = Path(document_content.metadata.document_path)
        if pdf_path.is_file():
            blob_name = pdf_path.name  # store in root
            cloud_uri = self.upload_blob(safe_container, blob_name, str(pdf_path))
            document_content.metadata.cloud_storage_path = cloud_uri

        # 2) If post_processing_content is present, upload each DataUnit in the root
        if document_content.post_processing_content:
            self._upload_post_processing_content(document_content.post_processing_content, safe_container)

        # 3) Upload each page
        for page in document_content.pages:
            self._upload_page_content_impl(page, safe_container)

        self.save_and_upload_document_content_json(document_content, 
                                                   doc_json_path=document_content.post_processing_content.document_json.text_file_path,
                                                   container_name=safe_container)

        return document_content


    def save_and_upload_document_content_json(
        self,
        document_content: DocumentContent,
        doc_json_path: Optional[str] = None,
        local_folder: Optional[str] = None,
        container_name: Optional[str] = None
    ) -> DocumentContent:
        """
        Saves the entire DocumentContent to a local JSON file (document_content.json),
        uploads it to the root of the given Azure container, and updates the
        post_processing_content with the resulting cloud URI.
        
        :param document_content:  The DocumentContent object to serialize.
        :param local_folder:      The local folder path where the JSON file will be saved.
        :param container_name:    The Azure container name. If not provided, uses the
                                document_id from metadata or 'default-container'.
        :return:                  The updated DocumentContent with cloud_storage_path
                                pointing to the newly uploaded JSON.
        """
        if not container_name:
            if document_content.metadata and document_content.metadata.document_id:
                container_name = document_content.metadata.document_id
            else:
                container_name = "default-container"

        if not doc_json_path:       
            if not local_folder:
                # Ensure the local folder exists
                Path(local_folder).mkdir(parents=True, exist_ok=True)
            else:
                local_folder = document_content.metadata.output_directory

            # Prepare local JSON path
            doc_json_path = Path(local_folder) / "document_content.json"

        # Serialize to JSON
        doc_dict = document_content.dict()
        with open(doc_json_path, "w", encoding="utf-8") as f:
            json.dump(doc_dict, f, indent=4, ensure_ascii=False)

        print(f"Saved DocumentContent to: {doc_json_path}")

        # Upload the file (blob will be called "document_content.json" at container root)
        cloud_uri = self.upload_blob(container_name, "document_content.json", str(doc_json_path))

        # Ensure post_processing_content.document_json is set
        if not document_content.post_processing_content:
            document_content.post_processing_content = PostProcessingContent()

        if not document_content.post_processing_content.document_json:
            document_content.post_processing_content.document_json = DataUnit(text="")

        document_content.post_processing_content.document_json.text_file_cloud_storage_path = cloud_uri

        return document_content



    def _upload_post_processing_content(
        self,
        post_proc: PostProcessingContent,
        container_name: str
    ) -> None:
        """
        Upload each DataUnit from the PostProcessingContent **in the root** of the container.
        """
        # Each of these is an optional DataUnit. We must upload them if they exist.
        if post_proc.condensed_text:
            self._upload_data_unit(container_name, post_proc.condensed_text, blob_prefix=None)

        if post_proc.table_of_contents:
            self._upload_data_unit(container_name, post_proc.table_of_contents, blob_prefix=None)

        if post_proc.full_text:
            self._upload_data_unit(container_name, post_proc.full_text, blob_prefix=None)

        if post_proc.document_json:
            self._upload_data_unit(container_name, post_proc.document_json, blob_prefix=None)

    # --------------------------------------------------------------------------
    # Upload a single PageContent
    # --------------------------------------------------------------------------
    def upload_page_content(
        self,
        page_content: PageContent,
        container_name: Optional[str] = None,
        document_path: Optional[str] = None
    ) -> PageContent:
        """
        Upload images, text, tables from a single PageContent into the container.
        If container_name is None, we derive from document_path or fallback to 'default-container'.
        """
        if not container_name:
            if document_path:
                container_name = Path(document_path).stem
            else:
                container_name = "default-container"

        safe_container = self._safe_container_name(container_name)
        self.create_container(safe_container)

        self._upload_page_content_impl(page_content, safe_container)
        return page_content

    def _upload_page_content_impl(self, page_content: PageContent, container_name: str) -> None:
        """
        Internal logic to upload the main page image, the combined page_text DataUnit,
        and each ExtractedText, ExtractedImage, ExtractedTable.
        """
        page_prefix = f"pages/page_{page_content.page_number}"

        # 1) Upload the main page image (page_image_path)
        main_img_path = Path(page_content.page_image_path)
        if main_img_path.is_file():
            # We'll store it under e.g. "pages/page_2/page_2.png"
            blob_name = f"{page_prefix}/{main_img_path.name}"
            cloud_uri = self.upload_blob(container_name, blob_name, str(main_img_path))
            # Overwrite the local path with the cloud URL:
            page_content.page_image_cloud_storage_path = cloud_uri

        # 2) Upload the combined page_text (DataUnit)
        if page_content.page_text:
            self._upload_data_unit(container_name, page_content.page_text, blob_prefix=page_prefix)

        # 3) Upload the extracted text (ExtractedText -> DataUnit)
        if page_content.text and page_content.text.text:
            # The DataUnit is in page_content.text.text
            self._upload_data_unit(container_name, page_content.text.text, blob_prefix=page_prefix)

        # 4) Upload images from 'images' list
        for i, img in enumerate(page_content.images):
            local_img_path = Path(img.image_path)
            if local_img_path.is_file():
                blob_name = f"{page_prefix}/images/{local_img_path.name}"
                cloud_uri = self.upload_blob(container_name, blob_name, str(local_img_path))
                # Overwrite local path with cloud URI
                img.image_path = cloud_uri

            # If there's a DataUnit for the text describing this image, upload it
            if img.text:
                self._upload_data_unit(container_name, img.text, blob_prefix=f"{page_prefix}/images")

        # 5) Upload tables from 'tables' list
        for i, tbl in enumerate(page_content.tables):
            if tbl.text:
                # We only have a text DataUnit (markdown, etc.)
                self._upload_data_unit(container_name, tbl.text, blob_prefix=f"{page_prefix}/tables")
