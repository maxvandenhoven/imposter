from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from imposter.models.catalog import ModelCatalog, ModelPrice, ModelProvider
from imposter.orchestration.setup import DEFAULT_MODEL_IDS
from imposter.words.picker import WordPicker


class CatalogModel(BaseModel):
    """A model that can play a seat, as the setup screen shows it.

    Attributes:
        id: The catalog id, the `model_id` of a seat in the game request.
        display_name: The name shown in the UI and in `models` identity mode.
        provider: The publisher of the model.
        logo: The path of the logo, relative to the web assets, if there is one.
        price_per_mtok: The price per million tokens, for cost estimates.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    display_name: str
    provider: ModelProvider
    logo: str | None
    price_per_mtok: ModelPrice


class CatalogCategory(BaseModel):
    """A built-in category of secret words, without its words.

    Attributes:
        name: The category name, the `category` of the word options.
        description: What the words of the category have in common.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str


class CatalogResponse(BaseModel):
    """What the setup screen offers: the models, the word categories and the lineup.

    Attributes:
        models: The models, in catalog order.
        categories: The word categories, in alphabetical order.
        default_lineup: The catalog ids of the default seats, in seat order.
    """

    model_config = ConfigDict(frozen=True)

    models: list[CatalogModel]
    categories: list[CatalogCategory]
    default_lineup: list[str]


def catalog_router(*, catalog: ModelCatalog, picker: WordPicker) -> APIRouter:
    """Build the router of the catalog route.

    Args:
        catalog: The models that can play a seat.
        picker: Holds the built-in word categories.

    Returns:
        The router.
    """
    router = APIRouter()
    response = CatalogResponse(
        models=[
            CatalogModel.model_validate(entry, from_attributes=True)
            for entry in catalog.entries
        ],
        categories=[
            CatalogCategory(name=category.name, description=category.description)
            for category in picker.categories.values()
        ],
        default_lineup=DEFAULT_MODEL_IDS,
    )

    @router.get(
        "/catalog",
        description="List the models, the word categories and the default lineup.",
    )
    async def read_catalog() -> CatalogResponse:
        return response

    return router
