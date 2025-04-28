import requests
from requests.models import Response
import logging
import json
import time
from pathlib import Path
import os
from concurrent.futures import ThreadPoolExecutor
import pandas as pd # Added pandas import


class AzureContentUnderstandingClient:
    def __init__(
            self,
            endpoint: str,
            api_version: str,
            subscription_key: str = None,
            api_token: str = None,
    ):
        if not subscription_key and not api_token:
            raise ValueError(
                "Either subscription key or API token must be provided.")
        if not api_version:
            raise ValueError("API version must be provided.")
        if not endpoint:
            raise ValueError("Endpoint must be provided.")

        self._subscription_key = subscription_key
        self._endpoint = endpoint.rstrip("/")
        self._api_version = api_version
        self._headers = ({
            "Ocp-Apim-Subscription-Key": self._subscription_key
        } if self._subscription_key else {
            "Authorization": f"Bearer {api_token}"
        })
        self._logger = logging.getLogger(__name__)

    def _get_analyzer_url(self, endpoint, api_version, analyzer_id):
        return f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}?api-version={api_version}"  # noqa

    def _get_analyzer_list_url(self, endpoint, api_version):
        return f"{endpoint}/contentunderstanding/analyzers?api-version={api_version}"

    def _get_analyze_url(self, endpoint, api_version, analyzer_id):
        return f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}:analyze?api-version={api_version}"  # noqa

    def _get_training_data_config(self, storage_container_sas_url,
                                  storage_container_path_prefix):
        return {
            "containerUrl": storage_container_sas_url,
            "kind": "blob",
            "prefix": storage_container_path_prefix,
        }

    def get_all_analyzers(self):
        """
        Retrieves a list of all available analyzers from the content understanding service.

        This method sends a GET request to the service endpoint to fetch the list of analyzers.
        It raises an HTTPError if the request fails.

        Returns:
            dict: A dictionary containing the JSON response from the service, which includes
                  the list of available analyzers.

        Raises:
            requests.exceptions.HTTPError: If the HTTP request returned an unsuccessful status code.
        """
        response = requests.get(
            url=self._get_analyzer_list_url(self._endpoint, self._api_version),
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    def get_analyzer_detail_by_id(self, analyzer_id):
        """
        Retrieves a specific analyzer detail through analyzerid from the content understanding service.
        This method sends a GET request to the service endpoint to get the analyzer detail.

        Args:
            analyzer_id (str): The unique identifier for the analyzer.

        Returns:
            dict: A dictionary containing the JSON response from the service, which includes the target analyzer detail.

        Raises:
            HTTPError: If the request fails.
        """
        response = requests.get(
            url=self._get_analyzer_url(self._endpoint, self._api_version,
                                       analyzer_id),
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    def begin_create_analyzer(
            self,
            analyzer_id: str,
            analyzer_schema: dict = None,
            analyzer_schema_path: str = "",
            training_storage_container_sas_url: str = "",
            training_storage_container_path_prefix: str = "",
    ):
        """
        Initiates the creation of an analyzer with the given ID and schema.

        Args:
            analyzer_id (str): The unique identifier for the analyzer.
            analyzer_schema (dict, optional): The schema definition for the analyzer. Defaults to None.
            analyzer_schema_path (str, optional): The file path to the analyzer schema JSON file. Defaults to "".
            training_storage_container_sas_url (str, optional): The SAS URL for the training storage container. Defaults to "".
            training_storage_container_path_prefix (str, optional): The path prefix within the training storage container. Defaults to "".

        Raises:
            ValueError: If neither `analyzer_schema` nor `analyzer_schema_path` is provided.
            requests.exceptions.HTTPError: If the HTTP request to create the analyzer fails.

        Returns:
            requests.Response: The response object from the HTTP request.
        """
        if analyzer_schema_path and Path(analyzer_schema_path).exists():
            with open(analyzer_schema_path, "r") as file:
                analyzer_schema = json.load(file)

        if not analyzer_schema:
            raise ValueError("Analyzer schema must be provided.")

        if (training_storage_container_sas_url
                and training_storage_container_path_prefix):  # noqa
            analyzer_schema["trainingData"] = self._get_training_data_config(
                training_storage_container_sas_url,
                training_storage_container_path_prefix,
            )

        headers = {"Content-Type": "application/json"}
        headers.update(self._headers)

        response = requests.put(
            url=self._get_analyzer_url(self._endpoint, self._api_version,
                                       analyzer_id),
            headers=headers,
            json=analyzer_schema,
        )
        response.raise_for_status()
        self._logger.info(f"Analyzer {analyzer_id} create request accepted.")
        return response

    def delete_analyzer(self, analyzer_id: str):
        """
        Deletes an analyzer with the specified analyzer ID.

        Args:
            analyzer_id (str): The ID of the analyzer to be deleted.

        Returns:
            response: The response object from the delete request.

        Raises:
            HTTPError: If the delete request fails.
        """
        response = requests.delete(
            url=self._get_analyzer_url(self._endpoint, self._api_version,
                                       analyzer_id),
            headers=self._headers,
        )
        response.raise_for_status()
        self._logger.info(f"Analyzer {analyzer_id} deleted.")
        return response

    def begin_analyze(self, analyzer_id: str, file_location: str):
        """
        Begins the analysis of a file or URL using the specified analyzer.

        Args:
            analyzer_id (str): The ID of the analyzer to use.
            file_location (str): The path to the file or the URL to analyze.

        Returns:
            Response: The response from the analysis request.

        Raises:
            ValueError: If the file location is not a valid path or URL.
            HTTPError: If the HTTP request returned an unsuccessful status code.
        """
        data = None
        if Path(file_location).exists():
            with open(file_location, "rb") as file:
                data = file.read()
            headers = {"Content-Type": "application/octet-stream"}
        elif "https://" in file_location or "http://" in file_location:
            data = {"url": file_location}
            headers = {"Content-Type": "application/json"}
        else:
            raise ValueError("File location must be a valid path or URL.")

        headers.update(self._headers)
        if isinstance(data, dict):
            response = requests.post(
                url=self._get_analyze_url(self._endpoint, self._api_version,
                                          analyzer_id),
                headers=headers,
                json=data,
            )
        else:
            response = requests.post(
                url=self._get_analyze_url(self._endpoint, self._api_version,
                                          analyzer_id),
                headers=headers,
                data=data,
            )

        response.raise_for_status()
        self._logger.info(
            f"Analyzing file {file_location} with analyzer: {analyzer_id}")
        return response

    def poll_result(
            self,
            response: Response,
            timeout_seconds: int = 120,
            polling_interval_seconds: int = 2,
    ):
        """
        Polls the result of an asynchronous operation until it completes or times out.

        Args:
            response (Response): The initial response object containing the operation location.
            timeout_seconds (int, optional): The maximum number of seconds to wait for the operation to complete. Defaults to 120.
            polling_interval_seconds (int, optional): The number of seconds to wait between polling attempts. Defaults to 2.

        Raises:
            ValueError: If the operation location is not found in the response headers.
            TimeoutError: If the operation does not complete within the specified timeout.
            RuntimeError: If the operation fails.

        Returns:
            dict: The JSON response of the completed operation if it succeeds.
        """
        operation_location = response.headers.get("operation-location", "")
        if not operation_location:
            raise ValueError(
                "Operation location not found in response headers.")

        headers = {"Content-Type": "application/json"}
        headers.update(self._headers)

        start_time = time.time()
        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout_seconds:
                raise TimeoutError(
                    f"Operation timed out after {timeout_seconds:.2f} seconds."
                )

            response = requests.get(operation_location, headers=self._headers)
            response.raise_for_status()
            status = response.json().get("status").lower()
            if status == "succeeded":
                self._logger.info(
                    f"Request result is ready after {elapsed_time:.2f} seconds."
                )
                return response.json()
            elif status == "failed":
                self._logger.error(
                    f"Request failed. Reason: {response.json()}")
                raise RuntimeError("Request failed.")
            else:
                self._logger.info(
                    f"Request {operation_location} in progress ...")
            time.sleep(polling_interval_seconds)

    def ensure_analyzer_exists(self, analyzer_id: str, analyzer_schema_path: str):
        """
        Checks if a custom analyzer exists, and creates it if it doesn't.

        Args:
            analyzer_id (str): The ID of the analyzer to check/create.
            analyzer_schema_path (str): The path to the analyzer schema JSON file, used if creation is needed.

        Raises:
            requests.exceptions.HTTPError: If checking or creating the analyzer fails.
            FileNotFoundError: If the analyzer_schema_path does not exist when creation is attempted.
        """
        try:
            self.get_analyzer_detail_by_id(analyzer_id)
            self._logger.info(f"Analyzer {analyzer_id} already exists.")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                self._logger.info(f"Analyzer {analyzer_id} not found. Creating...")
                if not Path(analyzer_schema_path).exists():
                     raise FileNotFoundError(f"Analyzer schema file not found at {analyzer_schema_path} for creation.")
                self.begin_create_analyzer(analyzer_id, analyzer_schema_path=analyzer_schema_path)
                # Add a small delay or polling mechanism if needed to ensure analyzer is ready before use
                # For simplicity, assuming creation is fast enough or handled by subsequent calls needing the analyzer.
                self._logger.info(f"Analyzer {analyzer_id} creation initiated.")
            else:
                # Re-raise other HTTP errors
                raise e

    def analyze_file_and_save_result(self, analyzer_id: str, file_path: str, output_path: str, timeout_seconds: int = 3600):
        """
        Analyzes a single file using the specified analyzer and saves the result to a JSON file.

        Args:
            analyzer_id (str): The ID of the analyzer to use.
            file_path (str): The full path to the file to analyze.
            output_path (str): The full path where the JSON result should be saved.
            timeout_seconds (int, optional): Timeout for polling the analysis result. Defaults to 3600.

        Returns:
            tuple: A tuple containing the input file_path and the elapsed time for processing.

        Raises:
            Exception: Catches and logs exceptions during the process.
        """
        start_time = time.time()
        self._logger.info(f"Processing {file_path}...")
        try:
            # Submit the file for content analysis
            response = self.begin_analyze(analyzer_id=analyzer_id, file_location=file_path)

            # Wait for the analysis to complete and get the content analysis result
            cu_result = self.poll_result(response, timeout_seconds=timeout_seconds)

            # Ensure the output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save the result to a file
            with open(output_path, "w") as f:
                json.dump(cu_result, f, indent=2)
            self._logger.info(f"Result saved to {output_path}")

        except Exception as e:
            self._logger.error(f"Error processing {file_path}: {e}")
            raise  # Re-raise the exception after logging

        end_time = time.time()
        elapsed_time = end_time - start_time
        self._logger.info(f"Finished processing {file_path} in {elapsed_time:.2f} seconds.")
        return cu_result, file_path, elapsed_time

    def analyze_files_in_parallel(self, analyzer_id: str, file_paths: list[str], output_dir: str, max_workers: int = 10, timeout_seconds: int = 3600):
        """
        Processes multiple files in parallel using the specified analyzer and saves results.

        Args:
            analyzer_id (str): The ID of the analyzer to use.
            file_paths (list[str]): A list of full paths to the files to process.
            output_dir (str): The directory where result JSON files should be saved.
                               File names will be based on input file names.
            max_workers (int, optional): Maximum number of parallel threads. Defaults to 4.
            timeout_seconds (int, optional): Timeout for polling each analysis result. Defaults to 3600.

        Returns:
            list: A list of results, where each result is a tuple (file_path, elapsed_time)
                  or None if an error occurred for that file.
        """
        results = []
        os.makedirs(output_dir, exist_ok=True) # Ensure output directory exists

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Prepare future tasks, mapping each future to its input file path
            future_to_file = {}
            for file_path in file_paths:
                # Construct the output path for each file
                base_name = os.path.basename(file_path)
                file_name_without_ext = os.path.splitext(base_name)[0]
                output_path = os.path.join(output_dir, f"{file_name_without_ext}.json")

                future = executor.submit(self.analyze_file_and_save_result,
                                         analyzer_id,
                                         file_path,
                                         output_path,
                                         timeout_seconds)
                future_to_file[future] = file_path

            # Process completed futures
            for future in future_to_file:
                file_path = future_to_file[future]
                try:
                    result = future.result()  # Collect the result (cu_result, file_path, elapsed_time)
                    results.append(result)
                except Exception as e:
                    self._logger.error(f"Failed to process {file_path} due to an error: {e}")
                    # Optionally append None or an error indicator to results
                    results.append(None) # Indicate failure for this file

        return results

    def process_analysis_results_to_csv(self, results_dir: str, file_type: str, output_csv_path: str):
        """
        Processes JSON result files from a directory, extracts data based on file type,
        and saves the combined results to a CSV file.

        Args:
            results_dir (str): The directory containing the JSON result files.
            file_type (str): The type of files analyzed (e.g., 'video', 'image', 'audio', 'document').
                             Determines how JSON results are parsed.
            output_csv_path (str): The full path where the output CSV file should be saved.

        Raises:
            FileNotFoundError: If the results_dir does not exist.
            Exception: Catches and logs other exceptions during processing.
        """
        if not os.path.isdir(results_dir):
            raise FileNotFoundError(f"Results directory not found: {results_dir}")

        combined_result = []
        col_names = ["file_name"] # Default column name

        self._logger.info(f"Processing results in {results_dir} for file type '{file_type}'")

        for json_file_name in os.listdir(results_dir):
            if json_file_name.endswith(".json"):
                json_file_path = os.path.join(results_dir, json_file_name)
                file_name_base = json_file_name.replace(".json", "")
                self._logger.debug(f"Processing result file: {json_file_path}")

                try:
                    with open(json_file_path, 'r') as f:
                        json_result_data = json.load(f)

                    # Initialize result list for this file
                    result = [file_name_base]

                    # --- Parsing logic based on file_type --- 
                    if (file_type == "document") or (file_type == "image"):
                        # Define column names based on the fields in page96.json
                        col_names = [
                            "file_name", "PageSectionTitle", "BodyText", "Summary", 
                            "PageKeywords", "FigureIds", "FigureCaptions", "FigureType", 
                            "FigureDescriptions", "FigureAnalyses", "ImportantWarnings"
                        ]
                        try:
                            contents = json_result_data.get("result", {}).get("contents", [])
                            if contents:
                                fields = contents[0].get("fields", {})
                                # Extract each field safely using .get()
                                page_section_title = fields.get("PageSectionTitle", {}).get("valueString", "")
                                body_text = fields.get("BodyText", {}).get("valueString", "")
                                summary = fields.get("Summary", {}).get("valueString", "")
                                page_keywords = fields.get("PageKeywords", {}).get("valueString", "")
                                figure_ids = fields.get("FigureIds", {}).get("valueString", "")
                                figure_captions = fields.get("FigureCaptions", {}).get("valueString", "")
                                figure_type = fields.get("FigureType", {}).get("valueString", "")
                                figure_descriptions = fields.get("FigureDescriptions", {}).get("valueString", "")
                                figure_analyses = fields.get("FigureAnalyses", {}).get("valueString", "")
                                important_warnings = fields.get("ImportantWarnings", {}).get("valueString", "")
                                
                                result.extend([
                                    page_section_title, body_text, summary, page_keywords, 
                                    figure_ids, figure_captions, figure_type, figure_descriptions, 
                                    figure_analyses, important_warnings
                                ])
                            else: # Handle case with no contents
                                self._logger.warning(f"No 'contents' found in {json_file_name}. Appending empty values.")
                                result.extend(["" for _ in range(len(col_names) - 1)]) # Append empty strings for all columns except file_name
                                
                            combined_result.append(result)

                        except Exception as e:
                            self._logger.warning(f"Could not parse document result {json_file_name} using page96 schema: {e}. Appending empty row.")
                            # Append a single row with file_name and empty values for other columns
                            empty_row = [file_name_base] + ["" for _ in range(len(col_names) - 1)]
                            combined_result.append(empty_row)
                            
                    else:
                        # Default case or unknown file type: just keep the file name
                        self._logger.warning(f"Unknown or unhandled file type '{file_type}' for {json_file_name}. Only file name will be included.")
                        combined_result.append(result) # Append only the file name
                        col_names = ["file_name"] # Reset columns if type is unknown

                except json.JSONDecodeError as e:
                    self._logger.error(f"Error decoding JSON from {json_file_path}: {e}")
                except Exception as e:
                    self._logger.error(f"Unexpected error processing {json_file_path}: {e}")

        # Save the results to a csv file
        try:
            # Ensure the output directory exists
            output_dir = os.path.dirname(output_csv_path)
            if output_dir:
                 os.makedirs(output_dir, exist_ok=True)
                 
            df_results = pd.DataFrame(combined_result, columns=col_names)
            df_results.to_csv(output_csv_path, index=False)
            self._logger.info(f"Results successfully saved to {output_csv_path}")
        except Exception as e:
            self._logger.error(f"Failed to save results to CSV {output_csv_path}: {e}")
            raise # Re-raise exception related to CSV saving

    def process_analysis_results_to_markdown(self, results_dir: str, file_type: str, output_md_path: str = None):
        """
        Processes JSON result files from a directory, extracts data based on file type,
        and generates an organized markdown text output.

        Args:
            results_dir (str): The directory containing the JSON result files.
            file_type (str): The type of files analyzed (e.g., 'video', 'image', 'audio', 'document').
                             Determines how JSON results are parsed.
            output_md_path (str, optional): The full path where the output markdown file should be saved.
                                          If None, the markdown string is returned.

        Returns:
            str or bool: The generated markdown string if output_md_path is None, 
                         True if saved successfully to a file, False otherwise.

        Raises:
            FileNotFoundError: If the results_dir does not exist.
            Exception: Catches and logs other exceptions during processing.
        """
        if not os.path.isdir(results_dir):
            os.makedirs(results_dir, exist_ok=True) # Create directory if it doesn't exist

        if output_md_path is not None:
            base_dir = os.path.dirname(results_dir)
            if not os.path.isdir(base_dir):
                os.makedirs(base_dir, exist_ok=True)

        markdown_output = []
        self._logger.info(f"Processing results in {results_dir} for file type '{file_type}' to generate Markdown.")

        for json_file_name in sorted(os.listdir(results_dir)): # Sort for consistent output order
            if json_file_name.endswith(".json"):
                json_file_path = os.path.join(results_dir, json_file_name)
                file_name_base = json_file_name.replace(".json", "")
                self._logger.debug(f"Processing result file for Markdown: {json_file_path}")

                try:
                    with open(json_file_path, 'r') as f:
                        json_result_data = json.load(f)

                    markdown_output.append(f"## Analysis Results for: `{file_name_base}`\n")

                    # --- Parsing logic based on file_type ---
                    if (file_type == "document") or (file_type == "image"):
                        try:
                            contents = json_result_data.get("result", {}).get("contents", [])
                            if contents:
                                fields = contents[0].get("fields", {})
                                
                                # Extract and format each field
                                page_section_title = fields.get("PageSectionTitle", {}).get("valueString", "")
                                if page_section_title: markdown_output.append(f"### {page_section_title}\n")

                                body_text = fields.get("BodyText", {}).get("valueString", "")
                                if body_text: markdown_output.append(f"**Body Text:**\n{body_text}\n")

                                summary = fields.get("Summary", {}).get("valueString", "")
                                if summary: markdown_output.append(f"**Summary:**\n{summary}\n")

                                page_keywords = fields.get("PageKeywords", {}).get("valueString", "")
                                if page_keywords: markdown_output.append(f"**Keywords:** `{page_keywords}`\n")

                                figure_ids = fields.get("FigureIds", {}).get("valueString", "")
                                if figure_ids: markdown_output.append(f"**Figure IDs:** `{figure_ids}`\n")

                                figure_captions = fields.get("FigureCaptions", {}).get("valueString", "")
                                if figure_captions: markdown_output.append(f"**Figure Captions:** {figure_captions}\n")

                                figure_type = fields.get("FigureType", {}).get("valueString", "")
                                if figure_type: markdown_output.append(f"**Figure Type:** `{figure_type}`\n")

                                figure_descriptions = fields.get("FigureDescriptions", {}).get("valueString", "")
                                if figure_descriptions: markdown_output.append(f"**Figure Descriptions:**\n{figure_descriptions}\n")

                                figure_analyses = fields.get("FigureAnalyses", {}).get("valueString", "")
                                if figure_analyses: markdown_output.append(f"**Figure Analyses:**\n{figure_analyses}\n")

                                important_warnings = fields.get("ImportantWarnings", {}).get("valueString", "")
                                if important_warnings: markdown_output.append(f"**Important Warnings:**\n{important_warnings}\n")

                            else:
                                self._logger.warning(f"No 'contents' found in {json_file_name}. Adding basic info.")
                                markdown_output.append("*No content fields extracted.*\n")

                        except Exception as e:
                            self._logger.warning(f"Could not parse document/image result {json_file_name} using expected schema: {e}. Adding basic info.")
                            markdown_output.append(f"*Error parsing content fields: {e}*\n")

                    else:
                        # Default case or unknown file type: just include raw JSON snippet or basic info
                        self._logger.warning(f"Unknown or unhandled file type '{file_type}' for {json_file_name}. Including basic info.")
                        markdown_output.append("*Analysis results for this file type are not specifically formatted.*\n")
                        # Optionally include raw JSON snippet here if desired
                        # markdown_output.append(f"```json\n{json.dumps(json_result_data, indent=2)}\n```\n")

                    markdown_output.append("\n---\n") # Separator between files

                except json.JSONDecodeError as e:
                    self._logger.error(f"Error decoding JSON from {json_file_path}: {e}")
                    markdown_output.append(f"## Analysis Results for: `{file_name_base}`\n")
                    markdown_output.append(f"*Error: Could not decode JSON file.*\n\n---\n")
                except Exception as e:
                    self._logger.error(f"Unexpected error processing {json_file_path}: {e}")
                    markdown_output.append(f"## Analysis Results for: `{file_name_base}`\n")
                    markdown_output.append(f"*Error: An unexpected error occurred during processing: {e}*\n\n---\n")

        # Combine markdown parts
        final_markdown = "".join(markdown_output)

        # Save to file or return string
        if output_md_path:
            try:
                # Ensure the output directory exists
                output_dir = os.path.dirname(output_md_path)
                if output_dir:
                    os.makedirs(output_dir, exist_ok=True)
                
                with open(output_md_path, 'w', encoding='utf-8') as f:
                    f.write(final_markdown)
                self._logger.info(f"Markdown results successfully saved to {output_md_path}")
                return True
            except Exception as e:
                self._logger.error(f"Failed to save markdown results to {output_md_path}: {e}")
                return False # Indicate failure to save
        else:
            return final_markdown # Return the generated string


