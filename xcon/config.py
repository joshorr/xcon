"""
Main config module. Key pieces such as `xcon.config.Config` and
`xcon.config.config` are imported directly into "xcon".

Very quick example, this will grab `SOME_CONFIG_ATTR` for you:

>>> from xcon.config import config
>>> config.SOME_CONFIG_ATTR

.. todo:: Link to the readme.md docs

"""
import os
from copy import copy
from dataclasses import dataclass, field
from inspect import isclass
from typing import (
    Dict, List, Union, Optional, Tuple, Iterable, Type, Any, Callable, TypeVar
)

# Note: pdoc3 can't resolve type-hints inside of method parameters with this enabled.
#   disabling it. (leaving it here for future reference for others)
# from __future__ import annotations
from xinject import XContext, Dependency
from xsettings import Settings, SettingsField
from xsettings.retreivers import SettingsRetrieverProtocol
from xsentinels import Default
from .types import OrderedDefaultSet, OrderedSet
from xsentinels.default import DefaultType
from xbool import bool_value
from xloop import xloop

from logging import getLogger

from .directory import Directory, DirectoryItem, DirectoryListing, DirectoryOrPath, DirectoryChain
from .exceptions import ConfigError
from .provider import Provider, ProviderChain, ProviderCacher, InternalLocalProviderCache
from .providers import EnvironmentalProvider
from .providers import default_provider_types
from .providers.dynamo import DynamoCacher

xlog = getLogger(__name__)

T = TypeVar('T')


@dataclass(frozen=True, eq=False)
class _ParentCursor:
    parent: "Config"
    index: int
    chain: "_ParentChain"

    def next_cursor(self) -> Optional["_ParentCursor"]:
        chain = self.chain
        next_index = self.index + 1
        parents = chain.parents
        if next_index >= len(parents):
            return None
        next_config = parents[next_index]
        return _ParentCursor(parent=next_config, index=next_index, chain=chain)


@dataclass(frozen=True, eq=True)
class _ParentChain:
    parents: Tuple["Config"] = field(default_factory=list)

    def __post_init__(self):
        parents = self.parents
        if not isinstance(parents, tuple):
            # Convert to a tuple
            object.__setattr__(self, 'parents', tuple(xloop(parents)))

    def start_cursor(self) -> Optional[_ParentCursor]:
        """

        :return:
        """
        parents = self.parents
        if not parents:
            return None
        return _ParentCursor(parent=parents[0], index=0, chain=self)


def _check_proper_cacher_or_raise_error(cacher):
    """ Checks if passed-in value is a proper cacher value from user to Config;
        otherwise we raise an error.
    """
    if cacher is Default:
        return
    if cacher is None:
        return
    if isclass(cacher) and issubclass(cacher, ProviderCacher):
        return
    ConfigError(
        f"Provided cacher ({cacher}) to Config was NOT a ProviderCacher subclass type, "
        f"`Default` or `None`"
    )


