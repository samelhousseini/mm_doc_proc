import os
import base64
import json
from PIL import Image
from utils.file_utils import write_to_file, replace_extension, read_asset_file, locate_prompt
from utils.text_utils import clean_up_text, extract_markdown, extract_code
from utils.openai_utils import call_llm, call_llm_structured_outputs
from multimodal_processing_pipeline.data_models import EmbeddedText, EmbeddedImages, EmbeddedTables


module_directory = os.path.dirname(os.path.abspath(__file__))



def locate_ingestion_prompt(prompt_name, module_directory=module_directory):
    return locate_prompt(prompt_name, module_directory)




def convert_png_to_jpg(image_path):
    """
    Converts a PNG image to JPG format.
    """
    if os.path.splitext(image_path)[1].lower() == '.png':
        with Image.open(image_path) as img:
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            new_image_path = os.path.splitext(image_path)[0] + '.jpg'
            img.save(new_image_path, 'JPEG')
            return new_image_path
    else:
        return image_path


def get_image_base64(image_path):
    """
    Encodes an image file in base64 format.
    """
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
        return encoded_string.decode('ascii')


def analyze_images(image_path, model_info=None):
    """
    Analyzes an image and generates descriptions or explanations.

    Args:
        image_path (str): Path to the image file.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Analysis response.
        str: Generated text filename.
    """
    prompt_path = locate_ingestion_prompt('image_description_prompt.txt')
    image_prompt = read_asset_file(prompt_path)[0]
    image_path = convert_png_to_jpg(image_path)  # Ensure the image is in JPG format

    response = call_llm_structured_outputs(
        imgs=image_path,
        prompt=image_prompt,
        model_info=model_info,
        response_format=EmbeddedImages
    )

    return response


def analyze_tables(image_path, model_info=None):
    """
    Analyzes an image to extract table data and formats it as Markdown.

    Args:
        image_path (str): Path to the image file.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Table analysis response.
        str: Generated Markdown filename.
    """
    prompt_path = locate_ingestion_prompt('table_description_prompt.txt')
    table_prompt = read_asset_file(prompt_path)[0]
    image_path = convert_png_to_jpg(image_path)  # Ensure the image is in JPG format

    response = call_llm_structured_outputs(
        imgs=image_path,
        prompt=table_prompt,
        model_info=model_info,
        response_format=EmbeddedTables
    )

    return response


def process_text(text, page_image_path, model_info=None):
    """
    Processes text using a language model.

    Args:
        text (str): The input text to process.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Processed text.
    """

    prompt_path = locate_ingestion_prompt('process_extracted_text_prompt.txt')
    process_text_prompt = read_asset_file(prompt_path)[0]

    prompt = process_text_prompt.format(text=text)

    if model_info.model_name == "o1-mini":
        response = call_llm(
            prompt,
            model_info=model_info
        )
        return response
    else:
        response = call_llm(
            prompt=prompt,
            model_info=model_info,
            imgs = [page_image_path],
        )
        return response


def condense_text(text, model_info=None):
    """
    Condenses text to a specified number of tokens.

    Args:
        text (str): The input text to condense.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Condensed text.
    """
    prompt_path = locate_ingestion_prompt('document_condensation_prompt.txt')
    condense_text_prompt = read_asset_file(prompt_path)[0]
    prompt = condense_text_prompt.format(document=text)

    response = call_llm(
        prompt,
        model_info=model_info
    )

    return response



def generate_table_of_contents(text, model_info=None):
    """
    Generates a table of contents.

    Args:
        text (str): The input text to use.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Table of contents.
    """
    prompt_path = locate_ingestion_prompt('table_of_contents_prompt.txt')
    toc_text_prompt = read_asset_file(prompt_path)[0]
    prompt = toc_text_prompt.format(document=text)

    response = call_llm(
        prompt,
        model_info=model_info
    )

    return response




def translate_text(text, target_language, model_info=None):
    """
    Translate text.

    Args:
        text (str): The input text to use.
        model_info (dict): Information about the model configuration.

    Returns:
        str: Translated text.
    """
    prompt_path = locate_ingestion_prompt('translate_text_prompt.txt')
    translate_prompt = read_asset_file(prompt_path)[0]
    prompt = translate_prompt.format(text=text, target_language=target_language)

    response = call_llm(
        prompt,
        model_info=model_info
    )

    return response




def apply_custom_page_processing_prompt(page_text: str, 
                                        custom_page_processing_prompt: str, 
                                        response_format=None, 
                                        model_info=None,
                                        imgs=[]):
    """
    Apply custom processing to a page of text using a language model.
        page_text (str): The text of the page to process.
        custom_page_processing_prompt (str): Custom instructions for processing the page.
        model_info (dict, optional): Information about the model configuration. Defaults to None.       

    Returns:
        str: The processed text as returned by the language model.
    """
    prompt_path = locate_ingestion_prompt('custom_page_processing_prompt_wrapper.txt')
    custom_page_prompt = read_asset_file(prompt_path)[0]
    prompt = custom_page_prompt.format(page_text=page_text, custom_instructions=custom_page_processing_prompt)

    if response_format is None:
        response = call_llm(
            prompt,
            model_info=model_info,
            imgs=imgs
        )
    else:
        response = call_llm_structured_outputs(
            prompt=prompt,
            model_info=model_info,
            response_format=response_format,
            imgs=imgs
        )
        
        response = json.dumps(response.model_dump(), indent=4)

    return response


def apply_custom_document_processing_prompt(document_text: str, 
                                            custom_document_processing_prompt: str,  
                                            response_format=None, 
                                            model_info=None,
                                            imgs=[]):
    """
    Apply custom processing to a document using a language model.
        page_text (str): The text of the document to process.
        custom_page_processing_prompt (str): Custom instructions for processing the document.
        model_info (dict, optional): Information about the model configuration. Defaults to None.       

    Returns:
        str: The processed text as returned by the language model.
    """
    prompt_path = locate_ingestion_prompt('custom_document_processing_prompt_wrapper.txt')
    custom_page_prompt = read_asset_file(prompt_path)[0]
    prompt = custom_page_prompt.format(document_text=document_text, custom_instructions=custom_document_processing_prompt)

    if response_format is None:
        response = call_llm(
            prompt,
            model_info=model_info,
            imgs=imgs
        )
    else:
        response = call_llm_structured_outputs(
            prompt=prompt,
            model_info=model_info,
            response_format=response_format,
            imgs=imgs
        )

        response = json.dumps(response.model_dump(), indent=4)

    return response