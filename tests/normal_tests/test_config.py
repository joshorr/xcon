import datetime as dt
import functools
import os
import time
from typing import Type
from xcon import xcon_settings

from xcon.providers.common import AwsProvider

from xboto import boto_clients
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
    DynamoCacher
)
from xcon.providers.dynamo import _ConfigDynamoTable

DEFAULT_TESTING_PROVIDERS = [EnvironmentalProvider, SecretsManagerProvider, SsmParamStoreProvider]

# We want to use the various aws-based providers for the unit tests, as we will
# be mocking the various aws services explicitly for them to use and so we are
# not in danger of it trying to use the real services.
#
# Normally, the 'config' fixture would configure it to not use a cacher and only use the
# EnvironmentalProvider.


def config_with_env_dyn_ssm_secrets_providers(myfunc):
    @functools.wraps(myfunc)
    def produce_config(*args, **kwargs):
        with Config(
            providers=[
                EnvironmentalProvider,
                DynamoProvider,
                SsmParamStoreProvider,
                SecretsManagerProvider,
            ],
        ):
            myfunc(*args, **kwargs)

    return produce_config


def test_env_only_env_var():
    def assert_only_provider_used(provider):
        assert [type(x) for x in config.provider_chain.providers] == [provider]

    # Check to see if normally, providers and cacher will used what's set on them.
    config.providers = [SsmParamStoreProvider]
    config.cacher = Default

    assert_only_provider_used(SsmParamStoreProvider)
    assert type(config.resolved_cacher) is DynamoCacher

    try:
        # Next, set XCON_ONLY_ENV_PROVIDER and check conditions.
        os.environ['XCON_ONLY_ENV_PROVIDER'] = 'true'

        # When using default providers, `EnvironmentalProvider` should be only one
        config.providers = [Default]
        assert_only_provider_used(EnvironmentalProvider)

        # Even when using set/explicit provider, only EnvironmentalProvider is used.
        config.providers = [SecretsManagerProvider]
        assert_only_provider_used(EnvironmentalProvider)

        # Config still remembers the providers it's configured with,
        # even if it does not use them with XCON_ONLY_ENV_PROVIDER is enabled.
        assert list(config.providers) == [SecretsManagerProvider]
    finally:
        del os.environ['XCON_ONLY_ENV_PROVIDER']

    # After environmental variable deleted, check to see if Config goes back to normal.
    assert_only_provider_used(SecretsManagerProvider)
    assert type(config.resolved_cacher) is DynamoCacher
    assert type(config.resolved_cacher) is DynamoCacher


@Config(providers=[EnvironmentalProvider])
def test_env_provider():
    # The rest of the unit tests configure an environmental provider.
    # Ensure the environmental provider works with a real environmental variable.
    # This env-var is configured via `tests/conftest.py`.
    item = config.get_item("SOME_ENV_VAR")

    # Ensure we got it from environmental provider.
    assert item.source == 'env'

    # Ensure we got correct value.
    assert item.value == 'hello'

    # Ensure we don't got some non-existent value...
    assert config.get_value("some_other_non_existent_env_var") is None


def test_config_disable_via_env_var():
    # Re-enable the cacher by default, so we can test cacher-related features
    # (it's set to None by default for unit tests)
    config.cacher = Default

    # Ensure we are starting with a Blank context with special Config in it
    # (unit tests normally have a special Config set to not use a cacher).
    # So the cacher should be ENABLED, checking our assumption:
    assert isinstance(config.resolved_cacher, DynamoCacher)

    # Next, we set env-var and see if the cacher is disabled now.
    xcon_settings.disable_default_cacher = True
    assert config.resolved_cacher is None

    # Ensure when using an explict cacher, we use it regardless of env-var value.
    with Config(cacher=DynamoCacher):
        assert isinstance(config.resolved_cacher, DynamoCacher)
        # ensure child config uses parent's config xcon_settings.
        with Config():
            assert isinstance(config.resolved_cacher, DynamoCacher)


@config_with_env_dyn_ssm_secrets_providers
def test_direct_class_access(directory: Directory):
    config['TEST_NAME'] = "myTestValue"
    # When you access a config var via the default config, it should lookup the current
    # default config automatically [via current XContext] and use that to get the var.
    assert config['TEST_NAME'] == 'myTestValue'


