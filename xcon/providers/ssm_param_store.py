# python
from __future__ import annotations

from typing import Optional, Mapping

from xboto import boto_clients
from botocore.exceptions import ClientError

from ..random_backup import RandomBackoff

from xcon.provider import AwsProvider, ProviderChain

from .common import handle_aws_exception
from ..directory import Directory, DirectoryListing, DirectoryOrPath, DirectoryItem, DirectoryChain


class SsmParamStoreProvider(AwsProvider):
    attributes_to_skip_while_copying = ['_store_get_params_paginator']
    name = "ssm"
    _store_get_params_paginator = None

    @property
    def _get_params_paginator(self):
        paginator = self._store_get_params_paginator
        if not paginator:
            paginator = boto_clients.ssm.get_paginator('get_parameters_by_path')
            self._store_get_params_paginator = paginator
        return paginator

    def get_item(
            self,
            name: str,
            directory: Optional[DirectoryOrPath],
            directory_chain: DirectoryChain,
            provider_chain: ProviderChain,
            environ: Directory
    ) -> Optional[DirectoryItem]:
        if directory is None:
            return None
        return self._item_only_for_directory(name=name, directory=directory)

    def _item_only_for_directory(
            self, name: str, directory: DirectoryOrPath
    ) -> Optional[DirectoryItem]:
        directory = Directory.from_path(directory)
        if not directory:
            return None

        listing = self.local_cache.get(directory)
        if listing:
            return listing.get_item(name)

        items = []
        try:
            # Retry paginator iteration with RandomBackoff.
            # Configure for multiple attempts via RandomBackoff.
            backoff = RandomBackoff(max_attempts=4)
            pages = []
            last_exception: Exception | None = None

            while backoff.wait():
                try:
                    pages_iter = self._get_params_paginator.paginate(
                        Path=directory.path,
                        Recursive=False,
                        WithDecryption=True,
                    )
                    # materialize to surface iterator/network errors (where throttles occur)
                    pages = list(pages_iter)
                    last_exception = None
                    break
                except ClientError as e:
                    # Only retry on throttling-related error codes.
                    error_code = ''
                    try:
                        error_code = e.response.get('Error', {}).get('Code', '')
                    except Exception:
                        pass

                    if error_code in (
                        'ThrottlingException',
                        'ThrottledException',
                    ):
                        last_exception = e
                        # loop will call backoff.wait() again (which sleeps) or exit when exhausted
                        continue
                    # Non-throttle ClientError: do not retry
                    last_exception = e
                    break
                except Exception:
                    raise

            if last_exception is not None and not pages:
                # Retries exhausted or non-throttle error -> delegate to existing handler
                raise last_exception from None

            for p in pages:
                for item_info in p['Parameters']:
                    item_path: str = item_info['Name']
                    item = DirectoryItem(
                        directory=directory,
                        name=item_path.split("/")[-1],
                        value=item_info['Value'],
                        source=self.name
                    )
                    items.append(item)

        except Exception as e:
            # Fallback to existing handler for any unexpected error
            handle_aws_exception(e, self, directory)

        # If we got an error, `items` will be empty.
        # In this case, in the future, we won't try to retrieve this directory since we are
        # setting it blank here.
        listing = DirectoryListing(directory=directory, items=items)

        self.log_about_items(
            items=listing.item_mapping().values(),
            path=listing.directory.path
        )

        self.local_cache[directory] = listing
        return listing.get_item(name)

    def retrieved_items_map(
            self, directory: DirectoryOrPath
    ) -> Optional[Mapping[str, DirectoryItem]]:
        directory = Directory.from_path(directory)
        listing = self.local_cache.get(directory)
        if listing is None:
            return None
        return listing.item_mapping()
