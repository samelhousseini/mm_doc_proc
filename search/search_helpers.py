import os
import sys
sys.path.append('..')
from pydantic import BaseModel
from azure.search.documents.indexes.models import (SearchFieldDataType, SimpleField, SearchField, SearchableField, ComplexField)
from typing import get_origin, get_args, Union
from typing import (Any, Dict, List, Optional, Type, Union)

from utils.openai_utils import *
from multimodal_processing_pipeline.data_models import *
from utils.file_utils import *
from utils.text_utils import *
from search_data_models import *




def expand_searh_terms(query, model_info=None):
    search_expansion_prompt = read_asset_file('search/search_prompts/search_expansion_prompt.txt')[0]
    prompt = search_expansion_prompt.format(query=query)

    response = call_llm_structured_outputs(
        prompt=prompt,
        model_info=model_info,
        response_format=SearchExpansion
    )

    return response





###############################################################################
# DYNAMIC INDEX BUILDER
###############################################################################
def is_pydantic_model(type_hint: Any) -> bool:
    """
    Check if a given type hint is a subclass of pydantic.BaseModel.
    """
    return isinstance(type_hint, type) and issubclass(type_hint, BaseModel)

def map_primitive_to_search_data_type(type_hint: Any) -> SearchFieldDataType:
    """
    Map Python primitive/standard types to Azure Cognitive Search data types.
    Extend or adjust as needed for your application.
    """
    from typing import get_origin, get_args
    import datetime

    if type_hint == str:
        return SearchFieldDataType.String
    if type_hint == int:
        return SearchFieldDataType.Int64  # or Int32
    if type_hint == float:
        return SearchFieldDataType.Double
    if type_hint == bool:
        return SearchFieldDataType.Boolean
    if type_hint in (datetime.date, datetime.datetime):
        return SearchFieldDataType.DateTimeOffset
    # Fallback
    return SearchFieldDataType.String



def build_search_fields_for_model(
    model: Type[BaseModel],
    key_field_name: Optional[str] = None,
    is_in_collection: bool = False,
    embedding_dimensions: int = 1536,
    vector_profile_name: str = "myHnswProfile"
):
    """
    Recursively build a hierarchical Azure Cognitive Search schema from a Pydantic model.

    - Nested models -> ComplexField with subfields
    - List of nested models -> ComplexField(collection=True)
    - List of primitives -> either SimpleField or SearchableField(collection=True)
    - List of float -> interpret as a Vector field (SearchField with vector config)
    - If 'key_field_name' matches the field, we mark it as the key (top-level only).
    - If 'is_in_collection' is True, we disable sorting to avoid multi-valued sorting errors.
    - We also disable sorting on vector fields.
    """
    
    def is_vector_field(outer_type: Any) -> bool:
        """
        Return True if the type is List[float] or Optional[List[float]] or similar.
        """
        # For example, if outer_type is List[float], or Union[List[float], None], etc.
        if get_origin(outer_type) in (list, List):
            (inner_type,) = get_args(outer_type)
            return inner_type == float
        if get_origin(outer_type) is Union:
            union_args = get_args(outer_type)
            # e.g. Union[List[float], None]
            # We'll check if there's exactly 1 non-None arg which is List[float].
            non_none_args = [arg for arg in union_args if arg is not type(None)]
            if len(non_none_args) == 1 and get_origin(non_none_args[0]) in (list, List):
                (inner_type,) = get_args(non_none_args[0])
                return inner_type == float
        return False

    fields = []

    for field_name, model_field in model.model_fields.items():
        use_as_key = (field_name == key_field_name)
        outer_type = model_field.annotation  # For Pydantic 2.x

        # 1) Check if it's a vector field (list of floats)
        if is_vector_field(outer_type):
            print(f"Vector field: {field_name} -> {outer_type}")
            # This field is a vector. We'll define a SearchField with vector properties.
            fields.append(
                SearchField(
                    name=field_name,
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,   # vector fields must be 'searchable=True'
                    filterable=False,
                    facetable=False,
                    sortable=False,    # no sorting on a vector
                    key=use_as_key,
                    vector_search_dimensions=embedding_dimensions,
                    vector_search_profile_name=vector_profile_name
                )
            )
            continue

        # 2) Otherwise, check if it's a generic list
        origin = get_origin(outer_type)
        if origin in (list, List):
            print(f"List field: {field_name} -> {outer_type}")
            (inner_type,) = get_args(outer_type)

            # If the inner type is another Pydantic model => Complex collection
            if is_pydantic_model(inner_type):
                print(f"Nested model collection: {field_name} -> {inner_type}")
                subfields = build_search_fields_for_model(
                    inner_type,
                    key_field_name=None,
                    is_in_collection=True,
                    embedding_dimensions=embedding_dimensions,
                    vector_profile_name=vector_profile_name
                )
                fields.append(
                    ComplexField(
                        name=field_name,
                        fields=subfields,
                        collection=True
                    )
                )
            else:
                # It's a list of primitives
                data_type = map_primitive_to_search_data_type(inner_type)
                if data_type == SearchFieldDataType.String:
                    fields.append(
                        SearchableField(
                            name=field_name,
                            type=data_type,
                            collection=True,
                            searchable=True,
                            filterable=True,
                            facetable=False,
                            sortable=False,  # multi-valued => no sorting
                            key=use_as_key
                        )
                    )
                else:
                    fields.append(
                        SimpleField(
                            name=field_name,
                            type=data_type,
                            collection=True,
                            filterable=True,
                            facetable=True,
                            sortable=False,  # multi-valued => no sorting
                            key=use_as_key
                        )
                    )
            continue

        # 3) If it's a nested Pydantic model (single object)
        if is_pydantic_model(outer_type):
            print(f"Nested model: {field_name} -> {outer_type}")
            subfields = build_search_fields_for_model(
                outer_type,
                key_field_name=None,
                is_in_collection=is_in_collection,
                embedding_dimensions=embedding_dimensions,
                vector_profile_name=vector_profile_name
            )
            fields.append(
                ComplexField(
                    name=field_name,
                    fields=subfields,
                    collection=False
                )
            )
            continue

        # 4) Otherwise, possibly a primitive or optional
        if get_origin(outer_type) is Union:
            print(f"Union type: {field_name} -> {outer_type}")
            union_args = get_args(outer_type)
            non_none_args = [arg for arg in union_args if arg is not type(None)]
            chosen_type = non_none_args[0] if non_none_args else str
        else:
            chosen_type = outer_type

        data_type = map_primitive_to_search_data_type(chosen_type)

        if data_type == SearchFieldDataType.String:
            fields.append(
                SearchableField(
                    name=field_name,
                    type=data_type,
                    searchable=True,
                    filterable=True,
                    facetable=False,
                    sortable=(False if is_in_collection else True),
                    key=use_as_key
                )
            )
        else:
            fields.append(
                SimpleField(
                    name=field_name,
                    type=data_type,
                    filterable=True,
                    facetable=True,
                    sortable=(False if is_in_collection else True),
                    key=use_as_key
                )
            )

    return fields