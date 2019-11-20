from collections.abc import Iterator
from unittest import TestCase, mock

from xsdata.codegen.resolver import DependenciesResolver
from xsdata.models.codegen import Attr, Class, Package
from xsdata.models.elements import Schema


class DependenciesResolverTest(TestCase):
    def setUp(self) -> None:
        self.resolver = DependenciesResolver()

    @mock.patch.object(DependenciesResolver, "resolve_imports")
    @mock.patch.object(DependenciesResolver, "create_class_list")
    @mock.patch.object(DependenciesResolver, "create_class_map")
    def test_process(
        self, mock_create_class_map, create_class_list, mock_resolve_imports
    ):
        classes = [Class(name=name) for name in "ab"]
        schema = Schema.create()
        package = "foo.bar.thug"

        mock_create_class_map.return_value = {"b": classes[0]}
        create_class_list.return_value = classes[::-1]

        self.resolver.imports.append(Package(name="foo", source="bar"))
        self.resolver.aliases = {"a": "a"}

        self.resolver.process(classes, schema, package)
        self.assertEqual([], self.resolver.imports)
        self.assertEqual({}, self.resolver.aliases)

        self.assertEqual(
            mock_create_class_map.return_value, self.resolver.class_map
        )
        self.assertEqual(
            create_class_list.return_value, self.resolver.class_list
        )
        self.assertEqual(schema, self.resolver.schema)
        self.assertEqual(package, self.resolver.package)
        self.assertEqual(package, self.resolver.package)

        mock_resolve_imports.assert_called_once_with()

    def test_sorted_imports(self):
        packages = [Package(name=x, alias=None, source="foo") for x in "cab"]
        self.resolver.imports = packages

        result = self.resolver.sorted_imports()
        self.assertIsNot(packages, result)

        self.assertEqual(packages[1], result[0])
        self.assertEqual(packages[2], result[1])
        self.assertEqual(packages[0], result[2])

    @mock.patch.object(DependenciesResolver, "apply_aliases")
    @mock.patch.object(DependenciesResolver, "add_package")
    def test_sorted_classes(self, mock_add_package, mock_apply_aliases):
        mock_apply_aliases.side_effect = lambda x: x

        self.resolver.class_list = ["a", "b", "c", "d"]
        self.resolver.class_map = {x: Class(name=x) for x in "ca"}

        result = self.resolver.sorted_classes()
        self.assertIsInstance(result, Iterator)

        expected = [self.resolver.class_map[x] for x in "ac"]

        self.assertEqual(expected, list(result))
        mock_apply_aliases.assert_has_calls([mock.call(x) for x in expected])
        mock_add_package.assert_has_calls([mock.call(x) for x in expected])

    def test_apply_aliases(self):
        self.resolver.aliases = {"d": "IamD", "a": "IamA"}
        obj = Class(
            name="a",
            attrs=[Attr(name=x, type=x, local_type="Element") for x in "ab"],
            inner=[
                Class(
                    name="b",
                    attrs=[
                        Attr(name=x, type=x, local_type="Element")
                        for x in "cd"
                    ],
                ),
            ],
        )

        result = self.resolver.apply_aliases(obj)
        self.assertIs(result, obj)
        self.assertEqual("IamA", obj.attrs[0].type_alias)
        self.assertIsNone(obj.attrs[1].type_alias)
        self.assertIsNone(obj.inner[0].attrs[0].type_alias)
        self.assertEqual("IamD", obj.inner[0].attrs[1].type_alias)

    @mock.patch.object(DependenciesResolver, "add_import")
    @mock.patch.object(DependenciesResolver, "find_package")
    @mock.patch.object(DependenciesResolver, "import_classes")
    def test_resolve_imports(
        self, mock_import_classes, mock_find_package, mock_add_import
    ):
        classes = [
            "foo",  # cool
            "bar",  # cool
            "thug:life",  # life class exists add alias
            "common:type",  # type class doesn't exist add just the name
        ]
        self.resolver.class_map = {"life": Class(name="life")}
        mock_import_classes.return_value = classes
        mock_find_package.side_effect = ["first", "second", "third", "forth"]

        self.resolver.resolve_imports()
        mock_add_import.assert_has_calls(
            [
                mock.call(alias=None, name="foo", package="first"),
                mock.call(alias=None, name="bar", package="second"),
                mock.call(alias="thug:life", name="life", package="third"),
                mock.call(alias=None, name="type", package="forth"),
            ]
        )

    def test_add_import(self):
        self.assertEqual(0, len(self.resolver.imports))

        self.resolver.add_import("foo", "there", "bar")
        self.resolver.add_import("thug", "there", None)

        first = Package(name="foo", alias="bar", source="there")
        second = Package(name="thug", alias=None, source="there")

        self.assertEqual(2, len(self.resolver.imports))
        self.assertEqual(first, self.resolver.imports[0])
        self.assertEqual(second, self.resolver.imports[1])
        self.assertEqual({"bar": "bar"}, self.resolver.aliases)

    def test_add_package(self):
        self.resolver.schema = Schema.create(
            target_namespace="http://foobar/common"
        )
        self.resolver.package = "common.foo"
        self.resolver.add_package(Class(name="foobar"))
        self.resolver.add_package(Class(name="none"))

        expected = {
            "{http://foobar/common}foobar": "common.foo",
            "{http://foobar/common}none": "common.foo",
        }
        self.assertEqual(expected, self.resolver.processed)

    def test_find_package(self):
        self.resolver.schema = Schema.create(
            nsmap={
                "common": "http://wwww.foobar.xx/common",
                "other": "http://wwww.foobar.xx/other",
            }
        )

        self.resolver.processed.update(
            {
                "{http://wwww.foobar.xx/common}foobar": "foo.bar",
                "{http://wwww.foobar.xx/common}something": "some.thing",
            }
        )

        self.assertEqual(
            "foo.bar", self.resolver.find_package("common", "foobar")
        )
        with self.assertRaises(KeyError):
            self.resolver.find_package("other", "something")

    def test_import_classes(self):
        self.resolver.class_list = [x for x in "abcdefg"]
        self.resolver.class_map = {x: x for x in "bdg"}
        self.assertEqual(["a", "c", "e", "f"], self.resolver.import_classes())

    def test_create_class_map(self):
        classes = [Class(name=name) for name in "ab"]
        expected = {obj.name: obj for obj in classes}
        self.assertEqual(expected, self.resolver.create_class_map(classes))

    def test_create_class_list(self):
        first = Class(
            name="a",
            inner=[
                Class(
                    name="b",
                    attrs=[
                        Attr(
                            name="c", type="f", local_type="", forward_ref=True
                        ),
                        Attr(name="d", type="xs:string", local_type=""),
                        Attr(name="e", type="c:g", local_type=""),
                    ],
                ),
                Class(
                    name="f",
                    attrs=[
                        Attr(name="h", type="i", local_type=""),
                        Attr(name="j", type="xs:string", local_type=""),
                        Attr(name="k", type="l", local_type=""),
                    ],
                ),
            ],
        )
        second = Class(
            name="l", attrs=[Attr(name="m", type="o", local_type="")]
        )
        third = Class(name="p", extensions=["xs:int", "a"])

        classes = [first, second, third]
        expected = ["c:g", "i", "o", "l", "a", "p"]
        self.assertEqual(expected, self.resolver.create_class_list(classes))