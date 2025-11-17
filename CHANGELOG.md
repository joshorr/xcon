# Changelog

## [1.1.0](https://github.com/joshorr/xcon/compare/v1.0.0...v1.1.0) (2025-11-17)


### Features

* allow subpaths to be grabbed in ssm. ([796469b](https://github.com/joshorr/xcon/commit/796469b943ee0701d4c9e6a75263eac64c40afec))


### Bug Fixes

* don't log out all of the names  retrieved, add that to 'extra', just too much info in there. ([2859370](https://github.com/joshorr/xcon/commit/28593700cdb72aa84a79b1f7a7ef1bbbc286d3b5))

## [1.0.0](https://github.com/joshorr/xcon/compare/v0.5.0...v1.0.0) (2025-10-25)


### ⚠ BREAKING CHANGES

* bump to version 1.0.0.

### Features

* bump to version 1.0.0. ([009cc69](https://github.com/joshorr/xcon/commit/009cc69917ba986e81f7786e20685d05db093d04))
* will retry ssm provider with throttled + correct changelog. ([5fbdc49](https://github.com/joshorr/xcon/commit/5fbdc495157a9dd0a19baf1e114e5c1cb1508fa4))


### Bug Fixes

* doc generator, update build dependencies, fix unit tests. ([52e8a35](https://github.com/joshorr/xcon/commit/52e8a35d7d0e5123856c03d1c87f8874c3e2a64e))

## [0.8.0](https://github.com/xyngular/py-xcon/compare/v0.7.0...v0.8.0) (2024-01-03)


### Features

* project uses plain dicts as ordered sets (for now), keep old xloop behavior; upgrade python to 3.11+. ([fedaaf0](https://github.com/joshorr/xcon/commit/fedaaf01efaac5185601ea8781cc4cebf4b86e3d))
* support easily injectable dynamodb resource to use for caching. ([534bf00](https://github.com/joshorr/xcon/commit/534bf00f6e57365c3bf084734e6525f140c09ee0))
* update documentation and readme. ([c9fec02](https://github.com/joshorr/xcon/commit/c9fec023477ef2878a0e1be22d12b94cfab85fa9))
* update table of contents for readme. ([7cf59f5](https://github.com/joshorr/xcon/commit/7cf59f527773754e803f9f5d086c7060dc9b26aa))

## [0.7.0](https://github.com/xyngular/py-xcon/compare/v0.6.0...v0.7.0) (2024-01-02)


### Features

* support easily injectable dynamodb resource to use for caching. ([534bf00](https://github.com/xyngular/py-xcon/commit/534bf00f6e57365c3bf084734e6525f140c09ee0))

## [0.6.0](https://github.com/xyngular/py-xcon/compare/v0.5.0...v0.6.0) (2023-10-31)


### Features

* update table of contents for readme. ([7cf59f5](https://github.com/xyngular/py-xcon/commit/7cf59f527773754e803f9f5d086c7060dc9b26aa))


### Bug Fixes

* documentation links. ([69f6a3a](https://github.com/xyngular/py-xcon/commit/69f6a3ab29f2a04851e34645ea6147eb40f6d4e6))

## [0.5.0](https://github.com/xyngular/py-xcon/compare/v0.4.1...v0.5.0) (2023-10-31)


### Features

* update documentation and readme. ([c9fec02](https://github.com/xyngular/py-xcon/commit/c9fec023477ef2878a0e1be22d12b94cfab85fa9))

## [0.4.1](https://github.com/xyngular/py-xcon/compare/v0.4.0...v0.4.1) (2023-04-15)


### Bug Fixes

* docs ([3d5dae9](https://github.com/xyngular/py-xcon/commit/3d5dae9cd21770370f6661df7901f8d74477247e))
* pypi license reference. ([7d11803](https://github.com/xyngular/py-xcon/commit/7d11803b82df183b0402fb064dd5efb2f3ede783))
* serverless permission file examples. ([435ea6f](https://github.com/xyngular/py-xcon/commit/435ea6feffdf260dd6e2163fe6f4bbf6a20d6529))

## [0.4.0](https://github.com/xyngular/py-xcon/compare/v0.3.3...v0.4.0) (2023-02-28)


### Features

* ignore if cache table does not exist (emit warning instead). ([9ae7731](https://github.com/xyngular/py-xcon/commit/9ae773187090619b590d235812a52986607302a6))


### Bug Fixes

* default ssm serverless permissions. ([96f7e23](https://github.com/xyngular/py-xcon/commit/96f7e237c55f5d3eda17afa62d1a7f405b9b7231))

## [0.3.3](https://github.com/xyngular/py-xcon/compare/v0.3.2...v0.3.3) (2023-02-21)


### Bug Fixes

* move dev-only dependencies to correct group. ([0830fec](https://github.com/xyngular/py-xcon/commit/0830fece38c3964a772b3cd93a5d02c21a5565a7))

## [0.3.2](https://github.com/xyngular/py-xcon/compare/v0.3.1...v0.3.2) (2023-02-20)


### Bug Fixes

* doc-generator for pdoc3 dependencies. ([f8ca9f1](https://github.com/xyngular/py-xcon/commit/f8ca9f133c3610fe507c4d7959e67be73450e57b))

## [0.3.1](https://github.com/xyngular/py-xcon/compare/v0.3.0...v0.3.1) (2023-02-20)


### Bug Fixes

* project publishing metadata ([d4a2886](https://github.com/xyngular/py-xcon/commit/d4a2886ee1a2ef3a88db58fd6c4d9f83538b700a))
* reame file name case. ([dd9e513](https://github.com/xyngular/py-xcon/commit/dd9e5137d4e80e3c94dc45dee0035b4ff7dd5898))
* remove xyn_config refs (now it's `xcon`). ([223666f](https://github.com/xyngular/py-xcon/commit/223666f9085ede6a008b967dfac77ff50a5d685f))

## 0.3.0 (2023-02-20)


### Features

* ability to use format-style paths with Directory objects. ([5d44735](https://github.com/xyngular/py-xcon/commit/5d44735a83beb9ba20c3550d59f9f715d98144fa))
* ability to use formatted directory paths, changeable default directory paths. ([1816e63](https://github.com/xyngular/py-xcon/commit/1816e639ab009e5ebaeafb02af90bf76ceb95bca))
* add a bunch of documentation, rename things to fit `xcon` name better. ([6120fd7](https://github.com/xyngular/py-xcon/commit/6120fd73b2add437c120fac14d1f6c64128523b7))
* added serverless yml files that can be copied or directly used to support config-cache (if wanted/needed) ([f3c154d](https://github.com/xyngular/py-xcon/commit/f3c154dda5e79b54313034bf5b46464b726ea1de))
* by default use `all` for all environments, instead of nothing. ([9cb5593](https://github.com/xyngular/py-xcon/commit/9cb55939a5f4b0c20e779d7c7cf99fc9e941275e))
* have pdoc3 document the other dependent modules. ([c821d7b](https://github.com/xyngular/py-xcon/commit/c821d7bb62963e77bd4c3741867d8e61ccdfc2ae))
* initial code import, using `xcon` for library name. ([79ec325](https://github.com/xyngular/py-xcon/commit/79ec32526e0f6e28c5eb3f03b368d36e5f84f026))
* rename dynamo cache/provider tables hash-key/range-key to be more self-descriptive. ([f3707fc](https://github.com/xyngular/py-xcon/commit/f3707fc0d8a97f1be8af1e4b45bf264e3058dc10))
* renamed/reconfigured dependcies, got unit tests working. ([ad325ad](https://github.com/xyngular/py-xcon/commit/ad325adb81826f8a5de2a45d3eeda1b2a4045e2b))
* use xcon.conf.Settings.[environment/service] instead of SERVICE_NAME on Config object; etc. ([54709ba](https://github.com/xyngular/py-xcon/commit/54709babb4cf4de5d117e5624ff7201ff8f55a7d))


### Bug Fixes

* add tomlkit dep ([3db114e](https://github.com/xyngular/py-xcon/commit/3db114e1deeb1bd354d44274451cc82d6394e830))
* remove unneeded code ([f08e057](https://github.com/xyngular/py-xcon/commit/f08e05726678d3cb1f3dbf160f19a44f0631b4d6))
* type in name. ([d8df718](https://github.com/xyngular/py-xcon/commit/d8df718aa1579b863c051ccdfa189548415013f3))


### Documentation

* fix doc url ref. ([7be339b](https://github.com/xyngular/py-xcon/commit/7be339b449d0a71273e75525a610f8c99f926af2))
* helps doc-generator to not make these inherit from ABC ([8857908](https://github.com/xyngular/py-xcon/commit/8857908750b60f9232ef9d943dd56bd8fc0fc6b4))
* one last note about the current state of things. ([55c3dd4](https://github.com/xyngular/py-xcon/commit/55c3dd4308f6e69fdb28500ceef68475ae39372c))
