from abc import ABC, abstractmethod


class PvxModule(ABC):
    name: str
    version: str

    @abstractmethod
    def cli_group(self):
        ...

    def interactive_entry(self):
        return None

    def get_logger(self):
        from pvx.logging_.setup import get_module_logger

        return get_module_logger(self.name)
