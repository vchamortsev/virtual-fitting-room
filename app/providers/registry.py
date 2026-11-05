"""Выбор движка. Авторежим не подставляет некоммерческий FLUX сам."""

from app.config import Settings
from app.domain import MODEL_ALIASES
from app.providers.base import ModelCard, TryOnProvider
from app.providers.catvton_flux import CatVtonFluxProvider
from app.providers.fashn import FashnProvider
from app.providers.mock import MockProvider


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._providers: dict[str, TryOnProvider] = {
            "fashn-vton-1.5": FashnProvider(settings),
            "catvton-flux": CatVtonFluxProvider(settings),
            "mock": MockProvider(),
        }

    def cards(self) -> list[ModelCard]:
        return [provider.probe() for provider in self._providers.values()]

    def resolve(self, requested: str | None) -> str:
        if requested is None or not requested.strip() or requested.strip().lower() == "auto":
            return self.default_id()
        canonical = MODEL_ALIASES.get(requested.strip().lower())
        if canonical is None or canonical not in self._providers:
            known = ", ".join(self._providers)
            raise KeyError(f"Неизвестная модель. Доступны: {known}.")
        return canonical

    def default_id(self) -> str:
        requested = self.settings.default_model.strip().lower()
        if requested and requested != "auto":
            return self.resolve(requested)
        for candidate in ("fashn-vton-1.5", "mock"):
            if self._providers[candidate].probe().available:
                return candidate
        return "mock"

    def get(self, model_id: str) -> TryOnProvider:
        return self._providers[model_id]

    def require_available(self, model_id: str) -> ModelCard:
        card = self.get(model_id).probe()
        if not card.available:
            raise RuntimeError(card.detail)
        return card
