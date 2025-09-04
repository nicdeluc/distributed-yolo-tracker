import yaml  # Add this import to the top of your file


def load_config(config_path="config/config.yaml"):
    """
    Loads the YAML configuration file.
    """
    try:
        with open(config_path, "r") as f:
            # Use safe_load for security
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found at {config_path}")
        return None
    except Exception as e:
        print(f"ERROR: Failed to load or parse configuration file: {e}")
        return None