class Config(Dependency):
    """
    Lets you easily get configuration values from various sources.

    You should read [Config Class Overview](#config-class-overview) first because it's a
    high-level overview of Config. Also, read the associated [Quick Start](#quick-start) that's
    there too. What you'll find below are implementation details that go into more depth on how
    Config works in various scenarios.

    .. todo::
        At some point in the future I would like to implement __getitem__ to have the Config class
        act sort of like a dictionary. If I did that, I would like the ability to iterate
        over all the current configuration key/values that the Config object knows about.
        Doing this would be a bit involved, so for now I am leaving dict/mapping like
        access non-implemented.
    """

    APP_ENV: Optional[str] = None
    """ Current application environment, this var only looks at
        the overrides, defaults and environmental variables. This will NOT look at providers
        when asked for.

        The reason for this is because the providers need the directories, and the default
        set of directories need `Config.APP_ENV` and `Config.SERVICE_NAME` in order to be created.

        This means the providers depend on this variable, and so it's special. Regardless of the
        providers set, or the directories set, this only looks in specific places.
        For details see [Service/Environment Names](#service-environment-names).
    """
    SERVICE_NAME: Optional[str] = None
    """ Current application/service name, this var only looks at
        the overrides, defaults and environmental variables. This will NOT look at providers
        when asked for.

        The reason for this is because the providers need the directories, and the default
        set of directories need `Config.APP_ENV` and `Config.SERVICE_NAME` in order to be created.

        This means the providers depend on this variable, and so it's special. Regardless of the
        providers set, or the directories set, this only looks in specific places.
        For details see [Service/Environment Names](#service-environment-names).
    """

    # These are guaranteed to be here after __init__
    # These contain the name/value pairs for our overrides and defaults.
    _override: DirectoryListing
    _defaults: DirectoryListing

    # Set in __init__, used to know if user wants us to user parent-chain or not.
    _use_parent: bool = True

    # These are here to store info from __init__, for lazy allocation when needed;
    # and to know what the user actually wanted [ie: Default, Blank list, None, Etc].
    _cacher: Union[DefaultType, None] = Default

    # These are also from __init__ [see last comment above _cacher]
    _providers: OrderedDefaultSet[Type[Provider]]
    _directories: OrderedDefaultSet[Directory]
    _exports: OrderedDefaultSet[Directory]

    @classmethod
    def current(cls):
        """ Calls 'cls.grab()', just am alternative name for the same thing, may make things
            a bit more self-documenting, since `Config` could be used in a lot of places.

        """
        return cls.grab()

    def __init__(
            self, *,
            directories: Union[Iterable[DirectoryOrPath], DefaultType] = Default,
            providers: Union[Iterable[Type[Provider]], DefaultType] = Default,
            cacher: Union[Type[DynamoCacher], DefaultType, None] = Default,
            use_parent: bool = True,
            parent: Any = Default,  # Note: This is *DEPRECATED*, see doc comment for details.
            defaults: Union[DirectoryListing, Dict[str, Any], DefaultType] = Default,
            service: str = Default,
            environment: str = Default
    ):
        """
        Create a new Config object. Normally you would just leave everything at their Default
        values. You can change any of them if needed. If you pass a None for any parameter
        that defaults to Default, that aspect will be disabled/not used. For example, if you
        pass a None for directories/providers, no directories/providers will be searched.

        Parameters
        ---------
        directories: Union[Iterable[xcon.directory.DirectoryOrPath], xsentinels.Default]
            List of directories/paths to search when querying for a name.
            If `xsentinels.Default`: Uses the first one from [Parent Chain](#parent-chain).
            If everyone in the parent chain is set to `Default`, uses `standard_directories()`.

            Various ways to change what directories to use:

            >>> my_directories = standard_directories(service='other_app', env=config.APP_ENV)
            >>> with Config(directories=my_directories):
            ...     config.SOME_VAR

            .. note:: This will also preserves the current service name
                As your just changing the directories used, and not the service name.
                This means the cache-path is not changed, so you don't have to add permissions
                to read/write other cache-path

            If you want to lookup the standard/default ones after, you can do this too:

            >>> my_directories = [
            ...     Directory(service='other_app', env=config.APP_ENV),
            ...     Directory(service='other_app'),
            ...     Default
            ... ]
            >>> with Config(directories=my_directories):
            ...     config.SOME_VAR

            When `Default` is resolved, after the ones your inserting your self,
            it will use the standard app service/env.

            This means it will first look for the two directiores first from other_app,
            and then if it still can't find the var it will next look at the current
            app/service for the var.

        providers: Union[Iterable[Type[[xcon.provider.Provider]], [xsentinels.Default]
            List of provider types to use. If set to `Default`, uses the first one from
            [Parent Chain](#parent-chain). If everyone in the parent chain is set to `Default`,
            uses `xcon.providers.default.default_provider_types`.

        cacher: Type[xcon.provider.ProviderCacher]
            In the future, I may allow other cachers to be passed in via this param, but right
            now only the DynamoCacher is used and the only values you can use are:

            - If `None`:
                - No flattened high-level caching will be used. The individual
                providers will still cache things internally per-directory/provider.

            - If left as `xsentinels.Default`:
                - Must have a service/enviroment we can use (ie: APP_ENV / SERVICE_NAME).
                If so, we will attempt to read/write to a special Dynamo table that has
                a flattened list of name/value pairs that are tied to the current service,
                enviroment, directory-chain, provider-chain at the time the value is asked for.

            The cacher-path will use current service/environment (SERVICE_NAME/APP_ENV).

            If you want change where you lookup variables without effecting the cacher-path,
            you can change the directories that Config uses.

            See below on `service` and `directories` paramters for examples/details.


        parent: Any
            .. deprecated:: v0.3.34

            Set `use_parent` instead of this. The `use_parent` param has taken this over.

            If `parent` is Default or a value that looks `True`, we will use whatever
            `use_parent` is set to. If it's a False like value, we will set use_parent to False.

        use_parent: bool
            [Parent Chain](#parent-chain) is used to find:

               - Overridden config values; these are values that set directly
                 on the Config object; ie: `xcon.config.config`.CONFIG_NAME = "Some Value to Override With"

               - Default values; these are used when config can find no other value for a
                 particular .CONFIG_NAME. See `set_default`

               - Default directories: Use parent directories by default.

               - Default providers: Use parent providers by default.

            The overridden/defaults/directory/providers 'inherit' up the config's
            [Parent Chain](#parent-chain).

            This makes it easy to override values in some parent... perhaps in a unit-test, or
            while a documentation generator is running, or if some library your calling
            wants to use a different set of providers, etc....

            If you pass a `use_parent=False`, no parent will be used or consulted. If anyone
            in the [Parent Chain](#parent-chain) has `use_parent==false`, the parent-chain
            will stop there.

            By `xsentinels.Default`:
               We lookup the parent by getting the current Config via current XContext;
               If that's ourselves, then we grab the parent context's Config resource.
               This lookup occurs every time we are asked for a .CONFIG_NAME to see if
               there is an override for it, etc. [see `parent is used to find` section above].
               That means the Config's parent can change depending on the current context the
               time the .CONFIG_NAME is asked for.

        defaults: Union[xcon.directory.DirectoryListing, Dict[str, Any], xsentinels.Default]
            Side Note:
            If a default is not provided for "APP_ENV", a "dev" default will be added for it.
            You can set your own default either via `defaults['APP_ENV'] = 'whatever'` or you
            can set it after creation via `Config().set_default("APP_ENV", 'whatever')`.
            Remember that all key/config names are case-insensitive when they are later looked
            up. Same with "SERVICE_NAME", we add a default for it as 'global' if a default is
            not defined by user of Config class.

            If `defaults` are provided, these values will be used when Config is asked for
            something that does not exist anywhere else. ie: Has not been overridden [by directly
            setting value on Config or a parent Config], and also not in any provider.

            Basically, if Config can't find a value anywhere else, it will as a last-resort
            check these defaults. If a value in defaults is present for the configuration
            name/key in question, the value in defaults will be returned.
            This default value is NOT cached via the DynamoCacher [in-fact, the DynamoCacher will
            cache the fact that the config var in question does not exist]. If the cacher reports
            that a particular var does not exist [reminder: the cache entries eventually expire]
            we skip checking the providers and just check the defaults.

            See the Config class doc, and the 'Search Order' section.

        environment: Dict[str, Default]
            Used to easily override the APP_ENV. Infact, `__init__` will simply do this
            if you provide a value for `environment`:

            >>> self.APP_ENV = environment

            Used when APP_ENV is needed, for everything from the cacher,
            to when constructing the default directory paths (ie: `/{SERVICE_NAME}/{APP_ENV}/...`)


        service: Dict[str, Default]
            Used to easily override the SERVICE_NAME. Infact, `__init__` will simply do this
            if you provide a value for `environment`:

            >>> self.SERVICE_NAME = service

            Used when SERVICE_NAME is needed, for everything from the cacher to know where to
            to when constructing the default directory paths (ie: `/{SERVICE_NAME}/{APP_ENV}/...`)

            If you want the cacher-path to be uneffected but you want to lookup settings
            from other app directory paths, you can do this sort of thing instead of changing
            the `service` / `SERVICE_NAME`:

            >>> my_directories = standard_directories(service='other_app', env=config.APP_ENV)
            >>> with Config(directories=my_directories):
            ...     config.SOME_VAR

            This preserves the current service name and so the cache-path is not changed.
            However, it will lookup the vars from the other directories, like you wanted.

            If you want to lookup the standard/default ones after, you can do this too:

            >>> my_directories = [
            ...     Directory(service='other_app', env=config.APP_ENV),
            ...     Directory(service='other_app'),
            ...     Default
            ... ]
            >>> with Config(directories=my_directories):
            ...     config.SOME_VAR

            When `Default` is resolved, after the ones your inserting your self,
            it will use the standard app service/env.

            This means it will first look for the two directiores first from other_app,
            and then if it still can't find the var it will next look at the current
            app/service for the var.

        """  # noqa
        super().__init__()

        self._override = DirectoryListing()
        self._defaults = DirectoryListing()

        # By default, we grab the ones from the parent chain and use them.
        self._exports = {Default: None}

        # This is for backwards-compatibility, at some point we will remove it.
        # see doc-comment for deprecation details.
        if parent is not Default and not parent:
            use_parent = False

        self._use_parent = use_parent

        # We lazy-lookup directories if it's Default, this is so you can directly override
        # APP_ENV and SERVICE_NAME if you want to easily change the defaults.
        # See 'self.directories' property.
        self.directories = directories

        # This property will lazily be used to create self.provider_chain when the chain
        # is requested for the first time.
        self._providers = {x: None for x in xloop(providers)}

        # We lazy-lookup cacher if it's Default or a Type.
        # See 'self.cacher' property.
        _check_proper_cacher_or_raise_error(cacher)
        self._cacher = cacher

        if isinstance(defaults, dict):
            for name, value in defaults.items():
                self.set_default(name, value)

        # if service provided, add an override for it.
        if service is not Default:
            self.SERVICE_NAME = service

        # if environment is provided, set it as an override.
        if environment is not Default:
            self.APP_ENV = environment

    @property
    def providers(self) -> Union[DefaultType, Iterable[Union[Type[Provider], DefaultType]]]:
        """ Lets you see providers set directly on this config object.

            If set to Default, it  means we look to our [Parent Chain](#parent-chain) first,
            and if one of them don't have any set to then use sensible defaults.

            Otherwise it's a list of `xcon.provider.Provider` types and/or Default.
        """
        return self._providers.keys()

    @property
    def directories(self) -> Union[DefaultType, Iterable[Union[Directory, DefaultType]]]:
        """ Lets you see directories set directly on this config object.

            If set to Default, it  means we look to our [Parent Chain](#parent-chain) first,
            and if one of them don't have any set to then use sensible defaults.

            Otherwise it's a list of `xcon.directory.Directory` and/or Default.
        """
        return self._directories.keys()

    @directories.setter
    def directories(
            self,
            value: Union[Iterable[Union[DefaultType, DirectoryOrPath]], DefaultType]
    ):
        """ List of all directories set on self, by default it's just `[Default]`.
            This DOES NOT resolve the `Default` if it's in the list.  That's resolved
            when you ask for the `Config.directory_chain`.
        """
        # make an ordered-set out of this.
        dirs: OrderedDefaultSet = {}
        for x in xloop(value):
            if x is not Default:
                x = Directory.from_path(x)
            dirs[x] = None

        self._directories = dirs

    @providers.setter
    def providers(self, value: Union[DefaultType, Iterable[Union[DefaultType, Type[Provider]]]]):
        """ List of all providers set on self, by default it's just `[Default]`.
            This DOES NOT resolve the `Default` if it's in the list.  That's resolved
            when you ask for the `Config.provider_chain`.
        """
        # make an ordered-set out of this.
        self._providers = {x: None for x in xloop(value)}

    def add_provider(self, provider: Type[Provider]):
        """ Adds a provider type to end of my provider type list [you can see what it is for
            myself via `Config.providers`].  By default, a Config object starts off with
            a provider list of just `[Default]`. By adding to the end of this, we still
            pick up the parent/default providers. This method simply appends to whatever
            we currently have.  If provider is already in list, nothing changes
            [ie: existing order will not change].
        """
        # If we already have it, no need to do anything else.
        if provider in self._providers:
            return

        # Add Provider type; using dict as an 'ordered set'; see xsentinels.OrderedSet.
        self._providers[provider] = None

    def add_directory(self, directory: Union[Directory, str, DefaultType]):
        """ Adds a directory to end of my directory list [you can see what it is for
            myself via `Config.directories`].  By default, a Config object starts off with
            a directory list of just `[Default]`. By adding to the end of this, we still
            pick up the parent/default directories.  If directory is already in list,
            nothing changes [ie: existing order will not change].
        """
        # If we already have it, no need to do anything else.
        if directory in self._directories:
            return

        # Add Directory; using dict as an 'ordered set'; see xsentinels.OrderedSet
        self._directories[directory] = None

    def add_export(self, *, service: str):
        """
        These are added to the `Config.directory_chain` after the normal directories from
        `Config.directories`. The purpose of these are to see 'exported' values from other
        services.  We currently use the current `Config.APP_ENV` when looking at
        the exported values for a service.

        Directories that are created in the `Config.directory_chain` from these exports follow
        this pattern:

        "/{service}/export/{`Config.APP_ENV`}"


        By default, the export list is just this:

        ( `xsentinels.Default`, )

        When you add more exports via `Config.add_export`, it will append to the end of this list.
        That way we still add whatever we need from parent and then an explicitly added to self.

        If you want to remove the [Default] option, see `Config.set_exports`.

        .. todo:: Someday in the future, we will probably add other parameters to override
            what service to use.

        Args:
            service: Name of the service you want exported values from.
                We currently use the environment that the Config object sees. At some point in
                the future we may support also adding an explict environment here as well
                (so you don't have to use the 'current' environment name, ie: testing/prod/etc;
                you could use whatever you want).
        """
        # This is an OrderedDefaultSet, add in the service...
        self._exports[service] = None

    def set_exports(self, *, services: Iterable[Union[str, DefaultType]]):
        """
        This allows you to set all of the exports. Right now
        we only support setting them by service [and not environment]. See `Config.add_export`
        for more details.

        This replaces all current services. By default, the export list is this:

        ( `xsentinels.Default`, )

        Which means, we ask the parent chain for an exports. If you set the exports without
        including this then the parent-chain won't be consulted.

        Args:
            services (Iterable[Union[str, `xsentinels.Default`]]): List of exports you want
                to add by service name. If you don't add the `Default` somewhere in this list
                then we will NOT check the parent-chain
        """
        self._exports = {x: None for x in xloop(services)}

    def get_exports_by_service(self):
        """ List of services we current check their export's for. This only lists the exports
            directly assigned to self (not in the [Parent Chain](#parent-chain)). Allows you to
            find out what this config object as set directly on it for which exports we
            look for per-service.
        """
        return self._exports.keys()

    def set_override(self, name, value: [Any, Default]):
        """
        Sets an override on self. When someone asks for this value, this will be returned
        regardless of what any provider or environmental variable as set.

        You can also set an override by setting a value for a config-name directly on `Config`
        via this syntax:

        >>> from xcon.config import config
        >>> config.SOME_OVERRIDE_NAME = "my override value"


        .. warning:: When doing it this way the first-char in the name must be upper-case.

        When using `set_override` you can use whatever case you want.

        For details see [Naming Rules](#naming-rules).

        .. important:: This will also effect child config objects!
            They will look for overrides set on a parent before looking at any providers.

            For more details see [Parent Chain](#parent-chain) and [Overrides](#overrides) topics.

        Args:
            name: Name of the item to remove, case-insensitive.
            value (Union[Any, xsentinels.Default]): Can be any value. If Default is used
                we will instead call `Config.remove_override(name)` for you to remove the value.
        """
        if value is Default:
            self.remove_override(name)
            return

        # Checked for default already, from this point forward it's just `Any` type.
        value: Any
        override_item = DirectoryItem(
            directory="/_override", name=name, value=value, source=f"Config.set_override",
            cacheable=False
        )

        xlog.info(f"Setting Config override for item ({override_item}).")
        self._override.add_item(
            override_item
        )

    def get_override(self, name) -> Union[Any, DefaultType, None]:
        """
        Returns a value of override for `name` was directly set on this config object
        in one one of two ways:

        - `config.set_override`
        -  `config.SOME_VAR = "a-value"`

        The returned value is `xsentinels.Default` if no override is found;
        this is so you can distinguish between overriding to None or no override set at all
        (`xsentinels.Default` evaluates to `False`, just like how `None` works).

        .. warning:: Only returns a value if overrides was directly set on self!

            (ie: **won't** consult the [Parent Chain](#parent-chain)).
            The parent chain (parent configs) are consulted when looking up a config value
            normally via `Config.get`. Overrides in self and then in parents are checked first.

            `get_override` method is here so you can examine a specific `Config` object and
            determine if there are any overrides set directly on it.

        Attributes:
            name (str): Name to use to get override [case-insensitive].

        Returns:
            Union[Any, xsentinels.Default]: The value, or `xsentinels.Default` if no value was
                set for `name`. This allows you to distinguish between overriding a value to
                `None` and no override being set in the first place
                (`xsentinels.Default` evaluates to `False`, just like how `None` works).
        """
        item = self._override.get_item(name)
        if item:
            return item.value
        return Default

    def remove_override(self, name):
        """
        Remove override **ONLY** on self.
        This will not remove overrides from a parent.

        .. warning:: This WON'T effect any override set on a parent!
            see [Parent Chain](#parent-chain).

        Someday we may make it easier to publicly go though the parents
        (right now there are internal/private methods that do this).

        If you don't like an override, you can override the override by setting an override
        on a child/current `Config` object (see `Config.set_override`).

        Probably should not mess with config objects from higher up that you don't know
        anything about in any case.  That's why I've hesitated about publicly exposing
        the parent chain too much.


        You can remove overrides in various ways, such as:

        ```python
        from xcon import config
        from xsentinels import Default

        # Alternate Method 1:
        config.SOME_NAME = Default

        # Alternate Method 2:
        config.set_override("SOME_NAME", Default)
        ```

        At the moment these ways ^ will not remove an override from a parent.

        If we do decide we want an ability  to "white-out" an override;
        I would probably do it such that you could tell a child to not check parent(s)
        overrides on a specific value
        (ie: I would set the override value to `Default` on self internally, to indicate that).
        """
        xlog.info(f"Removing Config override for name ({name}).")
        self._override.remove_item_with_name(name=name)

    @property
    def service(self) -> Union[DefaultType, str]:
        """
        Returns the value passed into __init__ for `service`, or any overridden value set
        for 'SERVICE_NAME' directly on self. This method WON'T check the
        [Parent Chain](#parent-chain). That way you can see exactly what was configured/directly
        set on the Config object it's self.

        If you passed in `service` to Config() during creation, it will set it as an
        [override](#overrides) like so: `self.SERVICE_NAME="some-service"`.

        ```python
        # Ways to override service on a Config object.
        config.SERVICE_NAME = "some-service"
        config.service = "some-service"
        config = Config(service="some-service")
        ```

        If it was not overridden, then returns `Default`. This is the default value. You can
        set the service via `config.service = Default` to remove any overridden and return
        to having it lookup the service like normal.

        ```python
        # You can remove the override and have it go back to normal like so:
        config.service = Default.

        # That ^ just does this for you:
        config.remove_override("SERVICE_NAME")

        # That ^ just does this for you:
        self.set_override("SERVICE_NAME", Default)

        # That ^ in turn does this for you:
        config.remove_override("SERVICE_NAME")
        ```

        If your interested it knowing what it's current using as the service name, you could
        take a look at `config.SERVICE_NAME`. That will check the [Parent Chain](#parent-chain)
        if needed. You could also ask for the `Config.directory_chain` and see what the first
        Directory in the chain has for the service
        `xcon.directory.Directory.service`.
        """
        item = self._override.get_item('service_name')
        if item:
            return item.value
        return Default

    @property
    def environment(self) -> str:
        """
        Returns the value passed into __init__ for `environment`, or any overridden value set
        for 'APP_ENV' directly on self. This method WON'T check the [Parent Chain](#parent-chain).
        That way you can see exactly what was configured/directly set on the Config object
        it's self.

        If you passed in `environment` to Config() during creation, it will set it as an
        [override](#overrides) like so: `self.APP_ENV="joshDev"`.

        ```python
        # Ways to override environment on a Config object.
        config.APP_ENV = "joshDev"
        config.service = "joshDev"
        config = Config(service="joshDev")
        ```

        If it was not overridden, then returns `Default`. This is the default value. You can
        set the service via `config.environment = Default` to remove any overridden and return
        to having it lookup the service like normal.

        ```python
        # You can remove the override and have it go back to normal like so:
        config.environment = Default.

        # That ^ just does this for you:
        self.set_override("APP_ENV", Default)

        # That ^ in turn does this for you:
        config.remove_override("APP_ENV")
        ```

        If your interested it knowing what it's current using as the environment name, you could
        take a look at `config.APP_ENV`. That will check the [Parent Chain](#parent-chain)
        if needed. You could also ask for the `Config.directory_chain` and see what the first
        Directory in the chain has for the environment
        `xcon.directory.Directory.env`.
        """
        item = self._override.get_item('app_env')
        if item:
            return item.value
        return Default

    @environment.setter
    def environment(self, value):
        """ See `Config.environment getter for details. """
        self.set_override("APP_ENV", value)

    @service.setter
    def service(self, value):
        """ See `Config.service getter for details. """
        self.set_override("SERVICE_NAME", value)

    @property
    def cacher(self) -> Optional[Union[Type[DynamoCacher], DefaultType]]:
        """ Returns what was originally passed into __init__ for `cacher`.
            It's here so you can see how this Config object was originally configured.
        """
        return self._cacher

    @cacher.setter
    def cacher(self, value: Union[Type[DynamoCacher], DefaultType, None]):
        """ Returns what was originally passed into __init__ for `cacher`.
            It's here so you can see how this Config object was originally configured.
        """
        _check_proper_cacher_or_raise_error(value)
        self._cacher = value

    @property
    def resolved_cacher(self) -> Optional[ProviderCacher]:
        """
        Returns the cacher object that is currently being used when config values are asked
        for; at the time this is called.
        This can change later if a config object or current context is changed.

        If environmental variable CONFIG_ONLY_ENV is set to true (looked at via `os.environ` ONLY),
        we will only ever return None for the resolved cacher to use no matter what
        parent-config / self's `Config.cacher` have been set with.
        """
        return self._cacher_with_cursor(cursor=self._parent_chain().start_cursor())

    @property
    def provider_chain(self) -> ProviderChain:
        """
        `xcon.provider.ProviderChain` we are currently using.
        This is effected by what was passed into Config when it was created.
        If it was left as `xsentinels.Default`, we will get the value via the
        [Parent Chain](#parent-chain).

        See `Config` for more details.

        If environmental variable CONFIG_ONLY_ENV is set to true (looked at via `os.environ` ONLY),
        we will only have the EnvironmentalProvider in the used/returned provider chain
        no matter what parent-config / self's `Config.providers` have been set with.
        """
        return self._provider_chain_with_cursor(cursor=self._parent_chain().start_cursor())

    @property
    def directory_chain(self) -> DirectoryChain:
        """
        `xcon.directory.DirectoryChain` we are currently using.
        This is effected by what was passed into Config when it was created.
        If it was left as `xsentinels.Default`, we will get the value via the
        [Parent Chain](#parent-chain).

        See `Config` for more details.
        """
        return self._directory_chain_with_cursor(cursor=self._parent_chain().start_cursor())

    @property
    def use_parent(self) -> bool:
        """
        If `True`: we will use the [Parent Chain](#parent-chain) when looking up things such as the
        `Config.provider_chain`. as an example; if it was left as `xsentinels.Default`
        when `Config` object was created.

        If `False`: the parent will not be consulted, and anything that was not set at creation
        or added/set after creation will use the default values. See `Config` for details.

        See [Parent Chain](#parent-chain) for more details about how config-parents works.
        """
        return self._use_parent

    def set_default(self, name: str, value: Optional[Any]):
        """
        When someone tries to lookup a config value [perhaps via `Config.get`] and if a value
        is not found anywhere... But someone called this to define a default for it we return
        the default value set here [or passed in via Config.__init__(defaults={...})].

        For a few examples of how this can be used, see `Config`, Search Order section.
        Also see Config.__init__(...) doc for 'defaults' param.

        Args:
            name (str): Case-insensitive name for the default config.
            value (Optional[Any]): Default value, can be anything [but are generally strings].
                If you provide None for this value param, that will be stored and will be returned
                if a default is needed for param [you can use this feature to override a
                parent-config default to None if needed].

        """
        if value is Default:
            self.remove_default(name)
            return

        default_item = DirectoryItem(
            directory="/_default/user-set", name=name, value=value, source=f"config.set_default",
            cacheable=False
        )

        xlog.info(
            "Setting Config default for item ({default_item}).",
            extra=dict(default_item=default_item)
        )
        self._defaults.add_item(default_item)

    def get_default(self, name: str) -> Optional[Any]:
        """
        Returns the default for 'name' if it was set via `Config.set_default()`. It only returns
        one if it was directly set on self. This means it **WON'T** consult
        the [Parent Chain](#parent-chain)). This is so you can more easily find/set defaults
        in the parent-chain your self if you need to track something down or some such.

        Most of the item you should just be able to use `Config.set_default` and not worry about
        an existing default set on us or some other `Config` object.

        Attributes:
            name (str): Name to use to get default [case-insensitive].

        Returns:
            Union[Any, None, xsentinels.Default]: The value, or Default if no default
                is set for name. This allows you to distinguish between defaulting a value to
                None and no default being set in the first place (`xsentinels.Default`
                looks like `False`, just like how `None` works).
        """
        item = self._defaults.get_item(name)
        if item:
            return item.value
        return Default

    def remove_default(self, name):
        """
        Remove default on self.

        .. warning:: This WON'T affect any default set on a parent,
            see [Parent Chain](#parent-chain).

        You can also call this other ways, such as:

        ```python
        from xcon import config
        from xsentinels import Default

        # Alternate Method 1:
        config.set_default("SOME_NAME", Default)
        ```
        """
        xlog.info(f"Removing Config default for name ({name}).")
        self._defaults.remove_item_with_name(name=name)

    def get(
            self,
            name: str,
            default=None,
            *,
            skip_providers: bool = False,
            skip_logging: bool = False,
            ignore_local_caches: bool = False
    ) -> Optional[str]:
        """
        Similar to dict.get(), provide name [case-insensitive] and we call `Config.get_item()`
        and return the `xcon.directory.DirectoryItem.value` of the item returned,
        or passed in `default=None` if no item was found.

        See documentation for `Config.get_item()` for more details and to find out more
        about the `skip_providers` option.

        Attributes:
            name (str): Name of the config value to lookup. Name can be of any case since
                lookup is case-insensitive. But if you can keep it all lower case it could be
                a bit more efficient, since it would not have to change it.

            default: Value to return if we don't find a config value via the normal means.

            skip_providers (bool): See self.get_items() for more details, suffice it to
                say it only returns things directly set/overridden or defaulted on self or on
                parent-chain [without consulting the providers and directories].

            skip_logging (bool): Skips logging about where we got the config value.

            ignore_local_caches (bool): allows you to ignore the local memory cache
                (as a convenience option).

                Right now it does this by resetting the entire cache for you before lookup.
                But in the future if needed, it may be more precise about what it does and may just
                retrieve that specific value from each provider until it finds the value
                (vs resetting the entire cache and bulk retrieving everything all over again).

                Mostly depends on how often we would really need to do this in the future.
                I am guessing it would be rare so the current implementation should be good enough
                for now.
        """
        if ignore_local_caches:
            InternalLocalProviderCache.grab().reset_cache()

        item = self.get_item(name=name, skip_providers=skip_providers, skip_logging=skip_logging)
        if item:
            value = item.value
            return value if value is not None else default
        return default

    def get_bool(self, name: str, default=False):
        """
        Grabs config variable for `name` and does it's best to convert it to a boolean if possible.
        If the value is:

        - None: we return `default`.
        - str: We run it though `distutils.util.strtobool` to convert it to a bool.
        - Any: Anything else, we simply call `bool(value)` on it.
        - If there is any ValueError while try to convert value, we return False.

        Args:
            name (str): Name of the config value, such as `DISABLE_DB`.
            default: If we can't find a value, what should we use? By default, it's False.

        Returns:
            bool:  We found a bool value, or you provided a boolean `default` value.
            default: This means that we could not find a config value, so return `default`;
                which defaults to False
        """
        value = self.get(name)
        if value is None:
            return default
        return bool_value(value)

    def get_value(self, *args, **kwargs) -> Optional[str]:
        """
        .. deprecated:: Deprecated in favor of using `Config.get()`.
            Right now we simply call `Config.get()` with same arguments for you and return result.
        """
        return self.get(*args, **kwargs)

    def get_item(
            self, name: str, *,
            skip_providers: bool = False,
            skip_logging: bool = False,
    ) -> Optional[DirectoryItem]:
        """
        Gets a DirectoryItem for name. If the value does not exist, we will still return a
        `xcon.directory.DirectoryItem` with a
        `xcon.directory.DirectoryItem.value` == `None`. This is because we cache the
        non-existence of items for performance reasons. This allows you to see
        where the None value came from via the `xcon.directory.DirectoryItem.directory`
        attribute.

        Attributes:
            name (str): Name to look for [will be used in a case-insensitive manner].

            skip_providers (bool): If False [default], checks all sources for the config
                values. If True, only checks for things overridden on self or a parent;
                [ie: Things directory set on self or directly on a parent Config].
                It will consult any defaults (`Config.get_default()`) if needed.

            skip_logging (bool): Skips logging about where we got the config value.

        Returns (Optional[DirectoryItem]):
            If None [only happens when skip_providers is True]; then no override/default was found.

            Otherwise returns the item as a DirectoryItem. A DirectoryItem.value can be None.
            This means that the value is None [either it could not find it or the value
            was really set to a `None`].
        """
        # todo: Someday, use a special str subclass that will indicate that it's already in
        #       lower-case format and use that instead [therefore, we can skip lower-casing it
        #       again and again as we pass the already lower-cased name along to other methods].
        name = name.lower()
        cursor = self._parent_chain().start_cursor()

        # We currently have two special variables that we should NEVER lookup via the
        # provider chain and always look just in the environment variables/overrides/defaults for.
        # They also have hard-defaults that we use if we can't find a value. These special
        # methods do the correct thing, so use them if the user asks for the values
        # (internally in Config, we always just use these special private methods).

        # app_env/service_name are fundamental variables; don't log out every time we get it
        # (also used by logging system, so don't log out when it reads it)
        if name == 'app_env':
            return self._environment_with_cursor(
                cursor=cursor,
                as_item=True,
                skip_source_logging=skip_logging
            )

        if name == 'service_name':
            # Fundamental variable, don't log out every time we get it
            # (also used by logging system, so don't log out when it reads it)
            return self._service_with_cursor(
                cursor=cursor,
                as_item=True,
                skip_source_logging=skip_logging
            )

        # Otherwise, we follow standard process.
        return self._get_item(
            name=name,
            skip_providers=skip_providers,
            cursor=self._parent_chain().start_cursor(),
            skip_source_logging=skip_logging
        )

    def _providers_with_cursor(self, cursor: Optional[_ParentCursor]) -> List[Provider]:
        pass

    def _resolve_providers_with_cursor(
            self, cursor: Optional[_ParentCursor]
    ) -> OrderedSet[Type[Provider]]:
        if _env_only_is_turned_on():
            # We also disable cacher, see other place we call the `_env_only_is_turned_on` method.
            return {EnvironmentalProvider: None}

        return self._resolve_attr_values_with_cursor(
            cursor=cursor,
            attribute_name="_providers",
            defaults_factory=lambda: default_provider_types
        )

    def _resolve_directories_with_cursor(
            self,
            cursor: Optional[_ParentCursor],
            service: Union[str, DefaultType, None] = Default,
            environment: Union[str, DefaultType, None] = Default
    ) -> OrderedSet[Directory]:
        # Making it a callable to make it lazy.

        def defaults_factory():
            return self._standard_directories(
                cursor=cursor,
                service=service,
                environment=environment
            )

        directories = self._resolve_attr_values_with_cursor(
            cursor=cursor,
            attribute_name="_directories",
            defaults_factory=defaults_factory
        )

        exported = self._resolve_attr_values_with_cursor(
            cursor=cursor,
            attribute_name="_exports",
            defaults_factory=tuple  # Fast, empty iterable
        )

        if exported:
            if not environment:
                environment = self._environment_with_cursor(cursor=cursor)
            # Any new values will be added to end, nothing will happen to order of existing ones.
            for x in exported:
                directories[Directory(service=x, env=environment, is_export=True)] = None

        directories = {
            k.resolve(service=service, environment=environment): None for k in directories
        }

        return directories

    def _resolve_attr_values_with_cursor(
            self,
            cursor: Optional[_ParentCursor],
            attribute_name: str,
            defaults_factory: Callable[[], Iterable[T]]
    ) -> OrderedSet[T]:
        """ Internally, we are using a dict as an ordered-set, python 3.7 guarantees dicts
            keep their insertion order.

            This will return an ordered-dict, where the keys are the values. This function
            will resolve any 'Default' values encountered with their parent version.
        """
        default = Default

        values: OrderedDefaultSet[T] = getattr(self, attribute_name)
        if default not in values:
            # Ensure we don't accidentally modify this ordered set somewhere else.
            return copy(values)

        if cursor:
            parent_values = cursor.parent._resolve_attr_values_with_cursor(
                cursor=cursor.next_cursor(),
                attribute_name=attribute_name,
                defaults_factory=defaults_factory
            )
        else:
            parent_values = {x: None for x in defaults_factory()}

        # We have a default we need to 'insert' our parent providers into....
        # First we check to see if we only have 'Default'...

        if len(values) == 1:
            # If we only have one value, it's only value is 'Default', so easy, just return
            # what we have and move on.
            return parent_values

        # If we have more then just 'Default', we replace it with parent providers...
        final_values: OrderedSet[T] = {}
        for p in values:
            if p is default:
                final_values.update(parent_values)
            else:
                final_values[p] = None

        return final_values

    def _provider_chain_with_cursor(self, cursor: Optional[_ParentCursor]) -> ProviderChain:
        """
        I first check to see if I have/use a parent and our provider list is Default;
        if that's the case we return the parent Config's provider_chain.

        Otherwise we need to create a provider_chain and cache/return that now and in the future.
        """

        # Note from Josh: Keep things simple for now, just create provider chain when needed.
        #
        # if we find creating/finding the provider chain takes to long, then we can cache
        # the chains by provider values. We could also keep them around and reset them if
        # any of our parent's providers are changed, etc. I decided that it's probably not
        # expensive and so not to pre-optimize and just worry about it down the road if that's
        # not the case anymore.

        provider_types = self._resolve_providers_with_cursor(cursor=cursor)
        return ProviderChain(providers=provider_types)

    def _cacher_with_cursor(
            self,
            cursor: Optional[_ParentCursor]
    ) -> Optional[DynamoCacher]:
        # if user set cacher to None, they don't want caching enabled, so return None.
        cacher = self._cacher
        if cacher is None:
            return None

        # if user wants to force only the environmental provider to be used, disable cacher too.
        if _env_only_is_turned_on():
            return None

        # If we have a parent, and user wants the Default cacher, ask the parent for it.
        if cursor and cacher is Default:
            return cursor.parent._cacher_with_cursor(cursor=cursor.next_cursor())

        # If cacher is Default, right now the only supported cacher type is DynamoCacher.
        if cacher is Default:
            # We don't check self, only an environmental variable for this.
            # This is so you don't have to modify the code to disable cacher by default.
            # If you want to disable cacher via code, do this instead:
            #
            #  with Config(cacher=None):
            #      pass
            #
            # or
            #
            #  @Config(cacher=None)
            #  def some_method():
            #      pass
            #
            # BUT if someone passes `Config(cacher=DynamoCacher)` explicitly we will use that
            # regardless of what `CONFIG_DISABLE_DEFAULT_CACHER` is set too.
            #
            # Lower-casing it because `EnvironmentalProvider` will do that for us when looking it
            # up (it looks it up in a case-insensitive manner).
            # Trying to make it a tiny bit more efficient since this is called a lot.
            env_provider = EnvironmentalProvider.grab()
            if bool_value(env_provider.get_value_without_environ("config_disable_default_cacher")):
                return None
            cacher = DynamoCacher

        # We only accept types at this point [we already handled None and Default cases above ^],
        # the idea is to use it as a resource, so that we can have multiple config objects
        # use the same 'cacher' type.  Right now, only DynamoCacher is even supported,
        # this is more of a sanity check. If we ever have other ProviderCacher subclasses in
        # the future, we can update this to be more open [but should check for inspect.isclass
        # in that future, we want only class types from the user at this point].
        if cacher is not DynamoCacher:
            raise ConfigError(
                f"Trying to get the cacher, but the type the user wants to use is not a "
                f"DynamoCacher type: ({cacher})  In the future I may support other cacher "
                f"types; but right now we only support either None, Default or "
                f"xcon.providers.dynamo.DynamoCacher."
            )

        # Grab the current cacher resource, it's a ProviderCacher type of some sort and
        # so is a xinject.dependency.Dependency
        # (right now, cacher can only be a DynamoCacher type;
        # although we can change that in the future if we decide to change how caching works)
        return cacher.grab()

    def _get_item(
            self, name: str, *,
            skip_providers: bool = False,
            skip_defaults: bool = False,
            cursor: Optional[_ParentCursor],
            skip_source_logging: bool = False,
    ) -> Optional[DirectoryItem]:

        item = None
        provider_chain = None
        directory_chain = None
        try:
            item = self._override.get_item(name)
            if not item and cursor:
                item = cursor.parent._get_item(
                    name=name,
                    skip_providers=True,
                    skip_defaults=True,
                    cursor=cursor.next_cursor(),
                    skip_source_logging=skip_source_logging
                )

            if item:
                return item

            # Check to see if we are skipping providers, this happens when we only want to look
            # at overrides and/or default values to fulfill the request. This mostly only happens
            # for 'app_env' and 'service_name' config vars.
            if not skip_providers:
                # We skip logging about this, since we normally don't care... Just a lot of extra
                # useless log messages about where we keeping getting the service or environment
                # from.
                service = self._service_with_cursor(cursor=cursor, skip_source_logging=True)
                environment = self._environment_with_cursor(
                    cursor=cursor,
                    skip_source_logging=True
                )

                cacher = None

                # We will disable caching if we don't have a defined service (ie: 'global' service)
                if not service or service != "global":
                    cacher = self._cacher_with_cursor(cursor=cursor)

                directory_chain = self._directory_chain_with_cursor(
                    cursor=cursor,
                    service=service,
                    environment=environment
                )
                provider_chain = self._provider_chain_with_cursor(cursor=cursor)

                cache_dir = None
                use_cacher = bool(cacher and provider_chain.have_any_cachable_providers)
                if use_cacher:
                    # todo: Consider passing this into _directory_chain_with_cursor instead
                    #   of the individual components.
                    cache_dir = Directory.from_components(service=service, environment=environment)
                else:
                    cacher = None

                item = provider_chain.get_item(
                    name=name,
                    directory_chain=directory_chain,
                    cacher=cacher,
                    environ=cache_dir
                )

            if skip_defaults:
                # If they skip defaults then return None...
                # with skip_defaults == False: We return a DirectoryItem with None as the value.
                # todo: Double check to see if we want to return item vs None
                #   [adjust comment just above to reflect decision].
                return item

            if not item or (item.value is None and item.directory.is_non_existent):
                # Check for default values next...
                default_item = self._get_default_item_with_cursor(name=name, cursor=cursor)
                if default_item:
                    item = default_item
        finally:
            # We normally only want to log about things the users actually requests,
            # and not things used to fulfill the request.
            if not skip_source_logging:
                self._log_about_item_retrieval(name, item, directory_chain, provider_chain)

        return item

    # noinspection PyMethodMayBeStatic
    def _log_about_item_retrieval(
        self,
        original_name: str,
        item: DirectoryItem,
        directory_chain: DirectoryChain = None,
        provider_chain: ProviderChain = None
    ):
        env_only_enabled = _env_only_is_turned_on()

        if item and not item.directory.is_non_existent:
            # FYI: What's nice about doing it this way are these string formatting placeholders
            # will only evaluated if log message is actually emitted.
            # This logging message could be called a lot.
            xlog.debug(
                "Config found ({config_var_name}); returned {config_item}; extra metadata {meta}; "
                f"env_only_enabled({env_only_enabled}).",
                extra=dict(
                    config_var_name=original_name,
                    config_item=item,
                    meta=item.supplemental_metadata,
                )
            )
        elif item:
            directories = directory_chain.directories if directory_chain else []
            providers = provider_chain.providers if provider_chain else []

            supplemental_msg = ""
            if item.from_cacher:
                supplemental_msg = f"non-existence entry was found in cacher; "

            xlog.debug(
                "Config not found ({config_var_name}); "
                f"{supplemental_msg}"
                "in directories ({directories}), "
                "for providers ({providers}); extra metadata ({meta}); "
                f"env_only_enabled({env_only_enabled}).",
                extra=dict(
                    config_var_name=original_name,
                    directories=[d.path for d in directories],
                    providers=[p.name for p in providers],
                    source=item.source,
                    meta=item.supplemental_metadata,
                )
            )

    def _get_default_item_with_cursor(
            self, name: str, cursor: Optional[_ParentCursor]
    ) -> Optional[DirectoryItem]:
        item = self._defaults.get_item(name=name)
        if item:
            return item

        if cursor:
            return cursor.parent._get_default_item_with_cursor(
                name=name,
                cursor=cursor.next_cursor()
            )

        return None

    def _parent_chain(self) -> _ParentChain:
        """
            See [Parent Chain](#parent-chain).

            There is a concept of a parent-chain with Config if the Config object has
            their `use_parent == True` [it defaults to True]. We use the current XContext to
            construct this parent-chain. See [parent-chain].

            The parent-chain starts with the config resource in the current XContext.
            If that context has a parent context, we next grab the Config resource from
            that parent context and check it's `Config.use_parent`. If True we keep doing
            this until we reach a XContext without a parent or a `Config.use_parent` that is False.

            We take out of the chain any config object that is myself. The only objects in
            the chain are other Config object instances.

            The parent chain is generally consulted when we encounter a `Default` value.
            If when reaching the last parent in the chain, we still have a `Default` value,
            sensible/default values are constructed [if they have not already been] and used.
        """
        use_parent = self._use_parent
        found_self = False
        skip_adding_more_parents = False

        chain = []
        for config_resource in XContext.grab().dependency_chain(Config, create=True):
            if config_resource is self:
                found_self = True
                if not use_parent:
                    break
                continue

            if skip_adding_more_parents:
                continue

            chain.append(config_resource)
            if not config_resource.use_parent:
                skip_adding_more_parents = True
                if use_parent:
                    # We don't need to go any further, we want to use parents and
                    # we found a parent that does not, just return what we have.
                    break
                # We keep going to see if we can find our selves, but we don't add
                # anymore to the chain. If we can't find our selves as a resource
                # in the current context parent-chain, we will return a blank chain.
                continue

        # If we did not find self and we don't want to use a parent, we return a blank parent
        # chain. This is because we are not in the current config context hierarchy, and so are
        # a 'separate' island and are cut-off from all other config objects.
        if not use_parent and not found_self:
            return _BlankParentChain

        return _ParentChain(parents=tuple(chain))

    def _directory_chain_with_cursor(
            self,
            cursor: Optional[_ParentCursor],
            service: Union[str, DefaultType, None] = Default,
            environment: Union[str, DefaultType, None] = Default,
    ) -> Optional[DirectoryChain]:
        directories = self._resolve_directories_with_cursor(
            cursor=cursor,
            service=service,
            environment=environment
        )

        # Return a blank directory chain, they gave us a 'blank' list of directories.
        return DirectoryChain(directories=directories)

    def _standard_directories(
            self,
            cursor: Optional[_ParentCursor],
            service: Union[str, DefaultType, None] = Default,
            environment: Union[str, DefaultType, None] = Default
    ) -> OrderedSet[Directory]:
        if service is Default:
            service = self._service_with_cursor(cursor=cursor)
        if environment is Default:
            environment = self._environment_with_cursor(cursor=cursor)
        return standard_directories(service=service, env=environment)

    def _service_with_cursor(
            self,
            cursor: Optional[_ParentCursor],
            skip_source_logging: bool = False,
            as_item: bool = False
    ) -> Union[DirectoryItem, str]:
        return self._get_special_non_provider_item_with_cursor(
            name='service_name',
            hard_default="global",
            cursor=cursor,
            skip_source_logging=skip_source_logging,
            as_item=as_item
        )

    def _environment_with_cursor(
            self,
            cursor: Optional[_ParentCursor],
            *,
            skip_source_logging: bool = False,
            as_item: bool = False
    ) -> Union[DirectoryItem, str]:
        return self._get_special_non_provider_item_with_cursor(
            name='app_env',
            hard_default="dev",
            cursor=cursor,
            skip_source_logging=skip_source_logging,
            as_item=as_item
        )

    def _get_special_non_provider_item_with_cursor(
            self,
            name: str,
            hard_default: str,
            cursor: Optional[_ParentCursor],
            *,
            skip_source_logging: bool = False,
            as_item: bool = False
    ) -> Union[DirectoryItem, str]:
        """
        Returns an item/value by searching for 'name' without using providers.
        If we can't find a value, or the value we find is false we use the provided hard_default.

        Args:
            name: Name to look for [case-insensitive]
            hard_default: Default to use if we can't find a non-false like value.
            cursor: Current cursor we are using, see `_ParentCursor` for more details.
            skip_source_logging: Don't log where we got this from
                (if this is used to get something else, limits excessive logging].
            as_item: Return `DirectoryItem` if true, else we return just the value.
        """
        # We need to use internal method to preserve the cursor.
        item = self._get_item(
            name,
            skip_providers=True,
            cursor=cursor,
            skip_source_logging=skip_source_logging
        )

        if item and item.value:
            if as_item:
                return item
            return item.value

        item = EnvironmentalProvider.grab().get_item_without_environ(name)
        if not item or not item.value:
            item = DirectoryItem(
                directory="/_default/hard-coded",
                name=name,
                value=hard_default,
                source=f"config.hard-coded-default={hard_default}",
                cacheable=False
            )

        return item if as_item else item.value

    def __getattribute__(self, name: str):
        # Must start with an UPPER-CASE for user-config name vs object attribute name.
        # If user has some other case, they can always use `get(...)` directly;
        # but keep in mind that user-config names are case-insensitive.
        if name[0].isupper():
            return self.get(name)

        # Do the normal object attribute lookup.
        return object.__getattribute__(self, name)

    def __setattr__(self, key, value):
        # Must start with an UPPER-CASE for user-config name vs object attribute name.
        # If user has some other case, they can always use `set_override(...)` directly;
        # but keep in mind that user-config names are case-insensitive.
        if key[0].isupper():
            self.set_override(key, value)
            return
        return object.__setattr__(self, key, value)


