import logging
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from textual.binding import Binding

from barback.util.logger import get_logger

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@dataclass
class AppConfig:
    """Configuration for an external application."""

    display_name: str
    application_name: str
    max_files: int | None = None


@dataclass
class BarbackConfig:
    """Main configuration for Barback."""

    theme: str = "tokyonight"
    good_dither_path: str | None = None
    log_level: LogLevel = "INFO"
    apps: list[AppConfig] = field(default_factory=list)
    logger: logging.Logger = get_logger()

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the path to the config file."""
        return Path.home() / ".barback" / "config.toml"

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default configuration as a TOML string."""
        current_file = Path(__file__)
        repo_root = current_file.parent.parent.parent
        repo_default = repo_root / "config.default.toml"

        if repo_default.exists():
            return repo_default

        package_default = current_file.parent.parent / "config.default.toml"
        if package_default.exists():
            return package_default

        local_default = Path("config.default.toml")
        if local_default.exists():
            return local_default

        raise FileNotFoundError(
            "config.default.toml not found. Please ensure it exists in the repository root, or create a config file at ~/.barback/config.toml"
        )

    @classmethod
    def load(cls) -> "BarbackConfig":
        """
        Load configuration from file or create default if not found.

        Returns:
            BarbackConfig: The loaded or default configuration
        """
        config_path = cls.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if not config_path.exists():
            # Copy default config file
            try:
                default_config_path = cls.get_default_config_path()
                shutil.copy2(default_config_path, config_path)
                cls.logger.info(f"Created default config at {config_path}")
            except FileNotFoundError as e:
                cls.logger.error(f"Could not find config.default.toml: {e}")

        # Load and parse config
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            # Parse apps
            apps = []
            for app_data in data.get("apps", []):
                apps.append(
                    AppConfig(
                        display_name=app_data["display_name"],
                        application_name=app_data["application_name"],
                        max_files=app_data.get("max_files"),
                    )
                )

            config = cls(
                theme=data.get("theme", "tokyo-night"),
                good_dither_path=data.get("good_dither_path"),
                log_level=data.get("log_level", "INFO"),
                apps=apps,
            )

            cls.logger.info(f"Loaded config from {config_path}")
            return config

        except Exception as e:
            cls.logger.error(
                f"Failed to load config from {config_path}: {e}", exc_info=True
            )
            cls.logger.info("Using default configuration")
            return cls()

    def get_log_level(self) -> int:
        """Convert log level string to self.logger constant."""
        return getattr(self.logger, self.log_level.upper(), logging.INFO)

    def generate_app_bindings(self) -> list[Binding]:
        """
        Generate Textual bindings for all configured apps.

        Returns:
            List of Bindings
        """
        bindings = []
        shift_key_names = [
            "exclamation_mark",  # 1
            "at",  # 2
            "hash",  # 3
            "dollar",  # 4
            "percent",  # 5
            "circumflex",  # 6
            "ampersand",  # 7
            "asterisk",  # 8
            "left_parenthesis",  # 9
            "right_parenthesis",  # 0
        ]

        for idx, app in enumerate(self.apps, start=1):
            if idx > 10:
                break

            key = str(idx % 10)
            # shift_key = "!@#$%^&*()"[idx - 1]
            shift_key = shift_key_names[idx - 1]

            # Regular binding: open selected file
            bindings.append(
                Binding(
                    key,
                    f"open_in_{app.display_name.lower().replace(' ', '_')}",
                    app.display_name,
                    show=True,
                    tooltip=f"Open selected file in {app.application_name}",
                )
            )

            # Shift binding: open all files with issue type
            bindings.append(
                Binding(
                    shift_key,
                    f"open_all_in_{app.display_name.lower().replace(' ', '_')}",
                    f"{app.display_name} (All)",
                    show=False,
                    tooltip=f"Open all files with a specific issue in {app.application_name}",
                )
            )

        return bindings


_config_instance = None


def get_config() -> BarbackConfig:
    """Get the Barback logger instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = BarbackConfig.load()
    return _config_instance
