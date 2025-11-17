"""
Way to easily get configuration values in a fast and dynamic way.

See [How To Use](#how-to-use) in README to get started fast.

# Importable Attributes

Here are a few special attributes at the top-level `xcon` module that you can easily import.

Go to [How To Use](#how-to-use) for more details on how to use this library.

- `xcon.config.Config`: Is the main class in by Config module, you can import easily it via

    ```python
    from xcon import Config
    ```

- `xcon.config.config`: It represents the currently active `xcon.config.Config`
    object.

    You can grab it via:

    ```
    from xcon import config
    ```

    For more details see:

       - Better Code Example: [Quick Start](#quick-start)

       - More about what the 'current config' is:  [Current Config](#current-config).

- `xcon.providers`: Easy access to the provider classes.
   See [Supported Providers](#supported-providers) for a list of providers.


- `xcon.config.ConfigSettings`: Used in projects to create a 'ConfigSettings' subclass.
    The subclass would allow you easily specify project xcon_settings to lazily lookup via Config.
"""
from .config import Config
from . import providers
from .config import config
from .config import ConfigSettings
from .conf import xcon_settings

__version__ = '1.1.0'
