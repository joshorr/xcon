from __future__ import annotations

import dataclasses
import os
import threading
from abc import ABC, abstractmethod
from inspect import isclass
from typing import Iterable, Optional, Mapping, Set, Type, Any, Callable, Dict
from typing import Union

from botocore.exceptions import BotoCoreError
from xinject import Dependency, XContext
from xloop import xloop

from .directory import Directory, DirectoryOrPath, DirectoryItem, DirectoryChain, DirectoryListing

import datetime as dt
from logging import getLogger

log = getLogger(__name__)


class Provider(Dependency):
    """
    Represents a Provider, which wraps a resource that can be used to store Config values based
    on a provided directory. It caches these directories so future lookups don't keep having to
    fetch them from the Dependency again in the future, while the process is still running.

    Most of the time there is no need for a several of the same provider in the same process/app.

    The providers generally keep a cache of every directory they already looked up, so it's nice to
    share that cache with other Child context's by default via the
    `xinject.dependency.Dependency` mechanism.

    Config will use the current/active provider when it needs to consult a Provider for values.

    Each provider should be careful that they communicate with any remote service in a thread-safe
    manner, as Config objects from other threads could use the same Provider instance.

    Most of the time, network clients are not thread-safe to use, examples include:

    - boto clients/resources are also not thread-safe.
    - Sessions from requests library can't be used cross-thread.

    For boto, if you use `xboto` to grab the boto client/resource,
    it will allow you to lazily get a shared object that is guaranteed to only be shared
    for the current thread.

    This allows boto to reuse connections for things running on the same thread,
    but `xboto` will lazily create a new client if your on a separate thread.
    """

    name = "?"
    """ This is the value that will normally be set to the items
        `xcon.directory.DirectoryItem.source`, also displayed
        when logging out the names of providers when something can't be found.
    """

    is_cacher = False
    """ Easy way to figure out if a provider is a `ProviderCacher` or just a normal provider.
        Should be set to `True` for provider subclasses that are cachers.
        Defaults to `False`.
    """

    query_before_cache_if_possible = False
    """ If True, and this is before any other providers that have this set to False, the
        cacher will be consulted AFTER that provider(s). In this way I'll make my best-effort
        to accommodate this particular request.

        If False, then I guarantee the cacher [if there is one] will be consulted BEFORE
        this provider is.

        See [Config Overview - Caching](config.html#caching) for more details on how caching
        works.
    """

    needs_directory = True
    """ By default, providers can't really use a `None` for a directory when calling `get_item()`.
        If you CAN work with a None directory then set this to False (for example
        `xcon.providers.environmental.EnvironmentalProvider` uses this).

        A `None` normally means that we could not determine the proper directory to use.
        This can happen if no SERVICE_NAME and APP_ENV are defined. But some providers don't
        really use directories and are ok with getting a `None` query.

        This flag lets Config class know if it should bother to allocate this provider or not based
        on if it has a directory list or not to work with.
    """

    _errored_directories: Set[Directory]
    """ Used to keep track of directories we are excluding. """

    # ------------------------------------
    # --------- Abstract Methods ---------

    @abstractmethod
    def get_item(
            self,
            name: str,
            directory: Optional[DirectoryOrPath],
            directory_chain: DirectoryChain,
            provider_chain: ProviderChain,
            environ: Directory
    ) -> Optional[DirectoryItem]:
        """
        Grabs a config value for name in directory.

        The other arg's are more for the `ProviderCache`. They describe the current environment
        of the current config lookup.

        Side Note: For and overview of the caching process, see
        [Config Overview - Caching](../config.html#caching)

        Args:
            name: Name of the config value, ie: `XYNAPI_BASE_URL`.
            directory: Directory to lookup value in, this is not really used right now by
                cacher. But it's used by the other providers. This cacher acts just like
                a provider and so accepts the parameter.
            directory_chain: Current directory chain that is being used to lookup value.
            provider_chain (xcon.provider.ProviderChain): Current provider chain
                that is being used to lookup value.
            environ:
                This is supposed to have the full service and environment name.

                Example Directory Path: `/hubspot/testing`

        Returns:
            xcon.directory.DirectoryItem: If we have the item, this is it.
            None: Otherwise we return None indicating we don't know about it.
        """
        raise NotImplementedError(f"Need to implement in ({self}).")

    @abstractmethod
    def retrieved_items_map(
            self, directory: DirectoryOrPath
    ) -> Optional[Mapping[str, DirectoryItem]]:
        """ Should return a read-only lower-case item name TO item mapping.
            You can easily get one of these from a DirectoryList object's `item_mapping()`.

            If provider has not yet retrieved the listing for the passed-in directory,
            it should simply pass back None. It's important to know the difference between
            a blank retrieval and no-retrieval attempt, so please pass back None in that case!!!
        """
        raise NotImplementedError(f"Need to implement in ({self}).")

    # ---------------------------------
    # --------- Other Methods ---------

    def __init__(self):
        self._errored_directories = set()

    def log_about_items(
        self, *, items: Iterable[DirectoryItem], path: str, msg_prefix='Retrieved'
    ):
        # We could be called before application has configured it's logging;
        # ensure logging has been configured before we log out.
        # Other-wise log message may never get logged out
        # (Python defaults to Warning log level).

        # Use cache_range_key if it exists, otherwise use name.
        # cache_range_key has the name + other uniquely identifying information.
        names = [v.cache_range_key or v.name for v in items]
        provider_class = self.__class__.__name__
        thread_name = threading.current_thread().name
        extra = dict(
            msg_prefix=msg_prefix,
            provider=self.name,
            provider_class=provider_class,
            names=names,
            path=path,
            thread_name=thread_name,
        )

        log.info(
            f"{msg_prefix} values via provider ({self.name}/{provider_class}) "
            f"for path ({path}), for thread ({thread_name}); see log extra's for list of all names retrieved.",
            extra=extra
        )

    def mark_errored_directory(self, directory: Directory):
        """ If a directory has an error, this is called. For informational purposes only. """
        self._errored_directories.add(directory)

    def directory_has_error(self, directory: Directory):
        """ If a directory had an error in the past, this returns true.
            For informational purposes only.
        """
        return directory in self._errored_directories

    def get_value(
            self,
            name: str,
            directory: Optional[DirectoryOrPath],
            directory_chain: DirectoryChain,
            provider_chain: ProviderChain,
            environ: Directory
    ):
        """ Gets an item's value for directory from provider. Return None if not found.
        """
        item = self.get_item(
            name=name,
            directory=directory,
            directory_chain=directory_chain,
            provider_chain=provider_chain,
            environ=environ
        )
        return item.value if item else None


