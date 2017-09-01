
'''
This file serves as an extension to the DRF docs. It removes the model dependancy when accesing parameter descriptions.

'''


import re

from rest_framework import  schemas
from rest_framework.utils import formatting
from rest_framework.compat import coreapi, coreschema, uritemplate
from django.utils.encoding import smart_text
import logging
logger = logging.getLogger(__name__)


header_regex = re.compile('^[a-zA-Z][0-9A-Za-z_]*:')


class ModifiedSchemaGenerator(schemas.SchemaGenerator):

    def get_description(self, path, method, view):
        method_name = getattr(view, 'action', method.lower())
        method_docstring = getattr(view, method_name, None).__doc__
        if method_docstring:
            # An explicit docstring on the method or action.
            try:
                method_docstring = method_docstring.split(':', 1)[0]
            except:
                pass
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

        fields = []

        if method_docstring:
            # An explicit docstring on the method or action.
            try:
                param_docstrings = method_docstring.split(':param')
            except:
                param_docstrings = None

        for variable in uritemplate.variables(path):
            title = ''
            description = ''
            if param_docstrings is not None:
                for i in range(1, len(param_docstrings)):
                    if variable in param_docstrings[i]:
                        try:
                            desc_part = param_docstrings[i].split(":")[1]
                        except KeyError:
                            desc_part = param_docstrings[i].split(variable)[1]
                        description = formatting.dedent(smart_text(desc_part))
                        break
            schema_cls = coreschema.String

            field = coreapi.Field(
                name=variable,
                location='path',
                required=True,
                schema=schema_cls(title=title, description=description)
            )
            fields.append(field)

        if method_docstring:
            try:
                qparam_docstrings = method_docstring.split(':queryparam')
                schema_cls = coreschema.String
                for i in range(1, len(qparam_docstrings)):
                    try:
                        qname, desc = qparam_docstrings[i].split(':', 1)
                    except ValueError:
                        logger.error('cannot determine queryparam name/desc from "{}"'
                                     .format(qparam_docstrings[i]))
                        continue
                    field = coreapi.Field(
                        name=qname.strip(),
                        location='query',
                        required=False,
                        schema=schema_cls(title='', description=desc))
                    fields.append(field)
            except:
                pass

        return fields
