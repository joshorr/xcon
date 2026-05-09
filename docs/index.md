---
title: Getting Started
---
## Getting Started

???+ warning "Docs not finished and are out of date!"
    This is pre-release software, based on another code base and the docs
    have not yet been completely finished/changed to accommodate the changes
    made to clean aspects of it.

    This will be fixed soon.

    For now, if you see refrences/names to things that don't exist
    or have slightly different names in code, just beware of the situation.

    Thank you for your support while the code base transitions to being open-source!

This read me is split into several sections.

The first is a quick reference on specific environmental variables, and basic use
so people coming back to document can just look at that to remind themselves.

Second part is a quick start section, that has basic information on how to install
and use the config library in projects/code.

Third part goes in-depth on various topics, so someone looking for more details on how
config works can get them.

# Special Env-Vars / Settings

Quick reference to commonly used settings that you might need to lookup quickly and reference
while using config in an ongoing basis.

If you know nothing and want the basics, go to [Why Use](#why-use)

Many of the settings have environmental variables you can use,
if the settings are not explicitly set then it falls-back to
the environmental variables.

The simplest way to explicitly set the settings is to import the
xcon_settings object and set the attributes on it; ie:

```python
from xcon import xcon_settings

# Example of explicitly setting service name:
xcon_settings.service = "MyAppName"
```

### XCON_ONLY_ENV_PROVIDER

If "true", by default Config will only use env-variables.

You can also set this via 
[`XconSettings.only_env_provider`](api/xcon/conf.html#xcon.conf.XconSettings.only_env_provider){target=_blank}.

This also implicitly disables the default cacher.

See [Disable Default Dynamo Caching](detailed_overview.md#disable-default-dynamo-caching)
See [Disable Cache + Non-Environmental Providers](detailed_overview.md#disable-cache-non-environmental-providers)


### XCON_DISABLE_DEFAULT_CACHER

If 'true', by default dynamo cacher will be disabled, unless specifically overridden.
(ie: the `Default` instance of the dynamo cacher is `None`).

You can also set this via 
[`XconSettings.disable_default_cacher`](api/xcon/conf.html#xcon.conf.XconSettings.disable_default_cacher){target=_blank}.

See [Disable Default Dynamo Caching](detailed_overview.md#disable-default-dynamo-caching)


### APP_ENV / APP_NAME

These are the defaults for [`Config.service`](api/xcon/config.html#xcon.config.Config.service){target=_blank}
and [`Config.environment`](api/xcon/config.html#xcon.config.Config.environment){target=_blank},
that config uses to construct its `Default` list of directories to search
when looking for things.

Also, these are used by DynamoCacher to determine the hash-key it uses to store cached values.
If either of these env-vars are blank/non-existent, then
[`DynamoCacher`](api/xcon/providers/dynamo.html#xcon.providers.dynamo.DynamoCacher){target=_blank}
will fall back to using [`Config.service`](api/xcon/config.html#xcon.config.Config.service){target=_blank}
and [`Config.environment`](api/xcon/config.html#xcon.config.Config.environment){target=_blank}
for the hash-key it uses for the DynamoCache table.


# Why Use

xcon's goal as a library is to simplify/abstract configuration lookup for our various
processors and services. Allows us to easily add new providers/services for configuration
with minimal changes to our projects (normally, just updating to latest `xcon` library).

It's also more secure to retrieve secrets at run time than store them as environmental
variables, since env-variables are normally stored in a task or lambda definition and are
more easily seen and usually not-encrypted (although that's improving over time in aws).


# Quick Start

## Install

```bash
# via pip
pip install xcon

# via poetry
poetry add xcon
```


## Using It

From the get-go and by default, environmental variables will 'just work'.

The main class is `Config` via `from xcon import Config`.

This class uses [xinject](https://pypi.org/project/xinject/) to do dependency injection.
You can easily inject a new version/configuration of the object without having to couple you code too close
together to get your configuration settings.

You get the current Config object via:

```python
from xcon import Config

current_config = Config.grab()
setting_value = current_config.get('some_setting')
```

An easier way to always use the current Config object is to use a proxy object.

```python
# Instead of importing the class, we import a proxy to the currently injected instance:
from xcon import config

setting_value = config.get('some_setting')
```

Alternatively, ou can also use `Config.proxy()` to get a proxy.

```python
# Importing proxy object to current Config injectable dependency.
# You can use it as if you did `Config.grab()`, as it does this
# for you each time you get something from it.
from xcon import config
import os

# Setting a environmental variable value to showcase retrieving it.
os.environ['SOME_CONFIG_VARIABLE'] = "my-value"

# If you had an environmental variable called `SOME_CONFIG_VARIABLE`, this would find it:
assert config.get('some_config_variable') == "my-value"

# Alternate 'dict; syntax, works just like you would expect.
# Just like dict, it will raise an exception if value not found.
assert config['some_config_variable'] == "my-value"
```

Config names are case-insensitive (although directory names are case-sensitive).

By default, [`Config`](api/xcon/config.html#xcon.config.Config){target=_blank} will look at environmental variables first,
and then other remote places second (the order and where to look is all configurable).

# Quick Overview

## Places Configuration is Retrieved From

As a side note for the below paths the `SERVICE_NAME` and `APP_ENV`variables
come from `xcon.xcon_settings.environment` and `xcon.xcon_settings.service`.
By default, these settings will use the `SERVICE_NAME` and `APP_ENV`
environmental variables. You can also set/override them expiclity
by setting a value one `xcon.xcon_settings.environment` and/or `xcon.xcon_settings.service`.

By default, Config will look in these paths (first).

- /{APP_NAME}/{APP_ENV}/{variable_name}
- /{APP_NAME}/all/{variable_name}
- /global/{APP_ENV}/{variable_name}
- /global/all/{variable_name}
- Details:
    - [Standard Directory Paths](detailed_overview.md#standard-directory-paths) 
    - [Directory Chain](detailed_overview.md#directory-chain)

For each directory/path, we go through these providers (second):

1. Environmental Variables
2. Dynamo Config Cache
    - Will be skipped if table/permissions don't exist.
3. AWS Secrets Manager
    - Will be skipped if needed permissions not in place
4. AWS Param Store
    - Will be skipped if needed permissions not in place
- Details:
    - [Provider Chain](detailed_overview.md#provider-chain)
    - [Supported Providers](detailed_overview.md#supported-providers)

In the order they are specified above (see [Standard Lookup Order](detailed_overview.md#standard-lookup-order)).

### Param Store Provider Specifics

Values are exclusively retrieved via "GetParametersByPath"; which allows for bulk-retrieval of settings.

All settings in a particular directory are retrieved in one request, and then whatever value is needed is returned.
These values are cached within the provider retriever object, so when other config values are asked for
there is a good chance it can return a value without having to go back to param store to ask for another value.

### Secrets Manager Provider Specifics

Secrets manager does not allow for bulk-retrieval of values.
Instead, you can bulk-request get a list of available secret names via `ListSecretVersionIds`.

The secrets provider will grab the full list, and then use that to know what is or is not available to get.
This makes it much faster, as it can quickly determine if it should attempt to retrieve a value or not based on this list.

## Case Sensitivity

The directory/path is case-sensitive; but the `VARIABLE_NAME` part at the end is case-insensitive.

So environmental variables are entirely case-insensitive, as they only have the `VAIRABLE_NAME`
and no directory path.

So you can do `config.get('some_var_name')`, and it would still find a value for it,
even if the name in the source/provider of values is `SOME_VAR_NAME`.

## Add Permissions

If you want to receive values from remote locations, the app will need the correct permissions.

For example, AWS's Param Store service will restrict access to the param values by path/directory.

There is a serverless permission resource template yaml file you can use directory or copy
and change as needed for your purposes.

- AWS Configuration Store Permissions:
    - [Param Store](https://github.com/joshorr/xcon/blob/main/xcon/serverless_files/ssm-permissions.yml)
    - [Secrets Manager](https://github.com/joshorr/xcon/blob/main/xcon/serverless_files/secrets-permissions.yml)

If you want to use a dynamo table cache (see [caching](#caching) in next section), use these:

- DynamoDB Cache Table:
    - [App Permissions](https://github.com/joshorr/xcon/blob/main/xcon/serverless_files/config_manager/cache-table.yml)
    - [Table Definition](https://github.com/joshorr/xcon/blob/main/xcon/serverless_files/cache-permissions.yml)

For more details, see [Permissions](detailed_overview.md#permissions).


## Caching

The purpose of the cache is to limit calls to the providers,
to prevent throttling from them.

For example, the AWS Param Store will throttle calls if there are too many per-second,
which could happen if several lambdas get launched and each lookup configuration simultaneously.

By default, values that are remotely looked up (ie: non-environmental variables)
are cached in a dynamo table.
Each of these lambdas can first check a DynamoDB cache table first, and if the value they need
is in there it will use that instead of attempting to retrieve values from the providers.

When something is not in the cache table, Config will look at each configured provider
and when it finds the value (or lack of a value), it will store what it found in the
dynamo cache table for later faster lookup.

The cache is a flattened list of all resolved values from all configured sources.
It will correctly cache according to the current providers, paths, and app environment + service.
Any of these variables can dynamically change, this information is added to each cached
entry so the correct value will be used in any situation.

### Time to live

The cache table is configured with a time-to-live attribute (named `ttl`).
The value is set for 12 hours, after which the item will expire.

There is an logarithm built into `Config` caching mechanism that will
pre-expire items sooner than normal randomly.
The algorith makes it more likely a particular item in the cache will expire
sooner as the expire-time approaches.

This means something that will expire in one hour will be more likely to
be pre-expired than something  that has 10 hours left.

This helps ensure that if a lambda is very busy and has many concurrent
instances running that it's likely only one of the lambdas would pre-expire
the cached items and 'refresh' them by re-looking up the values from the
providers and re-caching the newly looked up values.

This is a way to coordinate cache expiring and refreshing without
having to actually have any coordinating communication happening.

This allows the configuration refreshing to automatically scale
with the lambda activity in such a way as to limit the possibility
of being throttled from param store or secrets manager.

### Table Layout Details

The dynamo table has a two-part primary key.

The first part of the primary key is a hash key made up of apps
`xcon.xcon_settings.environment` and `xcon.xcon_settings.service` values.
This is the 'partition' key in the DynamoDB table, and AWS policies can allow
or deny access based on this hash key.
This allows the table to limit access to cached items by app's environment + service.

The second part of the primary key is a range-key made up of all provider names
and directory paths in the order they are looked up in. This allows multiple
values to be stored for the same config setting, depending on which providers
and directory paths were used to lookup the config setting.

This allows all looked up values for all dynamic situations to be cached
and used correctly.

For details see [Caching Details](detailed_overview.md#caching-details), [Historical Background](detailed_overview.md#historical-background).

## Unit Tests

By default, unit tests will always start with a Config object that has caching disabled,
and only uses the environmental provider (ie: only looks at environmental variables).

This is accomplished via an autouse fixture in a pytest plugin module
(see plugin module `xcon.pytest_plugin` or fixture `xcon.pytest_plugin.xcon`).

If a project has `xcon` as a dependency, pytest will find this plugin module
and automatically use it. Nothing more to do.

As an FYI/side-note: There is a `xinject.pytest_plugin.xyn_context` that will also
automatically  configure a blank context for each unit test.

This does mean you must configure Config using a fixture or at the top of your unit test method,
as any changes at the module-level will be forgotten.

The reason we do this is it guarantees that resources/config changes won't be propagaed/leak
into another unit test.

The end result is there is need to worry about these basics,
as they are taken care of for you automatically as long as the library is installed
as a dependency.




