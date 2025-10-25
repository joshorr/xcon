import os

import moto
import pytest
from xcon import config
from xboto.resource import dynamodb
from xcon import xcon_settings


service_name_at_import_time = os.environ['APP_NAME']
app_env_at_import_time = os.environ['APP_ENV']

os.environ['SOME_ENV_VAR'] = 'hello'


def test_ensure_config_is_at_baseline_at_module_import_time():
    # Ensure that config is configured at conftest import time.
    assert service_name_at_import_time == 'testing'
    assert app_env_at_import_time == 'unit'


@pytest.fixture
def directory():
    """ Returns the currently configured full test Directory [with the proper service/env set].
        This uses the `config` fixture to an isolated config, and `config` fixture will get
        an isolated XContext for you as well.
    """
    from xcon.directory import Directory
    return Directory(service=xcon_settings.service, env=xcon_settings.environment)


@pytest.fixture(autouse=True)
def start_moto():
    with moto.mock_aws():
        yield


@pytest.fixture(autouse=True)
def dynamo_cache_table(start_moto):
    return dynamodb.create_table(
        TableName='global-all-configCache',
        KeySchema=[
            # Partition Key
            {'AttributeName': 'app_key', 'KeyType': 'HASH'},
            # Sort Key
            {'AttributeName': 'name_key', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'app_key', 'AttributeType': 'S'},
            {'AttributeName': 'name_key', 'AttributeType': 'S'}
        ],
        # todo:
        #  YOu need to use a newer-boto3 for this to work than what lamda provides.
        #  HOWEVER, the config table should always exist, so we should not have to really
        #  worry about it. If the able already exists we won't attempt to create it.
        BillingMode='PAY_PER_REQUEST',
        SSESpecification={
            "Enabled": True
        }
    )


@pytest.fixture(autouse=True)
def dynamo_provider_table(start_moto):
    return dynamodb.create_table(
        TableName='global-all-config',
        KeySchema=[
            # Partition Key
            {'AttributeName': 'app_key', 'KeyType': 'HASH'},
            # Sort Key
            {'AttributeName': 'name_key', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'app_key', 'AttributeType': 'S'},
            {'AttributeName': 'name_key', 'AttributeType': 'S'}
        ],
        # todo:
        #  YOu need to use a newer-boto3 for this to work than what lamda provides.
        #  HOWEVER, the config table should always exist, so we should not have to really
        #  worry about it. If the able already exists we won't attempt to create it.
        BillingMode='PAY_PER_REQUEST',
        SSESpecification={
            "Enabled": True
        }
    )