@config_with_env_dyn_ssm_secrets_providers
def test_basic_configs(directory: Directory):
    # Basic defaults-test.
    config.set_default('TEST_NAME', 'myTestDefaultValue')
    value = config['TEST_NAME']
    assert value == 'myTestDefaultValue'
    config['TEST_NAME'] = "myTestValue"
    assert config['test_name'] == 'myTestValue'


@config_with_env_dyn_ssm_secrets_providers
def test_config_for_unconfiged_param(directory: Directory):
    # Basic defaults-test.
    config.set_default('TEST_NAME', 'myTestDefaultValue')
    assert config['TEST_NAME'] == 'myTestDefaultValue'
    assert config['TEST_NAME_OTHER'] is None


@config_with_env_dyn_ssm_secrets_providers
def test_direct_parent_behavior(directory: Directory):
    config.set_default("A_DEFAULT", 'parent-default')

    child = Config()

    assert child.directory_chain == config.directory_chain
    assert child.resolved_cacher is config.resolved_cacher
    assert child.cacher is Default
    assert config.cacher is Default
    assert child.provider_chain.providers == config.provider_chain.providers
    assert child['A_DEFAULT'] == 'parent-default'

    child = Config(cacher=None)
    assert child.directories == config.directories
    assert child.cacher is None
    assert child['A_DEFAULT'] == 'parent-default'

    # Remove the cacher provider, see if the others are still the same.
    config_providers = [
        p for p in config.provider_chain.providers if not isinstance(p, ProviderCacher)
    ]
    assert list(
        xloop(child.provider_chain.providers, default_not_iterate=[str])
    ) == list(xloop(config_providers, default_not_iterate=[str]))

    child = Config(directories=["/hello/another"])

    assert list(
        xloop(child.directory_chain.directories, default_not_iterate=[str])
    ) == [Directory.from_path("/hello/another")]

    assert child.cacher is Default
    assert child['A_DEFAULT'] == 'parent-default'
    child['A_DEFAULT'] = 'child-override'
    assert child['A_DEFAULT'] == 'child-override'

    # Replace cacher in parent provider list with child cacher, since the directory is
    # different, child should construct a new cacher.
    config_providers = [
        p if not isinstance(p, ProviderCacher) else child.cacher
        for p in config.provider_chain.providers
    ]
    child_providers = list(xloop(child.provider_chain.providers, default_not_iterate=[str]))
    parent_providers = list(xloop(config.provider_chain.providers, default_not_iterate=[str]))
    assert child_providers == parent_providers


@config_with_env_dyn_ssm_secrets_providers
def test_env_are_higher_priority_than_cacher(directory: Directory):
    # Re-enable the cacher by default, so we can test cacher-related features
    # (it's set to None by default for unit tests)
    # This is the root-config (via the config fixture).
    config.cacher = DynamoCacher

    # This is for making sure the default value does not somehow override other ways
    # config get's it's value [Config should use defaults as the last-resort].
    config.set_default('TEST_CACHER_NOT_USED', 'default-value')

    # Put some test-data in ssm.
    client = boto_clients.ssm
    client.put_parameter(
        Name=f'{directory.path}/test_cacher_not_used', Value="wrongValue", Type="String"
    )

    # Grab the existing values from the providers, make sure we see it [also caches it in cacher].
    assert config['TEST_CACHER_NOT_USED'] == 'wrongValue'

    # Override EnvironmentalProvider with a specific environmental-variable.
    with EnvironmentalProvider(env_vars={'TEST_CACHER_NOT_USED': 'rightValue'}):
        # Ensure the original ssm value made it into the cacher;
        # we are verifying that the cache got updated correctly with this check.
        cacher_obj = DynamoCacher.grab()
        assert (
            cacher_obj.get_value(
                name='TEST_CACHER_NOT_USED',
                directory=directory,
                directory_chain=config.directory_chain,
                provider_chain=config.provider_chain,
                environ=Directory(service=xcon_settings.service, env=xcon_settings.environment),
            )
            == 'wrongValue'
        )

        # Make sure the environmental variable is now taking priority over cacher.
        assert config['TEST_CACHER_NOT_USED'] == "rightValue"


