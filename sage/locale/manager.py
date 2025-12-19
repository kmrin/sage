from typing import Optional
from dataclasses import fields
from discord import Interaction, Locale

from ..log import loggers, log_exception
from ..paths import paths
from ..utils import yaml_read
from ..models.locale import Localisation

logger = loggers.LOCALE
locales: dict[str, Localisation] = {}


def get_interaction_locale(interaction: Interaction) -> Localisation:
    locale = str(interaction.locale) if interaction.locale else Locale.british_english

    if locale == Locale.american_english or locale not in locales:
        locale = Locale.british_english

    return locales.get(locale)


def catch_missing_sections(locale_data: dict) -> list[str]:
    sections = [field.name for field in fields(Localisation)]
    missing = [section for section in sections if section not in locale_data]

    return missing


def catch_invalid_sections(locale_data: dict) -> list[str]:
    return [section_name for section_name, section in locale_data.items() if not isinstance(section, dict)]


def validate_and_load_locales() -> bool:
    for locale_file in paths.locale.glob("*.yml"):
        locale_data = yaml_read(locale_file, supress_logs=True)

        if not locale_data:
            logger.warning(f"Skipping empty locale file {str(locale_file)}")
            continue

        missing = catch_missing_sections(locale_data)
        invalid = catch_invalid_sections(locale_data)

        if missing:
            logger.error(f"Missing sections in {str(locale_file)}: {', '.join(missing)}")
            return False
        if invalid:
            logger.error(f"Invalid sections in {str(locale_file)}: {', '.join(invalid)}")
            return False

        try:
            locales[locale_file.stem] = Localisation(**locale_data)
        except Exception as e:
            e_str = log_exception(e, logger)
            logger.error(f"Failed to load locale file {str(locale_file)}: {e_str}")
            continue

        logger.info(f"Locale {locale_file.stem} successfully loaded")

    if not locales:
        logger.error("No valid locale files found")
        return False
    return True


def get_string(
        context: str | Interaction,
        key: str,
        default: str = "",
        *args, **kwargs
) -> str:
    if isinstance(context, Interaction):
        locale = get_interaction_locale(context)
    else:
        locale = locales.get(context, locales.get(Locale.british_english))

    if not locale:
        logger.error(f"Failed to fetch locale data for '{context}'")
        return default

    fetched = locale.get(key, default)

    if not isinstance(fetched, str):
        logger.error(f"Failed to fetch '{key}' in locale data; value is not a string")
        return default

    return fetched.format(*args, **kwargs)


def get_string_list(
        context: str | Interaction,
        key: str,
        default: Optional[list[str]] = None
) -> list[str]:
    if isinstance(context, Interaction):
        locale = get_interaction_locale(context)
    else:
        locale = locales.get(context, locales.get(Locale.british_english))

    if not locale:
        logger.error(f"Failed to fetch locale data for '{context}'")
        return default

    fetched = locale.get(key, default)

    if not isinstance(fetched, list):
        logger.error(f"Failed to fetch '{key}' in locale data; value is not a list")
        return default
    elif len(fetched) == 0:
        logger.error(f"Failed to fetch '{key}' in locale data; list is empty")
        return default

    return fetched