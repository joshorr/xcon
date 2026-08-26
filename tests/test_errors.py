import datetime as dt
import functools
import os
import time
from typing import Type

from xcon.providers.common import AwsProvider

from xboto import boto_clients
import moto
import pytest
from xsentinels import Default
from xloop import xloop

from xcon import Config, config
from xcon.directory import DirectoryItem, Directory
from xcon.provider import ProviderCacher, InternalLocalProviderCache
from xcon.providers import (
    EnvironmentalProvider,
    DynamoProvider,
    SsmParamStoreProvider,
    SecretsManagerProvider,
    DynamoCacher,
)
from xcon.providers.dynamo import _ConfigDynamoTable

DEFAULT_TESTING_PROVIDERS = [EnvironmentalProvider, SecretsManagerProvider, SsmParamStoreProvider]

# TODO: It's so difficult to make boto3 not find credentials in all situations when running on local environment.
#   Need to come back to this and figure out how to make this unit test more reliable.

# @pytest.mark.parametrize(
#     "provider_type",
#     [
#         SecretsManagerProvider,
#         DynamoProvider,
#         SsmParamStoreProvider
#     ],
# )
# # Must run it before the others, or boto will 'cache' the config-file;
# # If the config file does not exist, it looks it up each time.
# # So the other tests should run fine and be able to find a default region.
# @pytest.mark.order("first")
# def test_providers_is_ok_without_region(provider_type: Type[AwsProvider]):
#     old_region = None
#     try:
#         # Point boto to a non-existent file;
#         # the easiest way I found to get boto to raise a NoRegion error.
#         os.environ['AWS_CONFIG_FILE'] = '/dev/null'
#         if 'AWS_DEFAULT_REGION' in os.environ:
#             old_region = os.environ['AWS_DEFAULT_REGION']
#             del os.environ['AWS_DEFAULT_REGION']
#
#         os.environ['AWS_CONFIG_FILE'] = '/dev/null'
#
#         provider = provider_type()
#
#         # If should not get an exception, it should be handled for us this should return None
#         item = provider.get_item(
#             name='some-name',
#             directory=Directory.from_path("/a/b"),
#             directory_chain=None,
#             provider_chain=None,
#             environ=Directory(service='unittest', env='unittest')
#         )
#
#         # It should look nothing up.
#         assert item is None
#
#         # See if we handled the correct error and not some other error.
#         from xcon.providers.common import aws_error_classes_to_ignore
#         assert provider.botocore_error_ignored_exception
#         assert type(provider.botocore_error_ignored_exception) in aws_error_classes_to_ignore
#     finally:
#         # Cleanup, this could contaminate other unit tests, remove it.
#         del os.environ['AWS_CONFIG_FILE']
#         if old_region is not None:
#             os.environ['AWS_DEFAULT_REGION'] = old_region