@config_with_env_dyn_ssm_secrets_providers
def test_basic_config(directory: Directory):
    # Put some test-data in ssm
    client = boto_clients.ssm
    client.put_parameter(Name=f'{directory.path}/test_name', Value="testValue2", Type="String")

    # Make sure moto is working....
    v = client.get_parameter(Name=f'{directory.path}/test_name')
    assert v['Parameter']['Value'] == 'testValue2'

    # See if our config object can lookup the test-data in ssm automatically.
    v2 = config.get('TEST_NAME')
    assert v2 == 'testValue2'


@config_with_env_dyn_ssm_secrets_providers
@pytest.mark.parametrize(
    "expected_values",
    [
        {"expected_value": "ssmValue", "cache_item_name": "test_name2"},
        {"expected_value": "dynamoVal", "cache_item_name": "test_name"},
    ],
)
def test_ssm_and_dynamo(directory: Directory, expected_values):
    client = boto_clients.ssm
    client.put_parameter(
        Name=f'{directory.path}/test_name',
        Value="ssmValue",
        Type="String",
    )

    table = _ConfigDynamoTable(table_name='global-all-config')
    item = DirectoryItem(
        name=expected_values['cache_item_name'],
        directory=directory,
        value="dynamoVal",
        cache_hash_key=directory.path,
        cache_concat_provider_names=config.provider_chain.concatenated_provider_names,
        cache_concat_directory_paths=config.directory_chain.concatenated_directory_paths,
        # moto can't do a comparison on a non-existent attribute, so provide one
        # [dynamo it's self works fine with filter-expressions on non-existent attributes].
        ttl=dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(hours=30),
    )
    table.put_item(item)

    # See if our config object can look up the test-data in ssm automatically.
    v2 = config['TEST_NAME']
    assert v2 == expected_values['expected_value']


def test_basic_confg_features_with_parent_chain(directory: Directory):
    current_config = config

    parent_config = Config.current()
    current_config.set_default(f"SOME_OTHER_NAME", "parent-default-value")
    current_config.set_default(f"ANOTHER_NAME", "parent-default-another-v")

    assert parent_config['SOME_OTHER_NAME'] == "parent-default-value"
    assert parent_config['ANOTHER_NAME'] == "parent-default-another-v"

    # Testing the get_default basic method.
    assert parent_config.get_default(f"ANOTHER_NAME") == "parent-default-another-v"
    assert (
        parent_config.get_item(f"ANOTHER_NAME", skip_providers=True).value
        == "parent-default-another-v"
    )

    with Config():
        assert current_config['SOME_OTHER_NAME'] == "parent-default-value"
        current_config['SOME_OTHER_NAME'] = "overriden-on-child"
        assert current_config['SOME_OTHER_NAME'] == "overriden-on-child"

        # This happens because the child object is in the parent-chain because the child
        # is the current config.
        assert parent_config.get("SOME_OTHER_NAME") == "overriden-on-child"

        # The parent check's it's self first before looking at the parent chain.
        parent_config['SOME_OTHER_NAME'] = "overriden-on-parent"
        assert parent_config['SOME_OTHER_NAME'] == "overriden-on-parent"

        # We should still be able to get the default via this method
        assert parent_config.get_default(f"SOME_OTHER_NAME") == "parent-default-value"
        assert current_config.get_default(f"SOME_OTHER_NAME") is Default

        assert parent_config.get_override('SOME_OTHER_NAME') == "overriden-on-parent"
        # Remove the override, see if that worked.
        parent_config['SOME_OTHER_NAME'] = Default
        assert parent_config['SOME_OTHER_NAME'] == "overriden-on-child"
        assert parent_config.get_override('SOME_OTHER_NAME') is Default

    # The child config is no longer the current, so it's overrides are forgotten.
    assert current_config['SOME_OTHER_NAME'] == "parent-default-value"