class AwsProvider(Provider):
    """ AwsProvider is the Base class for Aws-associated config providers.

        There is some aws specific error handing that this class helps with among the
        aws providers.

        This is the Default Doc message, you will want to override this doc-comment in
        any subclasses.
    """
    botocore_error_ignored_exception: BotoCoreError = None
    """ This means that any attempt to communicat with aws service will probably fail;
        probable due to a corrupted or missing aws credentials.
    """

    @property
    def local_cache(self) -> Dict[Directory, DirectoryListing]:
        cacher = InternalLocalProviderCache.grab()
        return cacher.get_cache_for_provider(provider=self, cache_constructor=lambda c: dict())


class ProviderCacher(AwsProvider):
    # See `Provider.is_cacher` for docs.
    is_cacher = True
    """ This is set to True by default for ProviderCacher's.
        See `Provider.is_cacher`.
    """

    @abstractmethod
    def cache_items(
            self,
            items: Iterable[DirectoryItem],
            provider_chain: ProviderChain,
            directory_chain: DirectoryChain,
            environ: Directory
    ):
        raise NotImplementedError(f"Need to implement in ({self}).")


@dataclasses.dataclass(eq=True, frozen=True)
class ProviderChain:
    """ A prioritized list of providers to consult when getting a value.
    """
    providers: Iterable[Union[Provider, Type[Provider]]] = dataclasses.field(
        compare=False, repr=False
    )
    """ This will be a tuple of ordered providers.
        When you create a ProviderChain, you can give it a class or objects.

        It will convert any class types passed in into a proper object for you automatically
        via the current context [as a resource].
    """

    concatenated_provider_names: str = dataclasses.field(init=False, compare=True)
    """ Concatenated list of all of my provider's `Provider.name` with a pipe `|` in-between.

        Only includes providers that are cachable.
        Cachable providers are ones assigned to myself after any providers list first that have
        `Provider.query_before_cache_if_possible` set to True.

        Starting with the first provider in my list has `Provider.query_before_cache_if_possible`
        set to False (default) we will consider them cachable.

        Normally, the `xcon.providers.environmental.EnvironmentalProvider` provider
        is the only non-cacheable provider, and normally it's listed first.

        This means that we will normally not cache values from this EnvironmentalProvider.
        If the EnvironmentalProvider happens to be after a cachable provider, we will include
        it as one of the keys in range-key of the items that gets cached into the Dynamo
        config cache table.

        This is because finding a value in some other provider before looking at
        EnvironmentalProvider can effect the results since we would not look in the
        EnvironmentalProvider in that case. As would finding a value in the environmental
        provider would prevent looking at other providers.

        Therefore it *might* effect the results. Just to be on safe side we use
        EnvironmentalProvider as one of the range cache keys in this situations.

        But like I said previously, normally the `EnvironmentalProvider` is the first provider
        and so is not included in the final `concatenated_provider_names` list.
    """

    have_any_cachable_providers: bool = True
    """ If any providers have `Provider.query_before_cache_if_possible` set to `False
        this will be `True`.

        If **all** providers have `Provider.query_before_cache_if_possible` set to `True`
        then this will set to `False`.
    """

    def __post_init__(self):
        providers = list()
        context = XContext.grab()
        provider_key_names = []
        query_before_finished = False
        for p in xloop(self.providers, default_not_iterate=[str]):
            # Check to see if any of them are classes [and type's resources needs to be grabbed].
            if isclass(p):
                p = context.dependency(p)
            providers.append(p)

            if not query_before_finished:
                if p.query_before_cache_if_possible:
                    continue
                query_before_finished = True
            provider_key_names.append(p.name)

        object.__setattr__(self, 'providers', tuple(providers))

        if not query_before_finished:
            object.__setattr__(self, 'have_any_cachable_providers', False)

        # Pre-calculate a useful field, a concatenated list of the directory paths.
        provider_names = '|'.join(provider_key_names)
        object.__setattr__(self, 'concatenated_provider_names', provider_names)

    def _providers_with_cacher(
            self,
            directory_chain: DirectoryChain,
            cacher: Optional[ProviderCacher] = None,
            environ: Directory = None
    ) -> Iterable[Provider]:
        """ Generator of providers and cacher, as needed. """
        already_used_cache = False
        for provider in self.providers:
            if already_used_cache or provider.query_before_cache_if_possible:
                yield provider
                continue
            already_used_cache = True
            if cacher:
                yield cacher
            yield provider

    def get_item(
        self,
        name: str,
        directory_chain: DirectoryChain,
        cacher: ProviderCacher = None,
        environ: Directory = None
    ) -> DirectoryItem:
        """
        Goes though passed in directory_chain, querying each provider in `DirectoryChain.providers`
        for a value. If it finds one, that's what we will return.  Otherwise None.

        We will check with the passed in cacher at the appropriate time as we go though
        our own providers via `DirectoryChain.providers`.

        If needed we will tell the cacher before we return to cache the values we find.
        """
        use_cacher = (cacher and environ)
        items_cache = {}
        item = None
        places_checked = []

        for directory in directory_chain.directories:
            item = None
            for provider in self._providers_with_cacher(
                directory_chain=directory_chain, cacher=cacher, environ=environ
            ):
                item = provider.get_item(
                    name=name, directory=directory,
                    directory_chain=directory_chain,
                    provider_chain=self,
                    environ=environ
                )

                had_error = provider.directory_has_error(directory)
                if had_error:
                    result = "error"
                elif item and item.directory and item.directory.is_non_existent:
                    result = "found(cached-as-non-existent)"
                elif item:
                    result = "found"
                else:
                    result = "not-found"

                places_checked.append(
                    f"{provider.name}:{directory.path} | result={result}"
                )

                if item is not None:
                    break

            if use_cacher and item and not item.cacheable:
                # Optimization: Don't spend time looking at what cacher could send if our
                # value is not cacheable [probably an environmental var].
                use_cacher = False

            # Priority for items is given to directories order, keep what we've already got
            # over the new stuff from a lower-priority directory.
            #
            # We do this so we can cache as much as we can at a time, otherwise we would be
            # caching with many single items with single requests at a time.
            #
            # The other option is to have the app/service that uses us use a batch-writer
            # for the ConfigDynamoTable, which might be better [so we only write exactly what
            # we need based on what got looked up].
            #
            # todo: [see discussion above]
            #   Consider if we should batch-write the whole time the program is running
            #   or if we should collect everything we can based on what we current have
            #   looked up and writing it to cache [only things that have not been in cache
            #   previously]. But we would need a way to force-write the current batch when
            #   we are done [think about it].
            if use_cacher:
                items_cache = {
                    **self.retrieved_items_map(directory=directory),
                    **items_cache
                }

            if item:
                break

        # If we did not find the item, create a 'nonExistent' item in it's place.
        if not item:
            item = DirectoryItem(None, name, value=None, source=f"/_nonExistent")

        item.add_supplemental_metadata("locations_searched", places_checked)

        if use_cacher and item.cacheable:
            items_cache[item.name] = item
            cacher.cache_items(
                items_cache.values(),
                provider_chain=self,
                directory_chain=directory_chain,
                environ=environ
            )
        return item

    def retrieved_items_map(
            self, directory: DirectoryOrPath
    ) -> Mapping[str, DirectoryItem]:
        """
        Will return a read-only lower-case item name TO item mapping by going through each
        provider in my chain, starting with the highest priority and calling
        `retrieved_items_map()` on them and collecting the results into a single dict that I'll
        return.

        Keep in mind that if a provider has not retrieved anything yet, I'll stop and return
        what I have at that point. These providers can be shared with other provider chains
        and if a lower-priority provider has retrieved their values before a higher-priority, we
        could end up with the wrong values.  Since I stop at the first provider that has not
        retrieved the passed in directory yet, we are protected from that possibility.
        """
        final_map = {}
        for provider in self.providers:
            provider_map = provider.retrieved_items_map(directory)
            if provider_map is None:
                # We stop when we encounter a provider that has not retrieved
                # the directory listing yet [safety mechanism, see doc comment above].
                break
            # `final_map` is second, so it overrides the `provider_map` dict.
            final_map = {**provider_map, **final_map}
        return final_map


