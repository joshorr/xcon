import os
import moto

import pytest

os.environ['APP_NAME'] = 'testing'
os.environ['APP_ENV'] = 'unit'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'


@pytest.fixture(autouse=True)
def moto_boto():
    with moto.mock_aws():
        yield