@Config(providers=[SsmParamStoreProvider])  # Not using EnvironmentalProvider, only Ssm...Provider.
def test_exported_values(directory: Directory):
    # This is for making sure the default value does not somehow override other ways
    # config get's it's value [Config should use defaults as the last-resort].
    config.set_default('some_exported_name', 'default-value')
    another_service = "another_service"

    config.add_export(service=another_service)

    # Put some test-data in ssm.
    client = boto_clients.ssm
    client.put_parameter(
        Name=f'/{another_service}/export/{directory.env}/some_exported_name',
        Value="an-exported-value",
        Type="String",
    )

    # Grab the existing values from the providers, make sure we see it [also caches it in cacher].
    assert config['SOME_EXPORTED_NAME'] == 'an-exported-value'

    # todo: Put some normal config values in the normal directories, ensure exported
    #   values don't override any of them.


def test_env_and_defaults_do_not_go_into_cache(directory: Directory):
    # Re-enable the cacher by default, so we can test cacher-related features
    # (it's set to None by default for unit tests)
    config.cacher = Default

    # This is for making sure the default value does not somehow override other ways
    # config get's it's value [Config should use defaults as the last-resort].
    config.set_default('TEST_CACHER_NOT_USED', 'default-value')

    # Grab the existing values from the providers, make sure we see it [also caches it in cacher].
    assert config['TEST_CACHER_NOT_USED'] == 'default-value'

    # Define our env-var.
    with EnvironmentalProvider(env_vars={'TEST_CACHER_NOT_USED': 'rightValue'}):
        # Make sure the environmental variable is now taking priority over cacher.
        assert config['TEST_CACHER_NOT_USED'] == "rightValue"

    # Ensure the values did not go into the cache
    # we are verifying that the cache got updated correctly with this check.
    cacher_obj = DynamoCacher.grab()
    assert (
        cacher_obj.get_value(
            name='TEST_CACHER_NOT_USED',
            directory=directory,
            directory_chain=config.directory_chain,
            provider_chain=config.provider_chain,
            environ=Directory(service=xcon_settings.service, env=xcon_settings.environment),
        )
        is None
    )


@config_with_env_dyn_ssm_secrets_providers
def test_env_and_defaults_do_not_go_into_cache(directory: Directory):
    # Re-enable the cacher by default, so we can test cacher-related features
    # (it's set to None by default for unit tests)
    # This is the root-config (via the config fixture).
    config.cacher = DynamoCacher

    # This is for making sure the default value does not somehow override other ways
    # config get's it's value [Config should use defaults as the last-resort].
    config.set_default('TEST_CACHER_NOT_USED', 'default-value')

    # Grab the existing values from the providers, make sure we see it [also caches it in cacher].
    assert config['TEST_CACHER_NOT_USED'] == 'default-value'

    # Define our env-var.
    with EnvironmentalProvider(env_vars={'TEST_CACHER_NOT_USED': 'rightValue'}):
        # Make sure the environmental variable is now taking priority over cacher.
        assert config['TEST_CACHER_NOT_USED'] == "rightValue"

    # Make sure it goes back to previous value from defaults
    assert config['TEST_CACHER_NOT_USED'] == 'default-value'

    assert xcon_settings.service == 'testing'

    # Ensure the values did not go into the cache
    # we are verifying that the cache got updated correctly with this check.
    cacher_obj = DynamoCacher.grab()
    cached_item = cacher_obj.get_item(
        name='TEST_CACHER_NOT_USED',
        directory=directory,
        directory_chain=config.directory_chain,
        provider_chain=config.provider_chain,
        environ=Directory(service=xcon_settings.service, env=xcon_settings.environment),
    )

    assert cached_item.value is None
    assert cached_item.directory.is_non_existent

    # Put some test-data in ssm.
    client = boto_clients.ssm
    client.put_parameter(
        Name=f'{directory.path}/test_cacher_not_used', Value="ssmValue", Type="String"
    )

    # Cacher already cached this (from earilier)
    assert config['TEST_CACHER_NOT_USED'] == "default-value"

    # We are no longer using a cacher, but SsmParamStoreProvider already looked up values in
    # ssm before we made our ssm change and should still return the old value.
    config2 = Config(cacher=None)
    assert config2['TEST_CACHER_NOT_USED'] == "default-value"

    # We create a brand-new blank SsmParamStoreProvider, when this provider is asked
    # about a value, it will re-lookup the value since it knows nothing.
    with SsmParamStoreProvider():
        # We are using a new config via `with` statement, we turn off the cacher to force
        # Config to ask SsmParamStoreProvider again for the value.
        with Config(cacher=None):
            assert config['TEST_CACHER_NOT_USED'] == "ssmValue"

        # Ensure the temporary config object is not being used anymore, should use cacher again.
        assert config['TEST_CACHER_NOT_USED'] == "default-value"