class InternalLocalProviderCache(Dependency):
    """
    Used by the providers for a place to store/cache things they retrieve from the systems
    they provide configuration values from.

    The reason we have a central resource to keep track of the cache now,
    instead of doing it directly inside the providers like they used to be is
    so that all providers can have their internal/local cache expire at the same time.

    If the dynamo cache provider expires, and it happens to be something did change in SSM
    and deleted a key in the dynamo cache table we want to look up the new value in SSM
    and not version we may have in the internal/local cache.

    If we did not expire everything simultaneously, it could be that the dynamo cache
    expires before the SSM.  So we end up check the SSM provider and the new value is
    not looked up because of its internal/local cache.

    Expiring all providers internal/local cached simultaneously avoids this problem,
    and simplifies the 'high-level' conceptual aspect of how the Config and its internal
    caching works from a usability/user-of-the-library point of view.

    At the moment, the key is id/memory-address of the provider instance.
    This means a new provider instance would provide a new/blank cache for that object.
    The old instance, if still used, would still have access to whatever it previously cached.
    """
    _local_internal_cache = None
    _time_cache_last_reset = None

    expire_time_delta: dt.timedelta = dt.timedelta(minutes=15)
    """
    Amount of time before cache expires.
    You can change this to anything you want at any time,
    as it's checked each time a provider retrieves it's cache.
    The providers do this every time they are asked for a value.

    In addition to changing this directly
    (via `InternalLocalProviderCache.grab().expire_time_delta` = ...)
    you can also override this via an environmental variable:

    `XCON_INTERNAL_CACHE_EXPIRATION_MINUTES`

    If this variable is defined, we will take the value as the number of minutes
    to wait until we expire/reset our cache.

    Otherwise the default expiration is 15 minutes.
    """

    def __init__(self):
        super().__init__()
        from xcon import xcon_settings
        if minutes := xcon_settings.internal_cache_expiration_minutes:
            if minutes > 0:
                self.expire_time_delta = dt.timedelta(minutes=minutes)
        self.reset_cache()

    def get_cache_for_provider(
        self, *, provider: Provider, cache_constructor: Callable[[InternalLocalProviderCache], Any]
    ) -> Any:
        """
        Given `provider`, we will return a cached object keyed to the `provider` instance.

        If there currently is no cache object for `provider` instance in self,
        and you provide a `cache_constructor`, we will call the `cache_constructor` and provide
        a single positional argument we pass `self` (instance of InternalLocalProviderCache) to.

        If you return a non-None value from this constructor, we will store this value
        as the cache object, keyed under the instance of `provider` and return this same
        object in the future until the cache is expired or reset.

        Otherwise, if you return None your expected to call `set_cache_for_provider` on
        the instance of InternalLocalProviderCache we give the constructor callback.

        If we still don't have a value, and you provided a constructor, we will raise a ValueError.
        """
        self.expire_cache_if_needed()
        provider_id = id(provider)
        cache = self._local_internal_cache.get(provider_id)
        if cache is None and cache_constructor:
            cache = cache_constructor(self)
            if cache is None:
                cache = self._local_internal_cache.get(provider_id)

            if cache is None:
                raise ValueError(
                    f"Provided cache_constructor returned a None value and also did not set "
                    f"a value either in InternalLocalProviderCache for provider ({provider})."
                )
            self._local_internal_cache[provider_id] = cache

        return cache

    def set_cache_for_provider(self, *, provider: Provider, cache: Any):
        self.expire_cache_if_needed()
        self._local_internal_cache[id(provider)] = cache

    def expire_cache_if_needed(self):
        if self._time_cache_last_reset < dt.datetime.now() - self.expire_time_delta:
            self.reset_cache()

    def reset_cache(self):
        self._local_internal_cache = {}
        self._time_cache_last_reset = dt.datetime.now()
