import os
import json
from app.core.logger import get_logger
from app.models.schemas import PortfolioData

logger = get_logger(__name__)

class DataProvider:
    """
    Centralized provider for loading and caching data from data.json.
    Uses file modification time (mtime) and Pydantic validation for data integrity.
    """
    _instance = None
    _data = None
    _last_mtime = 0
    _file_path = os.path.join(os.path.dirname(__file__), "../data/data.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataProvider, cls).__new__(cls)
        return cls._instance

    def get_data(self) -> dict:
        """
        Returns the data from data.json. Reloads and validates if mtime changed.
        """
        try:
            if not os.path.exists(self._file_path):
                logger.error(f"Data file not found at: {self._file_path}")
                return {}

            current_mtime = os.path.getmtime(self._file_path)
            if self._data is None or current_mtime > self._last_mtime:
                logger.info(f"Reloading and validating data from {self._file_path}")
                
                with open(self._file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                # Pydantic Validation
                validated_data = PortfolioData(**raw_data)
                self._data = validated_data.model_dump()
                self._last_mtime = current_mtime
                logger.info("Data validation successful.")
            
            return self._data
        except Exception as e:
            logger.error(f"DATA_VALIDATION_ERROR: {e}")
            # Return old data if new data is invalid, or empty dict if first load
            return self._data or {}

data_provider = DataProvider()