def test_config_item_not_logging_value(directory: Directory):
    config['SOME_SETTING'] = "my-value"
    item = config.get_item('some_setting')
    # Normal string should NOT include value (security)
    assert 'my-value' not in f'{item}'

    # Debug console should print out the value.
    assert 'my-value' in item.__repr__()


def test_secrets_manager_provider():
    config.providers = [EnvironmentalProvider, SecretsManagerProvider]
    boto_clients.secretsmanager.create_secret(
        Name='/testing/unit/my_secret',
        SecretString='my-secret-value',
    )

    assert config.get_value('my_secret') == 'my-secret-value'
    assert config.get_value('MY_SECRET') == 'my-secret-value'


def test_secrets_manager_provider_case_insensative():
    config.providers = [EnvironmentalProvider, SecretsManagerProvider]
    boto_clients.secretsmanager.create_secret(
        Name='/testing/unit/MY_secret',
        SecretString='my-secret-value',
    )

    assert config.get_value('my_secret') == 'my-secret-value'
    assert config.get_value('MY_SECRET') == 'my-secret-value'


@Config(providers=DEFAULT_TESTING_PROVIDERS, cacher=DynamoCacher)
def test_expire_internal_local_cache(directory: Directory):
    # Basic defaults-test.
    InternalLocalProviderCache.grab().expire_time_delta = dt.timedelta(milliseconds=250)

    path = f'/{xcon_settings.service}/{xcon_settings.environment}/exp_test_value'
    boto_clients.ssm.put_parameter(
        Name=path,
        Value="expiringTestValue",
        Type="String",
    )

    # Get value cached, and ensure it's correct
    assert config.get('exp_test_value') == 'expiringTestValue'

    # Change value in SSM
    boto_clients.ssm.put_parameter(
        Name=path,
        Value="expiringTestValue2",
        Type="String",
        Overwrite=True
    )

    # Value should still be cached and be the old value
    assert config.get('exp_test_value') == 'expiringTestValue'

    # Disabling the external dynamo cacher should still return the same value,
    # as SSM provider still has its internal cache.
    config.cacher = None
    assert config.get('exp_test_value') == 'expiringTestValue'

    # Wait until it's expired, tell config to use the external dynamo cacher again.
    # We should get same value due to the DynamoCacher, because the dynamo table (external cache)
    # still has this value in its table (it will retrieve old value from external dynamo table).
    time.sleep(0.260)
    config.cacher = DynamoCacher
    assert config.get('exp_test_value') == 'expiringTestValue'

    table = _ConfigDynamoTable(table_name='global-all-configCache', cache_table=True)
    table.delete_items(table.get_all_items())
    time.sleep(0.360)

    # Removed the external dynamo cacher items from its table, and see if we get the new value now
    # (as it will now consult with ssm provider which should re-lookup the value due to expire).
    assert config.get('exp_test_value') == 'expiringTestValue2'


