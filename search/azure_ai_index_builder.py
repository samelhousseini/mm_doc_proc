import datetime
from typing import (
    Any,
    List,
    get_args,
    get_origin,
    Union,
    Type,
    Optional
)
from pydantic import BaseModel

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    ComplexField,
    SearchFieldDataType,
    SearchField
)

def is_pydantic_model(type_hint: Any) -> bool:
    """
    Check if a given type hint is a subclass of pydantic.BaseModel.
    """
    return isinstance(type_hint, type) and issubclass(type_hint, BaseModel)

def map_primitive_to_search_data_type(type_hint: Any) -> SearchFieldDataType:
    """
    Map Python primitive/standard types to Azure Cognitive Search data types.
    Extend this as needed for your application.
    """
    if type_hint == str:
        return SearchFieldDataType.String
    if type_hint == int:
        # Edm.Int32 vs. Edm.Int64 is up to you. We'll choose Int64 for safety.
        return SearchFieldDataType.Int64
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
    is_in_collection: bool = False
) -> List[SearchField]:
    """
    Recursively build a hierarchical Azure Cognitive Search schema from a Pydantic model.

    - If a field is a nested Pydantic model, we create a ComplexField with its subfields.
    - If a field is a list of nested models, we set `collection=True` on that ComplexField,
      and recursively build subfields with `is_in_collection=True`.
    - If a field is a list of primitives, we set `collection=True` on the SimpleField or SearchableField.
    - If 'key_field_name' matches the current field, we mark it as the key (top-level only).
    - If 'is_in_collection' is True, we force `sortable=False` to prevent "multi-valued sorting" errors.
    """
    fields = []

    for field_name, model_field in model.__fields__.items():
        # Should this field be the key?
        use_as_key = (field_name == key_field_name)

        # In Pydantic 2.x, 'annotation' is the declared type
        outer_type = model_field.annotation

        # 1) Check for list/collection
        if get_origin(outer_type) in (list, List):
            (inner_type,) = get_args(outer_type)

            if is_pydantic_model(inner_type):
                # A list of nested Pydantic models
                subfields = build_search_fields_for_model(
                    inner_type,
                    # We don't pass the key name deeper for collection items
                    key_field_name=None,
                    # Inside a collection, subfields can't be sortable
                    is_in_collection=True
                )
                fields.append(
                    ComplexField(
                        name=field_name,
                        fields=subfields,
                        collection=True
                    )
                )
            else:
                # A list of primitives
                data_type = map_primitive_to_search_data_type(inner_type)
                # Because it's in a list, sorting is not allowed
                if data_type == SearchFieldDataType.String:
                    fields.append(
                        SearchableField(
                            name=field_name,
                            type=data_type,
                            collection=True,
                            searchable=True,
                            filterable=True,
                            facetable=False,
                            # Multi-valued => cannot enable sorting
                            sortable=False,
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
                            # Multi-valued => cannot enable sorting
                            sortable=False,
                            key=use_as_key
                        )
                    )

        # 2) If it's a nested Pydantic model (single object, not a list)
        elif is_pydantic_model(outer_type):
            subfields = build_search_fields_for_model(
                outer_type,
                key_field_name=None,  # don't propagate the key name to nested
                is_in_collection=is_in_collection  # keep track of whether we are nested in a collection
            )
            fields.append(
                ComplexField(
                    name=field_name,
                    fields=subfields,
                    collection=False
                )
            )

        # 3) Otherwise, it's likely a primitive or optional
        else:
            # If it's Optional[...] (Union[T, None]), unwrap T
            if get_origin(outer_type) is Union:
                union_args = get_args(outer_type)
                non_none_args = [arg for arg in union_args if arg is not type(None)]
                chosen_type = non_none_args[0] if non_none_args else str
            else:
                chosen_type = outer_type

            data_type = map_primitive_to_search_data_type(chosen_type)

            # If it's a string, default to "searchable"
            if data_type == SearchFieldDataType.String:
                fields.append(
                    SearchableField(
                        name=field_name,
                        type=data_type,
                        searchable=True,
                        filterable=True,
                        facetable=False,
                        # Disallow sorting if we're inside a collection
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
                        # Disallow sorting if we're inside a collection
                        sortable=(False if is_in_collection else True),
                        key=use_as_key
                    )
                )

    return fields


class DynamicAzureIndexBuilder:
    """
    A dynamic builder that can take any Pydantic model and generate an 
    Azure Cognitive Search index schema. This version prevents sorting 
    on multi-valued (collection) fields to avoid 'OperationNotAllowed' errors.

    Key field logic:
      1) Provide an existing field name as the key => That field is marked key=True
      2) Provide a new custom field name (not in the model) => We'll create it
      3) If none is provided => We'll create a new field called "index_id"
    """

    def __init__(self, endpoint: str, api_key: str):
        """
        :param endpoint: Your Azure Cognitive Search endpoint.
        :param api_key: Your Admin key for the search service.
        """
        self.index_client = SearchIndexClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key)
        )

    def build_index(
        self,
        model: Type[BaseModel],
        index_name: str,
        key_field_name: Optional[str] = None
    ) -> SearchIndex:
        """
        Build a SearchIndex from the given Pydantic model, ensuring exactly one key field.

        :param model: Pydantic model class.
        :param index_name: Must be lowercase for Azure Search.
        :param key_field_name: 
            - If it exists in the model, that field is the key
            - If it doesn't exist, we create a new string field with that name
            - If None, we default to "index_id"
        """
        # 1) Decide the final key field
        if not key_field_name:
            final_key_field = "index_id"
            create_new_key = True
        else:
            if key_field_name in model.__fields__:
                final_key_field = key_field_name
                create_new_key = False
            else:
                final_key_field = key_field_name
                create_new_key = True

        # 2) Build fields from the model
        built_fields = build_search_fields_for_model(
            model,
            key_field_name=(final_key_field if not create_new_key else None),
            is_in_collection=False
        )

        # 3) If needed, add a brand-new key field
        extra_fields = []
        if create_new_key:
            extra_fields.append(
                SimpleField(
                    name=final_key_field,
                    type=SearchFieldDataType.String,
                    key=True,
                    filterable=False,
                    facetable=False,
                    sortable=False
                )
            )

        all_fields = extra_fields + built_fields

        return SearchIndex(
            name=index_name.lower(),
            fields=all_fields
        )

    def create_or_update_index(
        self,
        model: Type[BaseModel],
        index_name: str,
        key_field_name: Optional[str] = None
    ) -> None:
        """
        Create or update the Azure Cognitive Search index.

        :param model: Pydantic model class.
        :param index_name: The index name (must be lowercase).
        :param key_field_name: 
            - Name of the key field if reusing a model field
            - A new field name
            - or None to default to 'index_id'
        """
        index_definition = self.build_index(model, index_name, key_field_name)
        result = self.index_client.create_or_update_index(index=index_definition)
        print(f"Index created/updated with name: {result.name}")
