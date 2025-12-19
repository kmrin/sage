from typing import Optional
from discord import Interaction, Locale

from ..log import loggers
from ..paths import paths
from ..utils import yaml_read
from ..models.locale import Localisation

logger = loggers.LOCALE
locales: dict[str, Localisation] = {}
locale_files = list(paths.locale.glob("*.yml"))

if not locale_files:
    raise RuntimeError(f"Localisation loading failed; No locale files found in locale path")

for locale_file in paths.locale.glob("*.yml"):
    locale_data = yaml_read(locale_file, supress_logs=True)
    
    if not locale_data or not isinstance(locale_data, dict):
        raise ValueError(f"Failed to load {locale_file}; Empty or invalid format")

    sections = [field for field in Localisation.__pydantic_fields__]
    missing = [section for section in sections if section not in locale_data]
    
    if missing:
        raise ValueError(f"Failed to load {locale_file}; Missing sections: {', '.join(missing)}")
    
    invalid = [section_name for section_name, section in locale_data.items() if not isinstance(section, dict)]
    
    if invalid:
        raise ValueError(
            f"Failed to load {locale_file}; One or more sections are in a invalid format: {', '.join(invalid)}"
        )
    
    locale_model = Localisation(**locale_data)  # Can raise pydantic.ValidationError
    locales[locale_file.stem] = locale_model
    
    logger.info(f"Locale {locale_file.stem} successfully loaded")

if Locale.british_english not in locales:
    raise RuntimeError(f"Default locale 'en-GB' not found in locale list")


def get_interaction_locale(interaction: Interaction) -> Localisation:
    int_locale = str(interaction.locale) if interaction.locale else Locale.british_english
    
    if int_locale == Locale.american_english or int_locale not in locales:
        int_locale = Locale.british_english
    
    try:
        return locales[str(int_locale)]
    except KeyError:
        # This should never be raised as 'en-GB' should always be present
        # but we'll catch it anyway
        logger.error(f"Failed to fetch locale {int_locale} from locale list; Not present")
        raise


def get_string(
        loc_source: str | Locale | Interaction, key: str, default: str = "", **string_format
) -> str:
    if isinstance(loc_source, Interaction):
        locale = get_interaction_locale(loc_source)
    else:
        locale = locales.get(str(loc_source), locales.get(str(Locale.british_english)))
    
    if not locale:
        logger.error(f"Failed to fetch locale data for {locale}")
        return default
    
    fetched = locale.get(key, default)
    
    if not isinstance(fetched, str):
        logger.error(f"Failed to fetch {key}; Value is not a string")
        return default
    
    return fetched.format(**string_format)


def get_string_list(
        loc_source: str | Locale | Interaction, key: str, default: Optional[list[str]] = None
) -> list[str]:
    if isinstance(loc_source, Interaction):
        locale = get_interaction_locale(loc_source)
    else:
        locale = locales.get(str(loc_source), locales.get(str(Locale.british_english)))
    
    if not locale:
        logger.error(f"Failed to fetch locale data for {locale}")
        return default or []
    
    fetched = locale.get(key, default or [])
    
    if not isinstance(fetched, list) or not fetched:
        logger.error(f"Failed to fetch {key}; Value is not a list or is empty")
        return default or []
    
    if not all(isinstance(item, str) for item in fetched):
        logger.error(f"Failed to fetch {key}; List items are not all strings")
        return default or []
    
    return fetched