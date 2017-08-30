
'''
This file serves as an extension to the DRF docs. It removes the model dependancy when accesing parameter descriptions.

'''



import re

from django.conf.urls import include, url
from rest_framework.documentation import get_docs_view,get_schemajs_view
from rest_framework import  schemas
from rest_framework.utils import formatting
from rest_framework.compat import (
    coreapi, coreschema, uritemplate,
)
from django.utils.encoding import smart_text

header_regex = re.compile('^[a-zA-Z][0-9A-Za-z_]*:')


class ModifiedSchemaGenerator(schemas.SchemaGenerator):

    def get_description(self, path, method, view):
        method_name = getattr(view, 'action', method.lower())
        method_docstring = getattr(view, method_name, None).__doc__
        if method_docstring:
            # An explicit docstring on the method or action.
            method_docstring = method_docstring.split(':param')[0]
            return formatting.dedent(smart_text(method_docstring))

        description = view.get_view_description()
        lines = [line.strip() for line in description.splitlines()]
        current_section = ''
        sections = {'': ''}

        for line in lines:
            if header_regex.match(line):
                current_section, seperator, lead = line.partition(':')
                sections[current_section] = lead.strip()
            else:
                sections[current_section] += '\n' + line

        header = getattr(view, 'action', method.lower())
        if header in sections:
            return sections[header].strip()
        if header in self.coerce_method_names:
            if self.coerce_method_names[header] in sections:
                return sections[self.coerce_method_names[header]].strip()
        return sections[''].strip()

    def get_path_fields(self, path, method, view):
        method_name = getattr(view, 'action', method.lower())
        method_docstring = getattr(view, method_name, None).__doc__
        if method_docstring:
            # An explicit docstring on the method or action.
            try:
                param_docstrings = method_docstring.split(':param')
            except:
                param_docstrings = ''

        fields = []

        for variable in uritemplate.variables(path):
            title = ''
            description = ''
            if param_docstrings:
                if len(param_docstrings)>2:
                    for i in range(1,len(param_docstrings)):
                        if variable in param_docstrings[i]:
                            description = formatting.dedent(smart_text(param_docstrings[i].split(":")[1]))
                else:
                    try:
                        description=formatting.dedent(smart_text(param_docstrings[1].split(":")[1]))
                    except:
                        pass
            schema_cls = coreschema.String

            field = coreapi.Field(
                name=variable,
                location='path',
                required=True,
                schema=schema_cls(title=title, description=description)
            )
            fields.append(field)

        return fields


def include_docs_urls(
        title=None, description=None, schema_url=None, public=True,
        patterns=None, generator_class=ModifiedSchemaGenerator):
    docs_view = get_docs_view(
        title=title,
        description=description,
        schema_url=schema_url,
        public=public,
        patterns=patterns,
        generator_class=generator_class,
    )
    schema_js_view = get_schemajs_view(
        title=title,
        description=description,
        schema_url=schema_url,
        public=public,
        patterns=patterns,
        generator_class=generator_class,
    )
    urls = [
        url(r'^$', docs_view, name='docs-index'),
        url(r'^schema.js$', schema_js_view, name='schema-js')
    ]
    return include(urls, namespace='api-docs')