# Allocate a ready-to-go default config object, see documentation above near start of file
# for details on what this is and how to use it.
#
# noinspection PyRedeclaration
config = Config.proxy()
"""
This will be an alias for the current Config object. Every time you ask it for something,
it looks up the current Config object and gets it from that. This means you can use this
directly as-if it's a `Config` object. Anytime you use it, it will lookup the current config
object and use that to get the attribute/method you want.

Example use case:

```python
    from xcon import config
    value = config.SOME_VAR
```
"""

Config.grab()


def _env_only_is_turned_on() -> bool:
    # Could have used `get_value_without_environ("config_env_only")` on EnvironmentalProvider,
    # (like I did with `config_disable_default_cacher`) but decided to just check environ directly
    # each time, for this exact case.  It could be something a developer would enable after
    # the EnvironmentalProvider takes a snapshot and expect to still work...
    # Just keeping it simple.
    return bool_value(os.environ.get('CONFIG_ENV_ONLY', False))


def standard_directories(*, service: str, env: str) -> OrderedSet[Directory]:
    """
    Gives you the standard list of directories for service/env combination.
    This is called when creating a `Config.__init__` if no `directories` are passed into any
    Config object in the [Parent Chain](#parent-chain).

    Normally you would want to use Config.directories = [Default]; which would cause the
    Config object to ask it's parent chain, and they are also all set to `Default` then
    it will call this `standard_directories` method for you to get the `Default` directories.

    If for some reason you want to custimize or use diffrent service/env names for addtional
    directory paths to check beyond the defaults, you can call this method and append them to
    a config object, like so:

    >>> from xcon.config import config
    >>> for directory in standard_directories(service="customService", env="customEnv"):
    ...     config.add_directory(directory)

    The code ^ above would keep the default directory as the first one(s) to look at to the
    current/default config. After looking at the pre-existing default ones it would next look
    at your customService/customEnv paths too afterwards. Finally, Config would then look at
    any ones added via `Config.add_export`.

    ## Whats Returned Summary

    For more details and context surounding what is returned, see
    [Standard Directory Paths](#standard-directory-paths). Below is a summary.

    Right now we return these directories, in priority order:

    1. `/{service}/{env}`
    2. `/{service}`
    3. `/global/{env}`
    4. `/global`

    If service == 'global' or None or blank, we will use `global` and only provide the two
    global directories and leave the {service} ones out of it:

    1. `/global/{env}`
    2. `/global`

    Parameters
    -----------
    service: str
        The name of the service, generally the project's name, in camelCase.
        You can grab the current service being used via `Config.SERVICE_NAME`.

        If None/Blank, we will use `global`.

    env: str
        Environment, could be 'testing', 'prod', or something custom like 'yourName',
        this is also generally in `camelCase`.

        You can grab the current environment being used via `Config.APP_ENV`.

        If None/Blank, we will use `dev`.
    """
    if not service:
        service = 'global'

    if not env:
        env = 'dev'

    cache = _std_directory_chain_cache
    cache_key = f"{service} : {env}"
    directory_chain = cache.get(f"{service} : {env}")
    if directory_chain:
        return directory_chain

    directories: OrderedSet[Directory] = {}
    if service == 'global':
        # FYI: We only log this once, since we will return cached version in the future.
        #      which is a good thing, otherwise it would be a lot of log messages.
        xlog.warning(
            "We have no specific SERVICE_NAME, so we will only check '/global/*' for Config "
            "values."
        )
    else:
        directories[Directory(service=service, env=env)] = None
        directories[Directory(service=service)] = None

    # When no service is provided, it uses the 'global' service by default for directory.
    directories[Directory(env=env)] = None
    directories[Directory()] = None
    cache[cache_key] = directories
    return directories


_BlankParentChain = _ParentChain()
_std_directory_chain_cache: Dict[str, OrderedSet[Directory]] = dict()


class ConfigRetriever(SettingsRetrieverProtocol):
    """Retrieving the setting from config"""
    def __call__(self, *, field: SettingsField, settings: 'Settings') -> Any:
        return config.get(field.name)


class ConfigSettings(Settings, default_retrievers=[ConfigRetriever()]):
    pass