@Config(providers=DEFAULT_TESTING_PROVIDERS, cacher=DynamoCacher)
def test_cache_uses_env_vars_by_default(directory: Directory):
    # First, put in value in SSM
    path = f'/{xcon_settings.service}/{xcon_settings.environment}/exp_test_value_3'
    boto_clients.ssm.put_parameter(
        Name=path,
        Value="expiringTestValue3",
        Type="String",
    )

    # Override service/environment directly on config object with current values
    config.service = xcon_settings.service
    config.environment = xcon_settings.environment

    # Override xcon_settings/default with different values.
    xcon_settings.service = 'some-other-service'
    xcon_settings.environment = 'some-other-env'

    # Ensure we are working like we expect, we explicitly set service/environment directly on
    # config object; lets ensure it uses them and not the default values.
    assert config.get('exp_test_value_3') == 'expiringTestValue3'
    table = _ConfigDynamoTable(table_name='global-all-configCache', cache_table=True)
    items = list(table.get_all_items())

    # See if what we stored in the cache table is what we expect.
    assert len(items) == 1
    assert items[0].cache_hash_key == f'/{xcon_settings.service}/{xcon_settings.environment}'

    # Now, set the environmental-vars and see if cacher will use these over the ones
    # overridden on Config object:
    xcon_settings.service = 'testserv'
    xcon_settings.environment = 'testenv'

    # We should still get our value, since the overridden service/environment on Config
    # object does not change how it looks up values in SSM, SecretsManager, etc:
    assert config.get('exp_test_value_3') == 'expiringTestValue3'

    # But the cacher should use the environ-vars as the place to store the values in
    # the cache table, so check to see if the old value is still cached in old location
    # and if the cache table now has a second item with the environ-vars as the hash key.
    items = list(table.get_all_items())
    assert len(items) == 2
    hash_keys_in_table = {o.cache_hash_key for o in items}
    expected_hash_keys = {f'/some-other-service/some-other-env', '/testserv/testenv'}
    assert hash_keys_in_table == expected_hash_keys


@Config(providers=DEFAULT_TESTING_PROVIDERS, cacher=DynamoCacher)
def test_dynamo_cacher_retrieves_new_values_after_local_cache_expires(directory: Directory):
    # Basic defaults-test.
    InternalLocalProviderCache.grab().expire_time_delta = dt.timedelta(milliseconds=250)

    path = f'/{xcon_settings.service}/{xcon_settings.environment}/exp_test_value'
    boto_clients.ssm.put_parameter(
        Name=path,
        Value="expiringTestValue",
        Type="String",
    )

    # Get value cached, and ensure it's correct
    assert config.get('exp_test_value') == 'expiringTestValue'

    # Change value in SSM
    boto_clients.ssm.put_parameter(
        Name=path,
        Value="expiringTestValue2",
        Type="String",
        Overwrite=True
    )

    # Value should still be cached and be the old value
    assert config.get('exp_test_value') == 'expiringTestValue'

    # Disabling the external dynamo cacher should still return the same value,
    # as SSM provider still has its internal cache.
    config.cacher = None
    assert config.get('exp_test_value') == 'expiringTestValue'

    # Wait until it's expired, tell config to use the external dynamo cacher again.
    # We should get same value due to the DynamoCacher, because the dynamo table (external cache)
    # still has this value in its table (it will retrieve old value from external dynamo table).
    config.cacher = DynamoCacher
    assert config.get('exp_test_value', ignore_local_caches=True) == 'expiringTestValue'

    table = _ConfigDynamoTable(table_name='global-all-configCache', cache_table=True)
    table.delete_items(table.get_all_items())

    # Removed the external dynamo cacher items from its table, and see if we get the new value now
    # (as it will now consult with ssm provider which should re-lookup the value due to expire).
    assert config.get('exp_test_value', ignore_local_caches=True) == 'expiringTestValue2'


@Config(providers=DEFAULT_TESTING_PROVIDERS)
def test_directory_order_followed():
    s = xcon_settings.service
    e = xcon_settings.environment

    boto_clients.ssm.put_parameter(Name='/global/all/testv', Value="/g/a", Type="String")
    assert config['testv'] == "/g/a"

    boto_clients.ssm.put_parameter(Name=f'/global/{e}/testv', Value="/g/e", Type="String")
    with InternalLocalProviderCache():
        assert config['testv'] == "/g/e"

    boto_clients.ssm.put_parameter(Name=f'/{s}/all/testv', Value="/s/a", Type="String")
    with InternalLocalProviderCache():
        assert config['testv'] == "/s/a"

    boto_clients.ssm.put_parameter(Name=f'/{s}/{e}/testv', Value="/s/e", Type="String")
    with InternalLocalProviderCache():
        assert config['testv'] == "/s/e"

    # Cache is still here, it only originally saw '/g/a'
    assert config['testv'] == "/g/a"

    InternalLocalProviderCache.grab().reset_cache()

    assert config['testv'] == "/s/e"

    config.directories = [
        "/global/all/",
        "/{service}/{environment}"
    ]

    assert config['testv'] == "/g/a"

    config.directories = Default
    assert config['testv'] == "/s/e"


