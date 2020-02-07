# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import json
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

from crashstats.crashstats.models import Product
from crashstats.crashstats.signals import PERMISSIONS
from crashstats.crashstats.tests.testbase import DjangoTestCase
from socorro.external.es.super_search_fields import FIELDS


class Response(object):
    def __init__(self, content=None, status_code=200):
        self.raw = content
        if not isinstance(content, str):
            content = json.dumps(content)
        self.content = content.strip()
        self.status_code = status_code

    @property
    def text(self):
        # Similar to content but with the right encoding
        return str(self.content, "utf-8")

    def json(self):
        return self.raw


class ProductVersionsMixin:
    """Mixin for DjangoTestCase tests to create products and versions

    This creates products.

    This mocks the function that sets the versions in the response context
    and the versions dropdown in the navbar.

    The versions dropdown is generated by get_versions_for_product which does
    a Supersearch. This lets you mock out that function to return default
    versions or specific versions.

    Usage::

        class TestViews(TestCase, ProductVersionsMixin):
            def test_something(self):
                # ...
                pass

            def test_something_else(self):
                self.set_product_versions(['64.0', '63.0', '62.0'])
                # ...
                pass

    """

    def setUp(self):
        super().setUp()
        cache.clear()

        # Create products
        Product.objects.create(product_name="WaterWolf", sort=1, is_active=True)
        Product.objects.create(product_name="NightTrain", sort=2, is_active=True)
        Product.objects.create(product_name="SeaMonkey", sort=3, is_active=True)

        # Create product versions
        self.mock_gvfp_patcher = mock.patch(
            "crashstats.crashstats.utils.get_versions_for_product"
        )
        self.mock_gvfp = self.mock_gvfp_patcher.start()
        self.set_product_versions(["20.0", "19.1", "19.0", "18.0"])

    def tearDown(self):
        self.mock_gvfp_patcher.stop()
        super().tearDown()

    def set_product_versions(self, versions):
        self.mock_gvfp.return_value = versions


class SuperSearchFieldsMock:
    def setUp(self):
        super().setUp()

        def mocked_supersearchfields(**params):
            results = copy.deepcopy(FIELDS)
            # to be realistic we want to introduce some dupes that have a
            # different key but its `in_database_name` is one that is already
            # in the hardcoded list (the baseline)
            results["accessibility2"] = results["accessibility"]
            return results

        self.mock_ssf_get_patcher = mock.patch(
            "crashstats.supersearch.models.SuperSearchFields.get"
        )
        self.mock_ssf_fields_get = self.mock_ssf_get_patcher.start()
        self.mock_ssf_fields_get.side_effect = mocked_supersearchfields

    def tearDown(self):
        self.mock_ssf_get_patcher.stop()
        super().tearDown()


class BaseTestViews(ProductVersionsMixin, SuperSearchFieldsMock, DjangoTestCase):
    def setUp(self):
        super().setUp()

        # Tests assume and require a non-persistent cache backend
        assert "LocMemCache" in settings.CACHES["default"]["BACKEND"]

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _add_permission(self, user, codename, group_name="Hackers"):
        group = self._create_group_with_permission(codename)
        user.groups.add(group)

    def _create_group_with_permission(self, codename, group_name="Group"):
        appname = "crashstats"
        ct, __ = ContentType.objects.get_or_create(model="", app_label=appname)
        permission, __ = Permission.objects.get_or_create(
            codename=codename, name=PERMISSIONS[codename], content_type=ct
        )
        group, __ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(permission)
        return group

    @staticmethod
    def only_certain_columns(hits, columns):
        """Return new list where dicts only have specified keys"""
        return [dict((k, x[k]) for k in x if k in columns) for x in hits]
